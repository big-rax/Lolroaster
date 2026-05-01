import discord
from discord import app_commands
from discord import embeds
from pyke import Continent, Pyke, exceptions
from bot.riot_api import get_account_info
from bot.store import save_link, add_allowed_channel, remove_allowed_channel, get_allowed_channels


def register_commands(tree: app_commands.CommandTree, api: Pyke) -> None:
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
            await interaction.followup.send(f"Couldn't find Riot account for {game_name}#{tag_line}. or some other shit broke idk")
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