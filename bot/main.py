import asyncio
import signal
import discord
from pyke import Pyke, DataDragon

from .commands import register_commands
from .config import TOKEN, RIOT_API_KEY
from .events import register_events
from .settings_ui import WelcomeView, DmSetupButton, DmSkipButton
from .store import init_db, touch_open_game_sessions
from .activities import load_tracked_games, known_games_loop
from .playtime import heartbeat_loop
from .leaderboard import leaderboard_loop, LeaderboardPageSelect


def build_client(api, ddragon) -> tuple[discord.Client, discord.app_commands.CommandTree]:
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    intents.presences = True  # privileged: also enable "Presence Intent" in the Developer Portal

    # Only user pings are allowed, so text echoed back from users can't trigger @everyone or role pings
    allowed_mentions = discord.AllowedMentions(everyone=False, roles=False, users=True, replied_user=True)
    client = discord.Client(intents=intents, allowed_mentions=allowed_mentions)
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
    client.add_dynamic_items(LeaderboardPageSelect)  # leaderboard page dropdown, on old posts too

    return client, tree


async def main() -> None:
    init_db()
    load_tracked_games()
    # Kept referenced so the tasks aren't garbage collected
    known_games_task = asyncio.create_task(known_games_loop())
    heartbeat_task = asyncio.create_task(heartbeat_loop())
    async with Pyke(RIOT_API_KEY) as api, DataDragon() as ddragon:
        client, _ = build_client(api, ddragon)
        leaderboard_task = asyncio.create_task(leaderboard_loop(client))
        # Hosts like Heroku stop the bot with SIGTERM (deploys, daily restarts). Closing the client lets
        # client.start() return normally instead of the process dying mid-heartbeat.
        try:
            asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, lambda: asyncio.create_task(client.close()))
        except NotImplementedError:
            pass  # Windows can't add signal handlers to the loop; Ctrl+C still stops the bot there
        try:
            await client.start(TOKEN)
        finally:
            # Open sessions are closed at their last_seen on the next start, so mark them seen right up to now
            try:
                touch_open_game_sessions()
            except Exception as e:
                print(f"Couldn't update open game sessions on shutdown: {e!r}", flush=True)
            print("Bot stopped", flush=True)


if __name__ == "__main__":
    asyncio.run(main())