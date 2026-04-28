import discord
from discord import app_commands
from pyke import Continent, Pyke, exceptions

from bot.riot_store import save_link


def register_commands(tree: app_commands.CommandTree) -> None:
    @tree.command(name="ping", description="Replies with pong")
    async def ping(interaction: discord.Interaction) -> None:
        await interaction.response.send_message("pong (in python)")

    @tree.command(name="freaky_command", description="does something freaky")
    async def freaky_command(interaction: discord.Interaction) -> None:
        await interaction.response.send_message("😛😛😛lul")

    #@tree.command(name"Track", description="Tracks a user")
    @tree.command(name="riot_link", description="Links your Riot account")
    async def riot_link(
        interaction: discord.Interaction,
        game_name: str,
        tag_line: str
    ) -> None:
        await interaction.response.defer()


        save_link(
            discord_id=str(interaction.user.id),
            puuid="",
            game_name=game_name,
            tag_line=tag_line,
        )

        

        await interaction.followup.send("test")
