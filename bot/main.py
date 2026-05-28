import asyncio
import discord
from pyke import Pyke, DataDragon

from .commands import register_commands
from .config import TOKEN, RIOT_API_KEY
from .events import register_events
from .store import init_db


def build_client(api, ddragon) -> tuple[discord.Client, discord.app_commands.CommandTree]:
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True

    client = discord.Client(intents=intents)
    tree = discord.app_commands.CommandTree(client)

    register_commands(tree, api, ddragon)
    register_events(client, tree)

    return client, tree


async def main() -> None:
    init_db()
    async with Pyke(RIOT_API_KEY) as api, DataDragon() as ddragon:
        client, _ = build_client(api, ddragon)
        await client.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())