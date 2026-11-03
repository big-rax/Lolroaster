from __future__ import annotations
import discord

from .store import get_allowed_channels, get_guild_settings, set_guild_settings, set_allowed_channels

# Step 3 of /settings: pick the allowed channels, or N/A to stay channel-specific with none picked.
# Discord's channel picker only works inside the server, so from a DM it's swapped for a plain
# dropdown of the server's text channels (Discord caps dropdowns at 25 options).
class SettingsChannelView(discord.ui.View):
    def __init__(self, guild: discord.Guild, current: list[str], in_dm: bool = False):
        super().__init__(timeout=120)
        self.guild_id = str(guild.id)
        if in_dm:
            self.remove_item(self.channel_select)
            channels = sorted(guild.text_channels, key=lambda c: c.position)[:25]
            dropdown = discord.ui.Select(
                placeholder="Choose the channels the bot can use...",
                min_values=1,
                max_values=len(channels) or 1,
                options=[
                    discord.SelectOption(label=f"#{c.name}", value=str(c.id), default=str(c.id) in current)
                    for c in channels
                ] or [discord.SelectOption(label="No text channels found", value="none")],
                disabled=not channels,
                row=0,
            )
            async def dropdown_callback(interaction: discord.Interaction) -> None:
                await self.save_channels(interaction, dropdown.values)
            dropdown.callback = dropdown_callback
            self.add_item(dropdown)
        else:
            # Pre-select the channels that are already allowed so the picker shows the full list
            self.channel_select.default_values = [
                discord.SelectDefaultValue(id=int(cid), type=discord.SelectDefaultValueType.channel)
                for cid in current[:25]
            ]

    async def save_channels(self, interaction: discord.Interaction, channel_ids: list[str]) -> None:
        set_guild_settings(self.guild_id, enabled=True, mode="specific")
        set_allowed_channels(self.guild_id, channel_ids)
        mentions = ", ".join(f"<#{cid}>" for cid in channel_ids)
        await interaction.response.edit_message(content=f"✅ Lolroaster is **on** and will only yap in: {mentions}", view=None)

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        placeholder="Choose the channels the bot can use...",
        channel_types=[discord.ChannelType.text, discord.ChannelType.news],
        min_values=1,
        max_values=25,
    )
    async def channel_select(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect) -> None:
        await self.save_channels(interaction, [str(c.id) for c in select.values])

    @discord.ui.button(label="N/A (no channels yet)", style=discord.ButtonStyle.secondary, row=1)
    async def no_channels(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        set_guild_settings(self.guild_id, enabled=True, mode="specific")
        current = get_allowed_channels(self.guild_id)
        if current:
            mentions = ", ".join(f"<#{cid}>" for cid in current)
            note = f"Keeping the channels already set: {mentions}"
        else:
            note = "No channels are set yet, so it'll stay quiet until you pick some with /settings."
        await interaction.response.edit_message(content=f"✅ Lolroaster is **on** in specific channels only.\n{note}", view=None)

# Step 2 of /settings: every channel, or specific channels only.
class SettingsModeView(discord.ui.View):
    def __init__(self, guild: discord.Guild, in_dm: bool = False):
        super().__init__(timeout=120)
        self.guild = guild
        self.guild_id = str(guild.id)
        self.in_dm = in_dm

    @discord.ui.select(
        placeholder="Where should the bot interact?",
        options=[
            discord.SelectOption(label="Every channel", value="all", emoji="🌍"),
            discord.SelectOption(label="Specific channels", value="specific", emoji="📌"),
        ]
    )
    async def mode_select(self, interaction: discord.Interaction, select: discord.ui.Select) -> None:
        if select.values[0] == "all":
            set_guild_settings(self.guild_id, enabled=True, mode="all")
            await interaction.response.edit_message(content="✅ Lolroaster is **on** in every channel. God help you all.", view=None)
        else:
            current = get_allowed_channels(self.guild_id)
            await interaction.response.edit_message(
                content="Pick the channels the bot can use, or choose N/A to set them later:",
                view=SettingsChannelView(self.guild, current, self.in_dm),
            )

# Step 1 of /settings: bot on or off for the whole server.
class SettingsPowerView(discord.ui.View):
    def __init__(self, guild: discord.Guild, in_dm: bool = False):
        super().__init__(timeout=120)
        self.guild = guild
        self.guild_id = str(guild.id)
        self.in_dm = in_dm

    @discord.ui.select(
        placeholder="Turn the bot on or off for this server?",
        options=[
            discord.SelectOption(label="Bot on", value="on", emoji="🔥"),
            discord.SelectOption(label="Bot off", value="off", emoji="😶‍🌫️"),
        ]
    )
    async def power_select(self, interaction: discord.Interaction, select: discord.ui.Select) -> None:
        if select.values[0] == "off":
            mode = get_guild_settings(self.guild_id)["mode"]  # remembered for when it's turned back on
            set_guild_settings(self.guild_id, enabled=False, mode=mode)
            await interaction.response.edit_message(content="😶‍🌫️ Lolroaster is **off** for this whole server. Slash commands still work.", view=None)
        else:
            await interaction.response.edit_message(content="Where should the bot interact?", view=SettingsModeView(self.guild, self.in_dm))

# Returns True if the user has Manage Server in the guild (looked up by ID so it also works from DMs).
async def can_manage(guild: discord.Guild, user: discord.abc.User) -> bool:
    member = guild.get_member(user.id)
    if member is None:
        try:
            member = await guild.fetch_member(user.id)
        except discord.HTTPException:
            return False
    return member.guild_permissions.manage_guild

# Opens the /settings flow as a private prompt. Used by /settings, the welcome message's Set up
# button, and the DM Set up button (which passes the guild since a DM has none).
async def open_settings(interaction: discord.Interaction, guild: discord.Guild | None = None) -> None:
    guild = guild or interaction.guild
    in_dm = interaction.guild is None
    if not await can_manage(guild, interaction.user):
        await interaction.response.send_message("You need the Manage Server permission to use this.", ephemeral=True)
        return
    guild_id = str(guild.id)
    current = get_guild_settings(guild_id)
    if not current["enabled"]:
        status = "off"
    elif current["mode"] == "all":
        status = "on in every channel"
    else:
        status = "on in specific channels"
    await interaction.response.send_message(
        f"**{guild.name}**: Lolroaster is currently **{status}**.\nTurn the bot on or off for this server?",
        view=SettingsPowerView(guild, in_dm),
        ephemeral=not in_dm,
    )

# Posted when the bot joins a server. Persistent (timeout=None + fixed custom_ids) so the
# buttons keep working after a restart; main.py registers it with client.add_view().
class WelcomeView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Set up", style=discord.ButtonStyle.primary, emoji="🔥", custom_id="lolroaster:welcome:setup")
    async def setup(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await open_settings(interaction)

    @discord.ui.button(label="Skip for now", style=discord.ButtonStyle.secondary, custom_id="lolroaster:welcome:skip")
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("You need the Manage Server permission to use this.", ephemeral=True)
            return
        await interaction.response.edit_message(
            content="👋 Lolroaster is here but staying quiet for now. An admin can run `/settings` anytime to set it up.",
            view=None,
        )

# Returns the channel to post the welcome message in: the server's system channel if the bot
# can talk there, otherwise the first text channel it can. None if it can't talk anywhere.
def find_welcome_channel(guild: discord.Guild) -> discord.TextChannel | None:
    me = guild.me
    candidates = [guild.system_channel] if guild.system_channel else []
    candidates += sorted(guild.text_channels, key=lambda c: c.position)
    for channel in candidates:
        if channel.permissions_for(me).send_messages:
            return channel
    return None

WELCOME_TEXT = (
    "🦧**Thanks for adding Lolroaster!**\n"
    "I can't see any channels currently. "
    "Hit **Set up** to choose a starting channel (or none yet), or run `/settings` anytime."
)

# DM version of the welcome buttons. The server's ID is baked into each button's custom_id so the
# bot knows which server it's about, even after a restart; main.py registers them with
# client.add_dynamic_items().
class DmSetupButton(discord.ui.DynamicItem[discord.ui.Button], template=r"lolroaster:dmsetup:(?P<guild_id>\d+)"):
    def __init__(self, guild_id: int):
        super().__init__(discord.ui.Button(
            label="Set up", style=discord.ButtonStyle.primary, emoji="🔥",
            custom_id=f"lolroaster:dmsetup:{guild_id}",
        ))
        self.guild_id = guild_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match) -> DmSetupButton:
        return cls(int(match["guild_id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        guild = interaction.client.get_guild(self.guild_id)
        if guild is None:
            await interaction.response.send_message("I'm not in that server anymore.")
            return
        await open_settings(interaction, guild)

class DmSkipButton(discord.ui.DynamicItem[discord.ui.Button], template=r"lolroaster:dmskip:(?P<guild_id>\d+)"):
    def __init__(self, guild_id: int):
        super().__init__(discord.ui.Button(
            label="Skip for now", style=discord.ButtonStyle.secondary,
            custom_id=f"lolroaster:dmskip:{guild_id}",
        ))
        self.guild_id = guild_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match) -> DmSkipButton:
        return cls(int(match["guild_id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            content="👋 No worries. Run `/settings` in the server anytime to set me up.",
            view=None,
        )

# Returns who added the bot to the server, from the audit log. Needs the View Audit Log
# permission; returns None without it (or if the entry can't be found).
async def find_inviter(guild: discord.Guild) -> discord.abc.User | None:
    if not guild.me.guild_permissions.view_audit_log:
        return None
    try:
        async for entry in guild.audit_logs(limit=10, action=discord.AuditLogAction.bot_add):
            if entry.target and entry.target.id == guild.me.id:
                return entry.user
    except discord.HTTPException:
        pass
    return None

# DMs the setup prompt to whoever added the bot, falling back to the server owner if the inviter
# can't be found or has DMs closed. Returns the user it reached, or None.
async def send_setup_dm(guild: discord.Guild) -> discord.abc.User | None:
    owner = guild.owner
    if owner is None:
        try:
            owner = await guild.fetch_member(guild.owner_id)
        except discord.HTTPException:
            pass
    recipients = []
    inviter = await find_inviter(guild)
    if inviter is not None:
        recipients.append(inviter)
    if owner is not None and all(r.id != owner.id for r in recipients):
        recipients.append(owner)

    view = discord.ui.View(timeout=None)
    view.add_item(DmSetupButton(guild.id))
    view.add_item(DmSkipButton(guild.id))
    text = (
        f"👋 **Thanks for adding Lolroaster to {guild.name}!**\n"
        "I couldn't post in any channel there (I'm probably missing the View Channels or Send Messages "
        "permission), so I'm messaging you instead. Hit **Set up** to choose where I'm allowed to roast "
        "people, or run `/settings` in the server anytime."
    )
    for user in recipients:
        try:
            await user.send(text, view=view)
            return user
        except discord.HTTPException:
            continue  # DMs closed, try the next person
    return None
