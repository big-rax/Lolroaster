import discord
from discord import app_commands
from pyke import Continent, Pyke, exceptions


def register_commands(tree: app_commands.CommandTree) -> None:
    @tree.command(name="ping", description="Replies with pong")
    async def ping(interaction: discord.Interaction) -> None:
        await interaction.response.send_message("pong (in python)")

    @tree.command(name="freaky_command", description="does something freaky")
    async def freaky_command(interaction: discord.Interaction) -> None:
        await interaction.response.send_message("😛😛😛lul")

    #@tree.command(name"Track", description="Tracks a user")
    @tree.command(name="riot_link", description="Links a Riot account for tracking")
    async def riot_link(interaction: discord.Interaction, riot_username: str) -> None:
        await interaction.response.send_message(f"Linking Riot account: {riot_username}")
