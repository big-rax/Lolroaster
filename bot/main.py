import asyncio
import discord
from pyke import Pyke, DataDragon

from .commands import register_commands
from .config import TOKEN, RIOT_API_KEY
from .events import register_events
from .settings_ui import WelcomeView, DmSetupButton, DmSkipButton
from .store import init_db
from .activities import load_tracked_games, known_games_loop
from .playtime import heartbeat_loop


def build_client(api, ddragon) -> tuple[discord.Client, discord.app_commands.CommandTree]:
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    intents.presences = True  # privileged: also enable "Presence Intent" in the Developer Portal

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
    load_tracked_games()
    # Kept referenced so the tasks aren't garbage collected
    known_games_task = asyncio.create_task(known_games_loop())
    heartbeat_task = asyncio.create_task(heartbeat_loop())
    async with Pyke(RIOT_API_KEY) as api, DataDragon() as ddragon:
        client, _ = build_client(api, ddragon)
        await client.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())