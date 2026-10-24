import asyncio
import discord
from pyke import Pyke, DataDragon

from .commands import register_commands
from .config import TOKEN, RIOT_API_KEY
from .events import register_events
from .settings_ui import WelcomeView, DmSetupButton, DmSkipButton
from .store import init_db


def build_client(api, ddragon) -> tuple[discord.Client, discord.app_commands.CommandTree]:
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True

    client = discord.Client(intents=intents)
    # Commands work in servers and, for users who install the app to their account, in DMs and group chats
    tree = discord.app_commands.CommandTree(
        client,
        allowed_installs=discord.app_commands.AppInstallationType(guild=True, user=True),
        allowed_contexts=discord.app_commands.AppCommandContext(guild=True, dm_channel=True, private_channel=True),
    )

    register_commands(tree, api, ddragon)
    register_events(client, tree)
    client.add_view(WelcomeView())  # keeps welcome-message buttons working after restarts
    client.add_dynamic_items(DmSetupButton, DmSkipButton)  # same for the DM version

    return client, tree


async def main() -> None:
    init_db()
    async with Pyke(RIOT_API_KEY) as api, DataDragon() as ddragon:
        client, _ = build_client(api, ddragon)
        await client.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())