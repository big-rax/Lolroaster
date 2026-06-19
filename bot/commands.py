import discord
from discord import app_commands
from pyke import Continent, Pyke, exceptions, DataDragon
from bot.riot_api import get_account_info, get_champion_mastery, get_all_ranks, rank_sort_key
from bot.store import save_link, add_allowed_channel, remove_allowed_channel, get_allowed_channels, get_link, toggle_user_opt_in, get_all_links


def register_commands(tree: app_commands.CommandTree, api: Pyke, ddragon: DataDragon) -> None:
    @tree.command(name="ping", description="Replies with pong")
    async def ping(interaction: discord.Interaction) -> None:
        await interaction.response.send_message("pong (in python)")

    @tree.command(name="freaky_command", description="does something freaky")
    async def freaky_command(interaction: discord.Interaction) -> None:
        await interaction.response.send_message("😛😛😛lul")

    #@tree.command(name"Track", description="Tracks a user")
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

    @tree.command(name="set_channel", description="Sets the channel in which the bot is allowed to message, react, etc.")
    async def set_channel(interaction: discord.Interaction) -> None:
        add_allowed_channel(str(interaction.channel_id), str(interaction.guild_id))
        await interaction.response.send_message(f"✅ Lolroaster will now react (roast) users in <#{interaction.channel_id}>")

    @tree.command(name="remove_allowed_channel", description="Removes an allowed channel")
    async def removed_allowed_channel(interaction: discord.Interaction) -> None:
        remove_allowed_channel(str(interaction.channel_id))
        await interaction.response.send_message(f"😶‍🌫️ Lolroaster will no longer yap in <#{interaction.channel_id}>")

    @tree.command(name="list_channels",description="List all allowed channels in a server")
    async def list_channels(interaction: discord.Interaction) -> None:
        channels = get_allowed_channels(str(interaction.guild_id))
        if not channels:
            return interaction.response.send_message("There are no channels currently set, please use /set_channel to add a channel!")
        channel_mentions = "\n".join([f"<#{cid}>" for cid in channels])
        await interaction.response.send_message(f"Allowed channels:{channel_mentions}")

    
    roast = app_commands.Group(name="roast", description="Roast related commands")

    @roast.command(name="toggle", description="Toggle whether the bot interacts with you")
    async def roast_toggle(interaction: discord.Interaction) -> None:
        opted_in = toggle_user_opt_in(str(interaction.user.id))
        if opted_in:
            await interaction.response.send_message("You will now be roasted (when the occasion calls for it)", ephemeral=True)
        else:
            await interaction.response.send_message("You will no longer be roasted... at least by me.", ephemeral=True)

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
                if interaction.guild.get_member(int(link["discord_id"])) is None:
                    try:
                        await interaction.guild.fetch_member(int(link["discord_id"]))
                    except discord.NotFound:
                        continue

                ranks = await get_all_ranks(api, link["puuid"])
                name = f"{link['game_name']}#{link['tag_line']}"

                
                solo_entries.append({**ranks["solo"], "name": name} if ranks["solo"] else {"name": name})
                flex_entries.append({**ranks["flex"], "name": name} if ranks["flex"] else {"name": name})

            solo_entries.sort(key=rank_sort_key, reverse=True)
            flex_entries.sort(key=rank_sort_key, reverse=True)

            def format_entry(i: int, e: dict) -> str:
                medal = ["🥇", "🥈", "🥉"][i] if i < 3 else f"`{i+1}.`"
                if "tier" not in e:
                    return f"{medal} **{e['name']}** — Unranked"
                return f"{medal} **{e['name']}** — {e['tier'].capitalize()} {e['rank']} {e['leaguePoints']} LP"

            embed = discord.Embed(title="🏆 Server Leaderboard", color=discord.Color.gold())

            if solo_entries:
                embed.add_field(
                    name="Solo/Duo Queue",
                    value="\n".join(format_entry(i, e) for i, e in enumerate(solo_entries)),
                    inline=False
                )
            else:
                embed.add_field(name="Solo/Duo Queue", value="No ranked players yet.", inline=False)

            if flex_entries:
                embed.add_field(
                    name="Flex Queue",
                    value="\n".join(format_entry(i, e) for i, e in enumerate(flex_entries)),
                    inline=False
                )
            else:
                embed.add_field(name="Flex Queue", value="No ranked players yet.", inline=False)

            embed.set_footer(text=f"Requested by {interaction.user.display_name}")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            import traceback
            traceback.print_exc()
            interaction.followup.send(content=e)

    tree.add_command(roast)