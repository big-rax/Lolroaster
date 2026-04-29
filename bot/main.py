import discord
from pyke import Pyke

from .commands import register_commands
from .config import TOKEN, RIOT_API_KEY
from .events import register_events

from .riot_store import init_db

def build_client() -> tuple[discord.Client, discord.app_commands.CommandTree]:
    intents = discord.Intents.default()
    intents.message_content = True

    client = discord.Client(intents=intents)
    tree = discord.app_commands.CommandTree(client)
    api = Pyke(RIOT_API_KEY)

    register_commands(tree, api)
    register_events(client, tree)

    return client, tree


def main() -> None:
    
    
    init_db()
    
    client, _ = build_client()
    client.run(TOKEN)


if __name__ == "__main__":
    main()
