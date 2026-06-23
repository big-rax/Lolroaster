import discord
from discord import app_commands
from pyke import Continent, Pyke, exceptions, DataDragon
from bot.riot_api import get_account_info, get_champion_mastery, get_all_ranks, rank_sort_key, get_live_game, get_champion_name_map
from bot.store import save_link, add_allowed_channel, remove_allowed_channel, get_allowed_channels, get_link, toggle_user_opt_in, get_all_links, is_user_opted_in


# Registers all slash commands with the Discord command tree.
# Takes the command tree, Riot API client, and DataDragon client as arguments.
def register_commands(tree: app_commands.CommandTree, api: Pyke, ddragon: DataDragon) -> None:
    @tree.command(name="ping", description="Replies with pong")
    async def ping(interaction: discord.Interaction) -> None:
        await interaction.response.send_message("pong (in python)")

    @tree.command(name="freaky_command", description="does something freaky")
    async def freaky_command(interaction: discord.Interaction) -> None:
        await interaction.response.send_message("😛😛😛lul")

    #@tree.command(name"Track", description="Tracks a user")
    # Looks up a Riot account by game name and tag line, saves the link to the calling user's
    # Discord ID, and replies with an embed showing their level and Solo/Duo rank.
    @tree.command(name="riot_link", description="Links your Riot account")
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

        rank=info["rank"]

        rank_str= f"{rank['tier']} {rank['rank']} - {rank['leaguePoints']} LP" if rank else "Unranked"

        embed = discord.Embed(title=f"{info['gameName']}#{info['tagLine']}", color=discord.Color.blue())

        embed.add_field(name="Level", value=str(info["summonerLevel"]), inline=True)
        embed.add_field(name="Solo/Duo Rank", value=rank_str, inline=True)
        embed.set_footer(text=f"Linked to {interaction.user.display_name}")

        await interaction.followup.send(embed=embed)

    # Fetches the top champion masteries for the calling user's linked Riot account
    # and displays them in an embed ordered by mastery points.
    @tree.command(name="league_mastery", description="Displays your top champion masteries")
    async def league_mastery(interaction: discord.Interaction) -> None:
        await interaction.response.defer()

        linked = get_link(str(interaction.user.id))
        if linked is None:
            await interaction.followup.send("You haven't linked a Riot account yet! Use /riot_link first.")
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
    @tree.command(name="set_channel", description="Sets the channel in which the bot is allowed to message, react, etc.")
    async def set_channel(interaction: discord.Interaction) -> None:
        add_allowed_channel(str(interaction.channel_id), str(interaction.guild_id))
        await interaction.response.send_message(f"✅ Lolroaster will now react (roast) users in <#{interaction.channel_id}>")

    # Removes the current channel from the bot's allowed list.
    @tree.command(name="remove_allowed_channel", description="Removes an allowed channel")
    async def removed_allowed_channel(interaction: discord.Interaction) -> None:
        remove_allowed_channel(str(interaction.channel_id))
        await interaction.response.send_message(f"😶‍🌫️ Lolroaster will no longer yap in <#{interaction.channel_id}>")

    # Lists all channels in the server that the bot is currently allowed to operate in.
    @tree.command(name="list_channels",description="List all allowed channels in a server")
    async def list_channels(interaction: discord.Interaction) -> None:
        channels = get_allowed_channels(str(interaction.guild_id))
        if not channels:
            return interaction.response.send_message("There are no channels currently set, please use /set_channel to add a channel!")
        channel_mentions = "\n".join([f"<#{cid}>" for cid in channels])
        await interaction.response.send_message(f"Allowed channels:{channel_mentions}")


    roast = app_commands.Group(name="roast", description="Roast related commands")

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
    @roast.command(name="toggle_user", description="(Admin) Toggle opt-in status for a specific user")
    async def toggle_user(interaction: discord.Interaction, user: discord.Member) -> None:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return
        opted_in = toggle_user_opt_in(str(user.id))
        if opted_in:
            await interaction.response.send_message(f"<@{user.id}> will now be opted in to all Lolroaster interactions.", ephemeral=True)
        else:
            await interaction.response.send_message(f"<@{user.id}> has been opted out.", ephemeral=True)

    # Checks if a linked user is currently in a live game. Defaults to the caller if no user is
    # specified. Shows game mode, time elapsed, and both teams with champion names and Riot IDs.
    @roast.command(name="live", description="Check if you (or another linked user) are in a live game")
    async def live(interaction: discord.Interaction, user: discord.Member | None = None) -> None:
        await interaction.response.defer()

        target = user or interaction.user
        linked = get_link(str(target.id))
        if linked is None:
            noun = "You haven't" if user is None else f"{target.display_name} hasn't"
            await interaction.followup.send(f"{noun} linked a Riot account yet.")
            return

        game = await get_live_game(api, linked["puuid"])
        if game is None:
            noun = "You're" if user is None else f"{target.display_name} is"
            await interaction.followup.send(f"{noun} not currently in a game.")
            return

        QUEUE_NAMES = {
            420: "Ranked Solo/Duo", 440: "Ranked Flex", 450: "ARAM",
            400: "Normal Draft", 430: "Normal Blind", 0: "Custom",
        }
        queue_name = QUEUE_NAMES.get(game.get("gameQueueConfigId", 0), game.get("gameMode", "Unknown"))

        elapsed = game.get("gameLength", 0)
        time_str = f"{elapsed // 60}m {elapsed % 60}s" if elapsed > 0 else "In loading screen"

        champ_map = await get_champion_name_map()

        blue = [p for p in game["participants"] if p["teamId"] == 100]
        red = [p for p in game["participants"] if p["teamId"] == 200]

        def fmt_team(players: list) -> str:
            lines = []
            for p in players:
                champ = champ_map.get(p["championId"], str(p["championId"])) if champ_map else str(p["championId"])
                name = p.get("riotId", p.get("summonerName", "Unknown"))
                lines.append(f"**{champ}** — {name}")
            return "\n".join(lines)

        embed = discord.Embed(
            title=f"🔴 Live Game — {queue_name}",
            description=f"⏱️ {time_str}",
            color=discord.Color.red()
        )
        embed.add_field(name="🔵 Blue Team", value=fmt_team(blue), inline=True)
        embed.add_field(name="🔴 Red Team", value=fmt_team(red), inline=True)
        embed.set_footer(text=f"{linked['game_name']}#{linked['tag_line']}")

        await interaction.followup.send(embed=embed)

    # Builds and sends a leaderboard embed for all opted-in users who have linked Riot accounts.
    # Fetches Solo/Duo and Flex ranks for each user, sorts by rank, and displays them with
    # tier/division emojis and LP. Ranked players are shown above a separator from unranked ones.
    # Embed color reflects the highest-ranked Solo/Duo player's tier.
    @roast.command(name="leaderboard", description="Shows the server's ranked leaderboard")
    async def leaderboard(interaction: discord.Interaction) -> None:
        try:
            await interaction.response.defer()

            links = get_all_links()
            if not links:
                await interaction.followup.send("No one has linked their account yet! Use /riot_link first.")
                return

            solo_entries = []
            flex_entries = []

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
                riot_name = f"{link['game_name']}#{link['tag_line']}"
                extra = {"name": riot_name, "display_name": member.display_name}

                solo_entries.append({**ranks["solo"], **extra} if ranks["solo"] else extra)
                flex_entries.append({**ranks["flex"], **extra} if ranks["flex"] else extra)

            solo_entries.sort(key=rank_sort_key, reverse=True)
            flex_entries.sort(key=rank_sort_key, reverse=True)

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

            top_tier = next((e["tier"].lower() for e in solo_entries if "tier" in e), None)
            embed_color = discord.Color(TIER_COLOR[top_tier]) if top_tier else discord.Color.fuchsia()

            def format_entry(i: int, e: dict) -> str:
                medal = ["🥇", "🥈", "🥉"][i] if i < 3 else f"`{i+1}.`"
                label = f"**{e['display_name']}** ({e['name']})"
                tier_lower = e["tier"].lower()
                tier_emoji = TIER_EMOJI.get(tier_lower, "")
                div_emoji = DIVISION_EMOJI.get(e["rank"], "") if tier_lower in TIERED else ""
                return f"{medal} {tier_emoji} {label} — {e['tier'].capitalize()} {e['rank']} {div_emoji} {e['leaguePoints']:,} LP"

            def build_field(entries: list) -> str:
                ranked = [e for e in entries if "tier" in e]
                unranked = [e for e in entries if "tier" not in e]
                lines = [format_entry(i, e) for i, e in enumerate(ranked)]
                if ranked and unranked:
                    lines.append("───────────────\n**Grass Touchers**")
                for e in unranked:
                    lines.append(f"-# {e['display_name']} ({e['name']}) — Unranked")
                return "\n".join(lines) if lines else None

            embed = discord.Embed(title="🏆 Server Leaderboard", color=embed_color)

            embed.add_field(
                name="Solo/Duo Queue",
                value=build_field(solo_entries) or "No players yet.",
                inline=False
            )

            embed.add_field(name="​", value="​", inline=False)

            embed.add_field(
                name="Flex Queue",
                value=build_field(flex_entries) or "No players yet.",
                inline=False
            )

            embed.set_footer(text=f"Requested by {interaction.user.display_name}")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            import traceback
            traceback.print_exc()
            await interaction.followup.send(content=str(e))

    tree.add_command(roast)
