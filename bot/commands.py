from __future__ import annotations
import asyncio
import random
import time
import discord
from discord import app_commands
from pyke import Continent, Pyke, exceptions, DataDragon
from bot.riot_api import get_account_info, riot_error_message, clean_riot_id_part, get_champion_mastery, get_all_ranks, rank_sort_key, get_live_game, get_match_result, get_champion_name_map, get_latest_patch, build_mastery_banner
from bot.store import save_link, get_allowed_channels, get_link, toggle_user_opt_in, get_all_links, is_user_opted_in, save_steam_link, delete_steam_link, set_ping_channel
from bot.steam import resolve_steam_id, get_profile, get_owned_games
from bot.config import BASE_DIR, WORDLE_BOT_ID
from bot.wordle import is_wordle_summary, wordle_number_for, wordle_date, build_wordle_roasts
from bot.activities import (
    MAX_GAME_NAME, MAX_GAMES_PER_SERVER, MAX_MESSAGE,
    add_game, added_games, is_default, remove_game, resolve_game_name, suggest_game_names, tracked_games,
)
from bot.data import FREAKY_GIFS
from bot.settings_ui import open_settings
from bot.help import register_help


# Registers all slash commands with the Discord command tree.
# Takes the command tree, Riot API client, and DataDragon client as arguments.
def register_commands(tree: app_commands.CommandTree, api: Pyke, ddragon: DataDragon) -> None:
    @tree.command(name="ping", description="Replies with pong")
    async def ping(interaction: discord.Interaction) -> None:
        await interaction.response.send_message("pong (in python)")

    @tree.command(name="freaky", description="does something freaky")
    async def freaky(interaction: discord.Interaction) -> None:
        # Falls back to the old text reply until FREAKY_GIFS has links in it
        message = random.choice(FREAKY_GIFS) if FREAKY_GIFS else "whoops something broke, go @brax"
        await interaction.response.send_message(message)

    roast = app_commands.Group(name="roast", description="Roast related commands")
    lol = app_commands.Group(name="lol", description="League of Legends: accounts, ranks and games")
    # Explicit False is needed: guild_only alone leaves DMs/group chats unset, which inherit the tree's default of allowed
    SERVER_ONLY = app_commands.AppCommandContext(guild=True, dm_channel=False, private_channel=False)
    channel = app_commands.Group(name="channel", description="Channel management commands", allowed_contexts=SERVER_ONLY)

    # Subcommands can't be restricted to servers on their own, so server-dependent ones check this at runtime.
    # interaction.guild is only set when the bot itself is in the server (not for user installs elsewhere).
    async def _require_bot_guild(interaction: discord.Interaction) -> bool:
        if interaction.guild is not None:
            return True
        await interaction.response.send_message("This command only works in a server I've been added to.", ephemeral=True)
        return False

    #@tree.command(name"Track", description="Tracks a user")
    # Looks up a Riot account by game name and tag line, saves the link to the calling user's
    # Discord ID, and replies with an embed showing their level and Solo/Duo rank.
    @lol.command(name="link", description="Links your Riot account")
    async def riot_link(interaction: discord.Interaction, game_name: str, tag_line: str) -> None:
        await interaction.response.defer()

        try:
            info = await get_account_info(api, game_name, tag_line)
        except Exception as e:
            print(f"Riot API ERROR: {e}", flush=True)
            riot_id = f"{clean_riot_id_part(game_name)}#{clean_riot_id_part(tag_line)}"
            await interaction.followup.send(riot_error_message(e, riot_id))
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
    @lol.command(name="mastery", description="Displays your top champion masteries")
    async def league_mastery(interaction: discord.Interaction) -> None:
        await interaction.response.defer()

        linked = get_link(str(interaction.user.id))
        if linked is None:
            await interaction.followup.send("You haven't linked a Riot account yet! Use /lol link first.")
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

    # Lists all channels in the server that the bot is currently allowed to operate in.
    @channel.command(name="list", description="List all allowed channels in a server")
    async def list_channels(interaction: discord.Interaction) -> None:
        channels = get_allowed_channels(str(interaction.guild_id))
        if not channels:
            return await interaction.response.send_message("There are no channels currently set, use /settings to choose some!")
        channel_mentions = "\n".join([f"<#{cid}>" for cid in channels])
        await interaction.response.send_message(f"Allowed channels:{channel_mentions}")

    # Admin-only: walks through turning the bot on/off for the server and choosing its channels.
    @tree.command(name="settings", description="(Admin) Turn the bot on/off for this server and choose its channels")
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @app_commands.default_permissions(manage_guild=True)
    async def settings(interaction: discord.Interaction) -> None:
        await open_settings(interaction)

    # Toggles the calling user's opt-in status for bot interactions (roasts, leaderboard, etc.).
    # Responds ephemerally so only the user sees the confirmation.
    @roast.command(name="toggle", description="Toggle whether the bot interacts with you")
    async def roast_toggle(interaction: discord.Interaction) -> None:
        opted_in = toggle_user_opt_in(str(interaction.user.id))
        if opted_in:
            await interaction.response.send_message("You will now be roasted (when the occasion calls for it)", ephemeral=True)
        else:
            await interaction.response.send_message("You will no longer be roasted... at least by me.", ephemeral=True)

    # Admin-only: opts a server member out of bot interactions. Opt-in is global across servers,
    # so admins can only opt people out; opting in stays the user's own choice via /roast toggle.
    # Responds ephemerally so only the admin sees the confirmation.
    @roast.command(name="toggle-user", description="(Admin) Opt a specific user out of Lolroaster interactions")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def toggle_user(interaction: discord.Interaction, user: discord.Member) -> None:
        if not await _require_bot_guild(interaction):
            return
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return
        if not is_user_opted_in(str(user.id)):
            await interaction.response.send_message(f"<@{user.id}> isn't opted in. Users opt in themselves with /roast toggle.", ephemeral=True)
            return
        toggle_user_opt_in(str(user.id))
        await interaction.response.send_message(f"<@{user.id}> has been opted out.", ephemeral=True)

    QUEUE_NAMES = {
        420: "Ranked Solo/Duo", 440: "Ranked Flex", 450: "ARAM",
        400: "Normal Draft", 430: "Normal Blind", 0: "Custom",
        900: "URF", 1900: "URF", 1020: "One for All",
        1300: "Nexus Blitz", 1700: "Arena", 1900: "URF",
    }
    GAME_MODE_NAMES = {
        "KIWI": "ARAM Mayhem", "CHERRY": "Arena", "URF": "URF",
        "ONEFORALL": "One for All", "NEXUSBLITZ": "Nexus Blitz",
        "ULTBOOK": "Ultimate Spellbook", "TUTORIAL": "Tutorial",
    }

    def build_live_embed(game: dict, linked: dict, champ_map: dict, patch: str = "15.1.1") -> discord.Embed:
        raw_mode = game.get("gameMode", "Unknown")
        queue_name = QUEUE_NAMES.get(
            game.get("gameQueueConfigId", 0),
            GAME_MODE_NAMES.get(raw_mode, raw_mode)
        )
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
                embed.set_thumbnail(url=f"https://ddragon.leagueoflegends.com/cdn/{patch}/img/champion/{champ_name}.png")

        embed.set_footer(text="🔄 Last updated")
        embed.timestamp = discord.utils.utcnow()

        return embed

    # Returns True if the caller may post the target's games publicly: themselves always,
    # anyone else only if that person has opted in. Tells the caller why when it's blocked.
    async def _target_allowed(interaction: discord.Interaction, target: discord.Member) -> bool:
        if target.id == interaction.user.id or is_user_opted_in(str(target.id)):
            return True
        await interaction.followup.send(f"{target.display_name} hasn't opted in to Lolroaster, so I can't show their games.", ephemeral=True)
        return False

    active_live_views: dict[str, "LiveGameView"] = {}
    LIVE_EDIT_WINDOW = 13 * 60  # stay safely inside the 15-minute interaction token lifetime

    class LiveGameView(discord.ui.View):
        def __init__(self, linked: dict):
            super().__init__(timeout=None)
            self.linked = linked
            self.message: discord.Message | None = None
            self._poll_task: asyncio.Task | None = None
            self.game_id: int | None = None
            self.patch: str = "15.1.1"
            # Outside servers the bot is in, the message can only be edited through the interaction
            # token, which expires after 15 minutes. None means no limit.
            self.edit_deadline: float | None = None

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
                if self.edit_deadline is not None and time.monotonic() > self.edit_deadline:
                    embed = self.message.embeds[0] if self.message.embeds else discord.Embed()
                    embed.set_footer(text="Auto-updates paused (Discord's 15 min limit outside servers). Press Refresh to resume.")
                    try:
                        await self.message.edit(embed=embed, view=self)
                    except (discord.NotFound, discord.HTTPException):
                        pass
                    break
                game = await get_live_game(api, self.linked["puuid"])
                if game is None:
                    for child in self.children:
                        if isinstance(child, discord.ui.Button) and child.style != discord.ButtonStyle.link:
                            child.disabled = True
                    discord.ui.View.stop(self)
                    active_live_views.pop(self.linked["puuid"], None)

                    pending = discord.Embed(
                        title=f"⬛ Game Over — {self.linked['game_name']}#{self.linked['tag_line']}",
                        description="Fetching result...",
                        color=discord.Color.dark_gray()
                    )
                    try:
                        await self.message.edit(embed=pending, view=self)
                    except (discord.NotFound, discord.HTTPException):
                        break

                    result = None
                    for _ in range(5):
                        await asyncio.sleep(60)
                        result = await get_match_result(api, self.linked["puuid"], self.game_id)
                        if result:
                            break

                    if result:
                        color = discord.Color.green() if result["win"] else discord.Color.red()
                        icon = "<:73494mogger:1522030305647788173>" if result["win"] else "<:50009catlaughing:1522030042044174396>"
                        outcome = "Victory" if result["win"] else "Defeat"
                        embed = discord.Embed(
                            title=f"{icon} {outcome} — {self.linked['game_name']}#{self.linked['tag_line']}",
                            color=color
                        )
                        embed.set_thumbnail(url=f"https://ddragon.leagueoflegends.com/cdn/{self.patch}/img/champion/{result['championName']}.png")
                        embed.add_field(name="Champion", value=result["championName"], inline=True)
                        embed.add_field(name="KDA", value=f"{result['kills']}/{result['deaths']}/{result['assists']}", inline=True)
                        mins, secs = divmod(result["gameDuration"], 60)
                        embed.add_field(name="Duration", value=f"{mins}m {secs}s", inline=True)
                    else:
                        embed = discord.Embed(
                            title=f"⬛ Game Over — {self.linked['game_name']}#{self.linked['tag_line']}",
                            description="The game has ended.",
                            color=discord.Color.dark_gray()
                        )
                    try:
                        await self.message.edit(embed=embed, view=self)
                    except (discord.NotFound, discord.HTTPException):
                        pass
                    break
                else:
                    if self.game_id is None:
                        self.game_id = game.get("gameId")
                    champ_map = await get_champion_name_map()
                    embed = build_live_embed(game, self.linked, champ_map, self.patch)
                    try:
                        await self.message.edit(embed=embed, view=self)
                    except (discord.NotFound, discord.HTTPException):
                        break

        async def disable(self, delete: bool = True) -> None:
            if self._poll_task and not self._poll_task.done():
                self._poll_task.cancel()
            discord.ui.View.stop(self)
            active_live_views.pop(self.linked["puuid"], None)
            if delete and self.message:
                try:
                    await self.message.delete()
                except (discord.NotFound, discord.HTTPException):
                    pass

        @discord.ui.button(label="Refresh", emoji="🔄", style=discord.ButtonStyle.primary)
        async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
            await interaction.response.defer()
            game = await get_live_game(api, self.linked["puuid"])
            if game is None:
                await self.disable(delete=False)
                await interaction.delete_original_response()
                await interaction.followup.send("Game has ended.")
                return
            champ_map = await get_champion_name_map()
            embed = build_live_embed(game, self.linked, champ_map, self.patch)
            await interaction.edit_original_response(embed=embed, view=self)
            if self.edit_deadline is not None:
                # The button press gives a fresh token, so hand it to the poller for another 15 minutes
                self.message = await interaction.original_response()
                self.edit_deadline = time.monotonic() + LIVE_EDIT_WINDOW
                if self._poll_task is None or self._poll_task.done():
                    self.start_polling()

        @discord.ui.button(label="Stop Watching", emoji="⛔", style=discord.ButtonStyle.danger)
        async def stop_watching(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
            await interaction.response.defer()
            await self.disable(delete=False)
            # Deleting through this interaction works even where the bot can't access the channel
            await interaction.delete_original_response()

    async def _start_live_tracking(interaction: discord.Interaction, target: discord.Member) -> None:
        if not await _target_allowed(interaction, target):
            return
        linked = get_link(str(target.id))
        if linked is None:
            noun = "You haven't" if target.id == interaction.user.id else f"{target.display_name} hasn't"
            await interaction.followup.send(f"{noun} linked a Riot account yet.")
            return

        game = await get_live_game(api, linked["puuid"])
        if game is None:
            noun = "You're" if target.id == interaction.user.id else f"{target.display_name} is"
            await interaction.followup.send(f"{noun} not currently in a game.")
            return

        existing = active_live_views.pop(linked["puuid"], None)
        if existing:
            await existing.disable()

        champ_map, patch = await asyncio.gather(get_champion_name_map(), get_latest_patch())
        embed = build_live_embed(game, linked, champ_map, patch)
        view = LiveGameView(linked)
        view.patch = patch
        active_live_views[linked["puuid"]] = view
        if interaction.guild is not None:
            view.message = await interaction.channel.send(embed=embed, view=view)
        else:
            # DMs, group chats, or servers the bot isn't in: the bot can't post to the channel directly
            view.message = await interaction.followup.send(embed=embed, view=view, wait=True)
            view.edit_deadline = time.monotonic() + LIVE_EDIT_WINDOW
        view.start_polling()

    class LiveUserSelectView(discord.ui.View):
        def __init__(self, owner_id: int):
            super().__init__(timeout=60)
            self.owner_id = owner_id

        # Only the person who ran /lol live can use this picker
        async def interaction_check(self, interaction: discord.Interaction) -> bool:
            if interaction.user.id == self.owner_id:
                return True
            await interaction.response.send_message("This isn't your menu. Run /lol live yourself.", ephemeral=True)
            return False

        @discord.ui.select(cls=discord.ui.UserSelect, placeholder="Choose a player to track...")
        async def user_select(self, interaction: discord.Interaction, select: discord.ui.UserSelect) -> None:
            target = select.values[0]
            await interaction.response.edit_message(content=f"Checking {target.display_name}'s game...", view=None)
            await _start_live_tracking(interaction, target)

    class LiveModeView(discord.ui.View):
        def __init__(self, owner_id: int):
            super().__init__(timeout=60)
            self.owner_id = owner_id

        # Only the person who ran /lol live can use this picker
        async def interaction_check(self, interaction: discord.Interaction) -> bool:
            if interaction.user.id == self.owner_id:
                return True
            await interaction.response.send_message("This isn't your menu. Run /lol live yourself.", ephemeral=True)
            return False

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
                await interaction.response.edit_message(content="Select a player to track:", view=LiveUserSelectView(self.owner_id))

    # Shows a prompt to choose between tracking yourself or another player.
    # Auto-updates the public game embed every 60 seconds and detects when the game ends.
    @lol.command(name="live", description="Track a live game — yours or another player's")
    async def live(interaction: discord.Interaction) -> None:
        await interaction.response.send_message("Who do you want to track?", view=LiveModeView(interaction.user.id))

    async def _show_last_game(interaction: discord.Interaction, target: discord.Member) -> None:
        if not await _target_allowed(interaction, target):
            return
        linked = get_link(str(target.id))
        if linked is None:
            noun = "You haven't" if target.id == interaction.user.id else f"{target.display_name} hasn't"
            await interaction.followup.send(f"{noun} linked a Riot account yet.", ephemeral=True)
            return

        result, patch = await asyncio.gather(
            get_match_result(api, linked["puuid"]),
            get_latest_patch()
        )
        if result is None:
            await interaction.followup.send("Couldn't find a recent game.", ephemeral=True)
            return

        color = discord.Color.green() if result["win"] else discord.Color.red()
        icon = "<:73494mogger:1522030305647788173>" if result["win"] else "<:50009catlaughing:1522030042044174396>"
        outcome = "Victory" if result["win"] else "Defeat"
        embed = discord.Embed(
            title=f"{icon} {outcome} — {linked['game_name']}#{linked['tag_line']}",
            color=color
        )
        embed.set_thumbnail(url=f"https://ddragon.leagueoflegends.com/cdn/{patch}/img/champion/{result['championName']}.png")
        embed.add_field(name="Champion", value=result["championName"], inline=True)
        embed.add_field(name="KDA", value=f"{result['kills']}/{result['deaths']}/{result['assists']}", inline=True)
        mins, secs = divmod(result["gameDuration"], 60)
        embed.add_field(name="Duration", value=f"{mins}m {secs}s", inline=True)
        await interaction.followup.send(embed=embed)

    class LastGameUserSelectView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=60)

        @discord.ui.select(cls=discord.ui.UserSelect, placeholder="Choose a player...")
        async def user_select(self, interaction: discord.Interaction, select: discord.ui.UserSelect) -> None:
            target = select.values[0]
            await interaction.response.edit_message(content=f"Fetching {target.display_name}'s last game...", view=None)
            await _show_last_game(interaction, target)

    class LastGameModeView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=60)

        @discord.ui.select(
            placeholder="Whose last game?",
            options=[
                discord.SelectOption(label="Mine", value="self", emoji="🤓"),
                discord.SelectOption(label="Another player", value="target", emoji="🫃"),
            ]
        )
        async def mode_select(self, interaction: discord.Interaction, select: discord.ui.Select) -> None:
            if select.values[0] == "self":
                await interaction.response.edit_message(content="Fetching your last game...", view=None)
                await _show_last_game(interaction, interaction.user)
            else:
                await interaction.response.edit_message(content="Select a player:", view=LastGameUserSelectView())

    # Fetches and displays the most recent match for the selected player.
    @lol.command(name="lastgame", description="Show the last game you or another player played")
    async def lastgame(interaction: discord.Interaction) -> None:
        await interaction.response.send_message("Whose last game?", view=LastGameModeView(), ephemeral=True)

    WORDLE_SEARCH_LIMIT = 200

    # Returns the Wordle bot's group summaries in this channel, newest first.
    async def _find_wordle_summaries(channel: discord.abc.Messageable) -> list[discord.Message]:
        summaries = []
        try:
            async for message in channel.history(limit=WORDLE_SEARCH_LIMIT):
                if message.author.id == WORDLE_BOT_ID and is_wordle_summary(message.content):
                    summaries.append(message)
        except (discord.Forbidden, discord.HTTPException):
            pass
        return summaries

    # Re-runs the Wordle roast on a past group summary in this channel. Defaults to the most recent one.
    @roast.command(name="wordle", description="Roast the players from a Wordle result")
    @app_commands.describe(number="Wordle number (defaults to the most recent result)")
    async def roast_wordle(interaction: discord.Interaction, number: int | None = None) -> None:
        if not await _require_bot_guild(interaction):
            return
        await interaction.response.defer()

        summaries = await _find_wordle_summaries(interaction.channel)
        if number is not None:
            summaries = [m for m in summaries if wordle_number_for(m) == number]
        if not summaries:
            which = f"Wordle No. {number}" if number is not None else "a Wordle result"
            await interaction.followup.send(
                f"Couldn't find {which} in the last {WORDLE_SEARCH_LIMIT} messages here.", ephemeral=True
            )
            return

        summary = summaries[0]
        roasts = build_wordle_roasts(summary.content)
        if not roasts:
            await interaction.followup.send("Nobody in that result is opted in to roasts.", ephemeral=True)
            return

        header = f"**Wordle No. {wordle_number_for(summary)}** ({summary.jump_url})"
        await interaction.followup.send("\n".join([header, *roasts]))

    @roast_wordle.autocomplete("number")
    async def roast_wordle_number_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[int]]:
        if interaction.guild is None:
            return []
        choices = []
        for message in await _find_wordle_summaries(interaction.channel):
            n = wordle_number_for(message)
            if current and not str(n).startswith(current):
                continue
            d = wordle_date(n)
            choices.append(app_commands.Choice(name=f"No. {n} ({d:%b} {d.day})", value=n))
        return choices[:25]

    game = app_commands.Group(name="game", description="Choose which games get people roasted", parent=roast)

    # Adds a game (any Discord activity) that pings opted-in players when they start it.
    @game.command(name="add", description="Roast people when they start playing a game")
    @app_commands.describe(
        name="The game's name exactly as Discord shows it (suggestions are what people are playing now)",
        message="(Optional) What to say after the @mention, e.g. \"is coding 🤓\" ",
    )
    async def game_add(
        interaction: discord.Interaction,
        name: app_commands.Range[str, 1, MAX_GAME_NAME],
        message: app_commands.Range[str, 1, MAX_MESSAGE] | None = None,
    ) -> None:
        if not await _require_bot_guild(interaction):
            return
        resolved = resolve_game_name(interaction.guild, name)
        if resolved is None:
            await interaction.response.send_message(
                f"Discord doesn't recognize **{name.strip()}** as a game, and nobody here has played it. "
                "Pick one from the suggestions.",
                ephemeral=True,
            )
            return
        name = resolved
        if name.lower() in tracked_games(interaction.guild_id):
            await interaction.response.send_message(f"**{name}** is already being tracked.", ephemeral=True)
            return
        if len(added_games(interaction.guild_id)) >= MAX_GAMES_PER_SERVER:
            await interaction.response.send_message(
                f"This server already tracks {MAX_GAMES_PER_SERVER} games. Remove one first.", ephemeral=True
            )
            return
        if not add_game(interaction.guild_id, name, message, interaction.user.id):
            await interaction.response.send_message(f"**{name}** is already being tracked.", ephemeral=True)
            return
        preview = f"{interaction.user.mention} {tracked_games(interaction.guild_id)[name.lower()][1]}"
        await interaction.response.send_message(
            f"Now tracking **{name}**. Opted-in players will get: {preview}",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @game_add.autocomplete("name")
    async def game_add_name_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        if interaction.guild is None:
            return []
        names = suggest_game_names(interaction.guild, current, exclude=set(tracked_games(interaction.guild.id)))
        return [app_commands.Choice(name=n, value=n) for n in names if len(n) <= MAX_GAME_NAME]

    @game.command(name="remove", description="Stop roasting people for a game")
    @app_commands.describe(name="A game added with /roast game add")
    async def game_remove(interaction: discord.Interaction, name: str) -> None:
        if not await _require_bot_guild(interaction):
            return
        if is_default(name):
            await interaction.response.send_message(f"**{name}** is a default game and can't be removed.", ephemeral=True)
            return
        display = added_games(interaction.guild_id).get(name.lower(), (name, None))[0]
        if not remove_game(interaction.guild_id, name):
            await interaction.response.send_message(f"**{name}** isn't being tracked.", ephemeral=True)
            return
        await interaction.response.send_message(f"Stopped tracking **{display}**.")

    @game_remove.autocomplete("name")
    async def game_remove_name_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        if interaction.guild_id is None:
            return []
        names = sorted(name for name, _ in added_games(interaction.guild_id).values() if current.lower() in name.lower())
        return [app_commands.Choice(name=n, value=n) for n in names[:25]]

    @game.command(name="list", description="Show which games get people roasted")
    async def game_list(interaction: discord.Interaction) -> None:
        if not await _require_bot_guild(interaction):
            return
        lines = []
        for name, message in tracked_games(interaction.guild_id).values():
            tag = " (default)" if is_default(name) else ""
            lines.append(f"• **{name}**{tag}: @player {message}")
        embed = discord.Embed(title="🎮 Tracked games", description="\n".join(lines), color=discord.Color.blurple())
        embed.set_footer(text="Only opted-in players are pinged. Add more with /roast game add")
        await interaction.response.send_message(embed=embed)

    # Admin-only: picks the channel game pings go to. Leaving the channel out goes back to the default.
    @game.command(name="channel", description="(Admin) Choose the channel game pings are posted in")
    @app_commands.describe(channel="Where to post game pings. Leave empty to go back to the default")
    async def game_channel(interaction: discord.Interaction, channel: discord.TextChannel | None = None) -> None:
        if not await _require_bot_guild(interaction):
            return
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("You need the Manage Server permission to change this.", ephemeral=True)
            return
        if channel is None:
            set_ping_channel(str(interaction.guild_id), None)
            await interaction.response.send_message(
                "Game pings will go to the default channel again (the first allowed channel from /settings)."
            )
            return
        if not channel.permissions_for(interaction.guild.me).send_messages:
            await interaction.response.send_message(f"I can't send messages in {channel.mention}.", ephemeral=True)
            return
        set_ping_channel(str(interaction.guild_id), str(channel.id))
        await interaction.response.send_message(f"Game pings will now be posted in {channel.mention}.")

    # Displays the calling user's currently linked Riot account and their Solo/Duo and Flex ranks.
    # Uses Components V2 layout with a container, section header, rank blocks, and footer.
    # Notifies the user if they haven't linked an account yet.
    @lol.command(name="account", description="Displays your currently linked Riot account")
    async def account(interaction: discord.Interaction) -> None:
        try:
            await interaction.response.defer()

            linked = get_link(str(interaction.user.id))
            if linked is None:
                await interaction.followup.send("You don't have a linked Riot account. Use /lol link to link one!")
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

        except Exception:
            import traceback
            traceback.print_exc()  # full details stay in the server logs, not the channel
            await interaction.followup.send(content="Something went wrong loading your account.", ephemeral=True)

    # Builds and sends a leaderboard embed for all opted-in users who have linked Riot accounts.
    # Fetches Solo/Duo and Flex ranks for each user, sorts by rank, and displays them with
    # tier/division emojis and LP. Ranked players are shown above a separator from unranked ones.
    # Embed color reflects the highest-ranked Solo/Duo player's tier.
    @lol.command(name="leaderboard", description="Shows the server's ranked leaderboard")
    async def leaderboard(interaction: discord.Interaction) -> None:
        if not await _require_bot_guild(interaction):
            return
        try:
            await interaction.response.defer()
        except discord.NotFound:
            return

        try:
            links = get_all_links()
            if not links:
                await interaction.followup.send("No one has linked their account yet! Use /lol link first.")
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

    steam = app_commands.Group(name="steam", description="Steam related commands")

    # Links a Steam account so game pings can use real playtime (hours in the last 2 weeks).
    @steam.command(name="link", description="Link your Steam account so playtime roasts are accurate")
    @app_commands.describe(profile="Your Steam profile link, custom URL name, or SteamID64")
    async def steam_link(interaction: discord.Interaction, profile: app_commands.Range[str, 1, 200]) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            steam_id = await resolve_steam_id(profile)
            info = await get_profile(steam_id) if steam_id else None
        except Exception as e:
            print(f"Steam lookup failed: {e!r}", flush=True)
            await interaction.followup.send("Couldn't reach Steam right now. Try again in a bit.", ephemeral=True)
            return
        if info is None:
            await interaction.followup.send(
                "Couldn't find that Steam account. Paste your profile link, "
                "e.g. `https://steamcommunity.com/id/yourname`.",
                ephemeral=True,
            )
            return

        save_steam_link(str(interaction.user.id), steam_id)
        try:
            games = await get_owned_games(steam_id)
        except Exception:
            games = {}
        if games:
            note = f"I can see {len(games)} games, so game pings will use your real playtime."
        else:
            note = (
                "Your game details are private, so I can't see your playtime yet. In Steam, go to "
                "Edit Profile → Privacy Settings and set **Game details** to Public."
            )
        await interaction.followup.send(f"Linked to Steam account **{info['name']}**. {note}", ephemeral=True)

    @steam.command(name="unlink", description="Unlink your Steam account")
    async def steam_unlink(interaction: discord.Interaction) -> None:
        if delete_steam_link(str(interaction.user.id)):
            await interaction.response.send_message("Unlinked your Steam account.", ephemeral=True)
        else:
            await interaction.response.send_message("You don't have a Steam account linked.", ephemeral=True)

    register_help(tree)
    tree.add_command(roast)
    tree.add_command(lol)
    tree.add_command(channel)
    tree.add_command(steam)
