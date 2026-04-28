import discord

from .commands import register_commands
from .config import TOKEN
from .events import register_events


def build_client() -> tuple[discord.Client, discord.app_commands.CommandTree]:
    intents = discord.Intents.default()
    intents.message_content = True

    client = discord.Client(intents=intents)
    tree = discord.app_commands.CommandTree(client)

    register_commands(tree)
    register_events(client, tree)

    return client, tree


def main() -> None:
    client, _ = build_client()
    client.run(TOKEN)


if __name__ == "__main__":
    main()
