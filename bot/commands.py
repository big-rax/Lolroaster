import asyncio
import time
import discord
from discord import app_commands
from pyke import Continent, Pyke, exceptions, DataDragon
from bot.riot_api import get_account_info, get_champion_mastery, get_all_ranks, rank_sort_key, get_live_game, get_champion_name_map, get_latest_patch, build_mastery_banner
from bot.store import save_link, add_allowed_channel, remove_allowed_channel, get_allowed_channels, get_link, toggle_user_opt_in, get_all_links, is_user_opted_in
from bot.config import BASE_DIR


# Registers all slash commands with the Discord command tree.
# Takes the command tree, Riot API client, and DataDragon client as arguments.
def register_commands(tree: app_commands.CommandTree, api: Pyke, ddragon: DataDragon) -> None:
    @tree.command(name="ping", description="Replies with pong")
    async def ping(interaction: discord.Interaction) -> None:
        await interaction.response.send_message("pong (in python)")

    @tree.command(name="freaky", description="does something freaky")
    async def freaky(interaction: discord.Interaction) -> None:
        await interaction.response.send_message("😛😛😛lul")

    roast = app_commands.Group(name="roast", description="Roast related commands")
    riot = app_commands.Group(name="riot", description="Riot/League related commands")
    channel = app_commands.Group(name="channel", description="Channel management commands")

    #@tree.command(name"Track", description="Tracks a user")
    # Looks up a Riot account by game name and tag line, saves the link to the calling user's
    # Discord ID, and replies with an embed showing their level and Solo/Duo rank.
    @riot.command(name="link", description="Links your Riot account")
    async def riot_link(interaction: discord.Interaction, game_name: str, tag_line: str) -> None:
        await interaction.response.defer()

        info = await get_account_info(api, game_name, tag_line)

        if info is None:
            await interaction.followup.send(f"Couldn't find Riot account for {game_name}#{tag_line}. or some other shit broke idk just ping Baboondini")
            return

        save_link(
            discord_id=str(interaction.user.id),
            puuid=info["puuid"],
            game_name=info["gameName"],
            tag_line=info["tagLine"]
        )

        rank = info["rank"]
        rank_str = f"{rank['tier']} {rank['rank']} - {rank['leaguePoints']} LP" if rank else "Unranked"

        masteries, patch = await asyncio.gather(
            get_champion_mastery(api, ddragon, info["puuid"]),
            get_latest_patch()
        )

        embed = discord.Embed(title=f"{info['gameName']}#{info['tagLine']}", color=discord.Color.blue())
        embed.add_field(name="Level", value=str(info["summonerLevel"]), inline=True)
        embed.add_field(name="Solo/Duo Rank", value=rank_str, inline=True)
        embed.set_footer(text=f"Linked to {interaction.user.display_name}")

        if masteries and masteries[0].get("championName") == "Teemo":
            embed.add_field(name="", value="This user might be on a list...😈", inline=False)

        if masteries and len(masteries) >= 3:
            banner = await build_mastery_banner(masteries, patch)
            embed.set_image(url="attachment://mastery.png")
            await interaction.followup.send(embed=embed, file=discord.File(banner, "mastery.png"))
        else:
            import os
            cat = discord.File(os.path.join(BASE_DIR, "bot", "assets", "cat_laugh.png"), "cat_laugh.png")
            embed.set_image(url="attachment://cat_laugh.png")
            await interaction.followup.send(embed=embed, file=cat)

    # Fetches the top champion masteries for the calling user's linked Riot account
    # and displays them in an embed ordered by mastery points.
    @riot.command(name="mastery", description="Displays your top champion masteries")
    async def league_mastery(interaction: discord.Interaction) -> None:
        await interaction.response.defer()

        linked = get_link(str(interaction.user.id))
        if linked is None:
            await interaction.followup.send("You haven't linked a Riot account yet! Use /riot link first.")
            return

        masteries = await get_champion_mastery(api, ddragon, linked["puuid"])
        if masteries is None:
            await interaction.followup.send("Something went wrong fetching your mastery data.")
            return

        embed = discord.Embed(title="Top Champion Masteries", color=discord.Color.gold())
        for i, champ in enumerate(masteries):
            embed.add_field(
                name=f"#{i+1} {champ['championName']}",
                value=f"Points: {champ['championPoints']:,} | Level: {champ['championLevel']}",
                inline=False
            )
        embed.set_footer(text=f"{linked['game_name']}#{linked['tag_line']}")

        await interaction.followup.send(embed=embed)

    # Adds the current channel to the bot's allowed list so it can send messages and reactions there.
    @channel.command(name="set", description="Sets the channel in which the bot is allowed to message, react, etc.")
    async def set_channel(interaction: discord.Interaction) -> None:
        add_allowed_channel(str(interaction.channel_id), str(interaction.guild_id))
        await interaction.response.send_message(f"✅ Lolroaster will now react (roast) users in <#{interaction.channel_id}>")

    # Removes the current channel from the bot's allowed list.
    @channel.command(name="remove", description="Removes an allowed channel")
    async def removed_allowed_channel(interaction: discord.Interaction) -> None:
        remove_allowed_channel(str(interaction.channel_id))
        await interaction.response.send_message(f"😶‍🌫️ Lolroaster will no longer yap in <#{interaction.channel_id}>")

    # Lists all channels in the server that the bot is currently allowed to operate in.
    @channel.command(name="list", description="List all allowed channels in a server")
    async def list_channels(interaction: discord.Interaction) -> None:
        channels = get_allowed_channels(str(interaction.guild_id))
        if not channels:
            return interaction.response.send_message("There are no channels currently set, please use /channel set to add a channel!")
        channel_mentions = "\n".join([f"<#{cid}>" for cid in channels])
        await interaction.response.send_message(f"Allowed channels:{channel_mentions}")

    # Toggles the calling user's opt-in status for bot interactions (roasts, leaderboard, etc.).
    # Responds ephemerally so only the user sees the confirmation.
    @roast.command(name="toggle", description="Toggle whether the bot interacts with you")
    async def roast_toggle(interaction: discord.Interaction) -> None:
        opted_in = toggle_user_opt_in(str(interaction.user.id))
        if opted_in:
            await interaction.response.send_message("You will now be roasted (when the occasion calls for it)", ephemeral=True)
        else:
            await interaction.response.send_message("You will no longer be roasted... at least by me.", ephemeral=True)

    # Admin-only: toggles opt-in status for any server member selected via a user picker.
    # Blocked for non-admins. Responds ephemerally so only the admin sees the confirmation.
    @roast.command(name="toggle-user", description="(Admin) Toggle opt-in status for a specific user")
    async def toggle_user(interaction: discord.Interaction, user: discord.Member) -> None:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return
        opted_in = toggle_user_opt_in(str(user.id))
        if opted_in:
            await interaction.response.send_message(f"<@{user.id}> will now be opted in to all Lolroaster interactions.", ephemeral=True)
        else:
            await interaction.response.send_message(f"<@{user.id}> has been opted out.", ephemeral=True)

    QUEUE_NAMES = {
        420: "Ranked Solo/Duo", 440: "Ranked Flex", 450: "ARAM",
        400: "Normal Draft", 430: "Normal Blind", 0: "Custom",
    }

    def build_live_embed(game: dict, linked: dict, champ_map: dict) -> discord.Embed:
        queue_name = QUEUE_NAMES.get(game.get("gameQueueConfigId", 0), game.get("gameMode", "Unknown"))
        game_start_ms = game.get("gameStartTime", 0)
        elapsed = max(0, int(time.time() - game_start_ms / 1000)) if game_start_ms else game.get("gameLength", 0)
        time_str = f"{elapsed // 60}m {elapsed % 60}s" if elapsed > 0 else "Loading screen"

        blue = [p for p in game["participants"] if p["teamId"] == 100]
        red = [p for p in game["participants"] if p["teamId"] == 200]

        player_champ_id = next(
            (p["championId"] for p in game["participants"] if linked["puuid"] in p.get("puuid", "")),
            None
        )

        def fmt_team(players: list) -> str:
            lines = []
            for p in players:
                champ = champ_map.get(p["championId"], str(p["championId"])) if champ_map else str(p["championId"])
                name = p.get("riotId", p.get("summonerName", "Unknown"))
                lines.append(f"`{champ}`\n{name}")
            return "\n\n".join(lines)

        embed = discord.Embed(
            title=f"🔴 Live Game — {linked['game_name']}#{linked['tag_line']}",
            color=discord.Color.red()
        )
        embed.add_field(name="Queue", value=queue_name, inline=True)
        embed.add_field(name="Duration", value=time_str, inline=True)
        embed.add_field(name="​", value="​", inline=True)
        embed.add_field(name="🔵 Blue Team", value=fmt_team(blue), inline=True)
        embed.add_field(name="🔴 Red Team", value=fmt_team(red), inline=True)

        if player_champ_id and champ_map:
            champ_name = champ_map.get(player_champ_id, "")
            if champ_name:
                embed.set_thumbnail(url=f"https://ddragon.leagueoflegends.com/cdn/15.1.1/img/champion/{champ_name}.png")

        embed.set_footer(text="🔄 Last updated")
        embed.timestamp = discord.utils.utcnow()

        return embed

    active_live_views: dict[str, "LiveGameView"] = {}

    class LiveGameView(discord.ui.View):
        def __init__(self, linked: dict):
            super().__init__(timeout=None)
            self.linked = linked
            self.message: discord.Message | None = None
            self._poll_task: asyncio.Task | None = None

            name_tag = f"{linked['game_name']}-{linked['tag_line']}".replace(" ", "%20")
            self.add_item(discord.ui.Button(
                label="Porofessor",
                emoji="📊",
                style=discord.ButtonStyle.link,
                url=f"https://porofessor.gg/live/na/{name_tag}"
            ))

        def start_polling(self) -> None:
            self._poll_task = asyncio.create_task(self._poll_loop())

        async def _poll_loop(self) -> None:
            while True:
                await asyncio.sleep(60)
                if self.message is None:
                    break
                game = await get_live_game(api, self.linked["puuid"])
                if game is None:
                    embed = discord.Embed(
                        title=f"⬛ Game Over — {self.linked['game_name']}#{self.linked['tag_line']}",
                        description="The game has ended.",
                        color=discord.Color.dark_gray()
                    )
                    for child in self.children:
                        if isinstance(child, discord.ui.Button) and child.style != discord.ButtonStyle.link:
                            child.disabled = True
                    try:
                        await self.message.edit(embed=embed, view=self)
                    except (discord.NotFound, discord.HTTPException):
                        pass
                    discord.ui.View.stop(self)
                    active_live_views.pop(self.linked["puuid"], None)
                    break
                else:
                    champ_map = await get_champion_name_map()
                    embed = build_live_embed(game, self.linked, champ_map)
                    try:
                        await self.message.edit(embed=embed, view=self)
                    except (discord.NotFound, discord.HTTPException):
                        break

        async def disable(self) -> None:
            if self._poll_task and not self._poll_task.done():
                self._poll_task.cancel()
            discord.ui.View.stop(self)
            active_live_views.pop(self.linked["puuid"], None)
            if self.message:
                try:
                    await self.message.delete()
                except (discord.NotFound, discord.HTTPException):
                    pass

        @discord.ui.button(label="Refresh", emoji="🔄", style=discord.ButtonStyle.primary)
        async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
            await interaction.response.defer()
            game = await get_live_game(api, self.linked["puuid"])
            if game is None:
                await self.disable()
                await interaction.followup.send("Game has ended.", ephemeral=True)
                return
            champ_map = await get_champion_name_map()
            embed = build_live_embed(game, self.linked, champ_map)
            await interaction.edit_original_response(embed=embed, view=self)

        @discord.ui.button(label="Stop Watching", emoji="⛔", style=discord.ButtonStyle.danger)
        async def stop_watching(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
            await interaction.response.defer(ephemeral=True)
            await self.disable()

    async def _start_live_tracking(interaction: discord.Interaction, target: discord.Member) -> None:
        linked = get_link(str(target.id))
        if linked is None:
            noun = "You haven't" if target.id == interaction.user.id else f"{target.display_name} hasn't"
            await interaction.followup.send(f"{noun} linked a Riot account yet.", ephemeral=True)
            return

        game = await get_live_game(api, linked["puuid"])
        if game is None:
            noun = "You're" if target.id == interaction.user.id else f"{target.display_name} is"
            await interaction.followup.send(f"{noun} not currently in a game.", ephemeral=True)
            return

        existing = active_live_views.pop(linked["puuid"], None)
        if existing:
            await existing.disable()

        champ_map = await get_champion_name_map()
        embed = build_live_embed(game, linked, champ_map)
        view = LiveGameView(linked)
        active_live_views[linked["puuid"]] = view
        view.message = await interaction.channel.send(embed=embed, view=view)
        view.start_polling()

    class LiveUserSelectView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=60)

        @discord.ui.select(cls=discord.ui.UserSelect, placeholder="Choose a player to track...")
        async def user_select(self, interaction: discord.Interaction, select: discord.ui.UserSelect) -> None:
            target = select.values[0]
            await interaction.response.edit_message(content=f"Checking {target.display_name}'s game...", view=None)
            await _start_live_tracking(interaction, target)

    class LiveModeView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=60)

        @discord.ui.select(
            placeholder="Who do you want to track?",
            options=[
                discord.SelectOption(label="Myself", value="self", emoji="😏"),
                discord.SelectOption(label="Another player", value="target", emoji="🫃"),
            ]
        )
        async def mode_select(self, interaction: discord.Interaction, select: discord.ui.Select) -> None:
            if select.values[0] == "self":
                await interaction.response.edit_message(content="Checking your game...", view=None)
                await _start_live_tracking(interaction, interaction.user)
            else:
                await interaction.response.edit_message(content="Select a player to track:", view=LiveUserSelectView())

    # Shows an ephemeral prompt to choose between tracking yourself or another player.
    # Auto-updates the public game embed every 60 seconds and detects when the game ends.
    @roast.command(name="live", description="Track a live game — yours or another player's")
    async def live(interaction: discord.Interaction) -> None:
        await interaction.response.send_message("Who do you want to track?", view=LiveModeView(), ephemeral=True)

    # Displays the calling user's currently linked Riot account and their Solo/Duo and Flex ranks.
    # Uses Components V2 layout with a container, section header, rank blocks, and footer.
    # Notifies the user if they haven't linked an account yet.
    @riot.command(name="account", description="Displays your currently linked Riot account")
    async def account(interaction: discord.Interaction) -> None:
        try:
            await interaction.response.defer()

            linked = get_link(str(interaction.user.id))
            if linked is None:
                await interaction.followup.send("You don't have a linked Riot account. Use /riot link to link one!")
                return

            ranks, masteries, patch = await asyncio.gather(
                get_all_ranks(api, linked["puuid"]),
                get_champion_mastery(api, ddragon, linked["puuid"]),
                get_latest_patch()
            )
            solo = ranks["solo"]
            flex = ranks["flex"]

            def rank_str(entry: dict | None) -> str:
                if not entry:
                    return "Unranked"
                return f"{entry['tier'].capitalize()} {entry['rank']} — {entry['leaguePoints']:,} LP"

            def rank_emoji(entry: dict | None) -> str:
                if not entry:
                    return "⬜"
                icons = {
                    "iron": "<:7574iron:1517989092288233513>",
                    "bronze": "<:1184bronze:1517989087674368171>",
                    "silver": "<:7455silver:1517989093135355954>",
                    "gold": "<:1053gold:1517989094473470013>",
                    "platinum": "<:3978platinum:1517989095794806804>",
                    "emerald": "💚",
                    "diamond": "<:1053diamond:1517989089847017674>",
                    "master": "<:9231master:1517989091436658919>",
                    "grandmaster": "<:9476grandmaster:1517989098285961216>",
                    "challenger": "<:9476challenger:1517989097094910092>",
                }
                return icons.get(entry["tier"].lower(), "⬜")

            summoner_name = f"{linked['game_name']}#{linked['tag_line']}"

            container = discord.ui.Container(accent_colour=discord.Colour.blue())

            header = discord.ui.Section(
                discord.ui.TextDisplay(f"# {summoner_name}"),
                accessory=discord.ui.Thumbnail(
                    media=interaction.user.display_avatar.url,
                    description=interaction.user.display_name
                )
            )

            container.add_item(header)
            container.add_item(discord.ui.Separator())
            container.add_item(discord.ui.TextDisplay(f"**Solo/Duo** {rank_emoji(solo)}\n{rank_str(solo)}"))
            container.add_item(discord.ui.TextDisplay(f"**Flex** {rank_emoji(flex)}\n{rank_str(flex)}"))
            container.add_item(discord.ui.Separator())
            container.add_item(discord.ui.TextDisplay(f"-# Linked to {interaction.user.display_name}"))

            files = []
            if masteries and len(masteries) >= 3:
                banner = await build_mastery_banner(masteries, patch)
                banner_file = discord.File(banner, "mastery.png")
                files.append(banner_file)
                container.add_item(discord.ui.Separator())
                container.add_item(discord.ui.MediaGallery(
                    discord.MediaGalleryItem(media=discord.UnfurledMediaItem("attachment://mastery.png"))
                ))

            if masteries and masteries[0].get("championName") == "Teemo":
                container.add_item(discord.ui.TextDisplay("This user might be on a list...😈"))

            layout = discord.ui.LayoutView()
            layout.add_item(container)
            await interaction.followup.send(view=layout, files=files)

        except Exception as e:
            import traceback
            traceback.print_exc()
            await interaction.followup.send(content=str(e))

    # Builds and sends a leaderboard embed for all opted-in users who have linked Riot accounts.
    # Fetches Solo/Duo and Flex ranks for each user, sorts by rank, and displays them with
    # tier/division emojis and LP. Ranked players are shown above a separator from unranked ones.
    # Embed color reflects the highest-ranked Solo/Duo player's tier.
    @riot.command(name="leaderboard", description="Shows the server's ranked leaderboard")
    async def leaderboard(interaction: discord.Interaction) -> None:
        try:
            await interaction.response.defer()
        except discord.NotFound:
            return

        try:
            links = get_all_links()
            if not links:
                await interaction.followup.send("No one has linked their account yet! Use /riot_link first.")
                return

            TIER_EMOJI = {
                "iron": "<:7574iron:1517989092288233513>",
                "bronze": "<:1184bronze:1517989087674368171>",
                "silver": "<:7455silver:1517989093135355954>",
                "gold": "<:1053gold:1517989094473470013>",
                "platinum": "<:3978platinum:1517989095794806804>",
                "emerald": "💚",
                "diamond": "<:1053diamond:1517989089847017674>",
                "master": "<:9231master:1517989091436658919>",
                "grandmaster": "<:9476grandmaster:1517989098285961216>",
                "challenger": "<:9476challenger:1517989097094910092>",
            }
            DIVISION_EMOJI = {"I": "👑", "II": "🫃", "III": "🤪", "IV": "💀"}
            TIERED = {"iron", "bronze", "silver", "gold", "platinum", "emerald", "diamond"}
            TIER_COLOR = {
                "iron": 0x8A7066, "bronze": 0xA05000, "silver": 0xA8B4C0,
                "gold": 0xC89B3C, "platinum": 0x007B6C, "emerald": 0x009B57,
                "diamond": 0x576BCE, "master": 0x9B4BC8, "grandmaster": 0xC8342B,
                "challenger": 0xF4C874,
            }

            player_entries = []
            for link in links:
                if not is_user_opted_in(link["discord_id"]):
                    continue

                member = interaction.guild.get_member(int(link["discord_id"]))
                if member is None:
                    try:
                        member = await interaction.guild.fetch_member(int(link["discord_id"]))
                    except discord.NotFound:
                        continue

                ranks = await get_all_ranks(api, link["puuid"])
                player_entries.append({
                    "display_name": member.display_name,
                    "riot_name": f"{link['game_name']}#{link['tag_line']}",
                    "solo": ranks["solo"],
                    "flex": ranks["flex"],
                })

            player_entries.sort(
                key=lambda p: (rank_sort_key(p["solo"]), rank_sort_key(p["flex"])),
                reverse=True
            )

            def fmt_rank(entry: dict | None) -> str:
                if not entry or "tier" not in entry:
                    return "Unranked"
                tier_lower = entry["tier"].lower()
                div_emoji = DIVISION_EMOJI.get(entry["rank"], "") if tier_lower in TIERED else ""
                return f"{entry['tier'].capitalize()} {entry['rank']} {div_emoji} {entry['leaguePoints']:,} LP"

            def format_player(i: int, p: dict) -> str:
                solo_ranked = p["solo"] and "tier" in p["solo"]
                best = p["solo"] if solo_ranked else p["flex"]
                tier_emoji = TIER_EMOJI.get(best["tier"].lower(), "")
                medal = ["🥇", "🥈", "🥉"][i] if i < 3 else f"`{i+1}.`"
                header = f"{medal} {tier_emoji} **{p['display_name']}** ({p['riot_name']})"
                stats = f"-# Solo: {fmt_rank(p['solo'])}  ·  Flex: {fmt_rank(p['flex'])}"
                return f"{header}\n{stats}"

            ranked = [p for p in player_entries if (p["solo"] and "tier" in p["solo"]) or (p["flex"] and "tier" in p["flex"])]
            unranked = [p for p in player_entries if p not in ranked]

            lines = [format_player(i, p) for i, p in enumerate(ranked)]
            if ranked and unranked:
                lines.append("───────────────\n**Grass Touchers**")
            for p in unranked:
                lines.append(f"-# **{p['display_name']}** ({p['riot_name']}) — Unranked")

            top_tier = None
            if ranked:
                best = ranked[0]["solo"] if (ranked[0]["solo"] and "tier" in ranked[0]["solo"]) else ranked[0]["flex"]
                if best and "tier" in best:
                    top_tier = best["tier"].lower()
            embed_color = discord.Color(TIER_COLOR[top_tier]) if top_tier else discord.Color.fuchsia()

            embed = discord.Embed(title="🏆 Server Leaderboard", color=embed_color)
            embed.add_field(name="Rankings", value="\n".join(lines) or "No players yet.", inline=False)
            embed.set_footer(text=f"Requested by {interaction.user.display_name}")

            await interaction.followup.send(embed=embed)

        except Exception:
            import traceback
            traceback.print_exc()
            try:
                await interaction.followup.send(content="Something went wrong building the leaderboard.", ephemeral=True)
            except Exception:
                pass

    tree.add_command(roast)
    tree.add_command(riot)
    tree.add_command(channel)
