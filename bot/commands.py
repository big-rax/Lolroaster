import discord
from discord import app_commands
from pyke import Continent, Pyke, exceptions
from bot.riot_api import get_account_info
from bot.riot_store import save_link


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

        rank_str= f"{rank["tier"]} {rank["rank"]} - {rank["leaguePoints"]} LP" if rank else "Unranked"

        await interaction.followup.send(f"Account found, current ranked stats are: {rank_str}")
