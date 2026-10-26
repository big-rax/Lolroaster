import random
import time

import discord

from .config import WORDLE_BOT_ID
from .triggers import handle_trigger_message
from .wordle import handle_wordle_message
from .store import is_bot_active, is_user_opted_in, get_guild_settings, get_allowed_channels
from .settings_ui import WelcomeView, WELCOME_TEXT, find_welcome_channel, send_setup_dm
from .activities import record_seen_activities, tracked_activities, tracked_games
from .deadlock import deadlock_updates, seed_deadlock_state
from .playtime import playtime_message, record_sessions, resume_sessions

ACTIVITY_PING_COOLDOWN = 3 * 60 * 60  # seconds between pings per person, per activity, per server
# (guild_id, user_id, lowercased activity name) -> time of last ping. In memory, so it resets on restart.
_activity_last_ping: dict[tuple[int, int, str], float] = {}


# Picks where presence-based messages go: the channel chosen with /roast game channel if the bot can
# still post there, otherwise the first allowed channel, or the welcome channel when all channels are allowed.
def find_announce_channel(guild: discord.Guild) -> discord.TextChannel | None:
    settings = get_guild_settings(str(guild.id))
    if not settings["enabled"]:
        return None
    if settings["ping_channel_id"]:
        channel = guild.get_channel(int(settings["ping_channel_id"]))
        if isinstance(channel, discord.TextChannel) and channel.permissions_for(guild.me).send_messages:
            return channel
    if settings["mode"] == "all":
        return find_welcome_channel(guild)
    for channel_id in get_allowed_channels(str(guild.id)):
        channel = guild.get_channel(int(channel_id))
        if isinstance(channel, discord.TextChannel) and channel.permissions_for(guild.me).send_messages:
            return channel
    return None


EDIT_RESPONSES = [
    "Caught you editing 😈",
    "🥸",
    "Whatcha editing 🕵️",
    "I know what you are, Light. https://tenor.com/bLgLG.gif",
]


def register_events(client: discord.Client, tree: discord.app_commands.CommandTree) -> None:
    @client.event
    async def on_ready() -> None:
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name="Use /roast toggle if you dare...",
        )
        await client.change_presence(status=discord.Status.online, activity=activity)
        await tree.sync()
        # Learn what people are already doing in Deadlock so in-progress queues/matches aren't announced late
        humans = [m for guild in client.guilds for m in guild.members if not m.bot]
        for member in humans:
            seed_deadlock_state(member)
        resume_sessions(humans)
        print(f"Logged in as {client.user}", flush=True)

    # Posts the setup prompt when the bot is added to a new server.
    @client.event
    async def on_guild_join(guild: discord.Guild) -> None:
        channel = find_welcome_channel(guild)
        if channel is not None:
            try:
                await channel.send(WELCOME_TEXT, view=WelcomeView())
                return
            except discord.HTTPException as e:
                print(f"Couldn't send welcome message in {guild.name}: {e}", flush=True)

        # Couldn't post in the server, so DM whoever added the bot (or the owner) instead
        reached = await send_setup_dm(guild)
        if reached:
            print(f"Joined {guild.name}: no channel to post in, DMed {reached} instead", flush=True)
        else:
            print(f"Joined {guild.name} but couldn't post anywhere or DM the inviter/owner", flush=True)

    @client.event
    async def on_message(message: discord.Message) -> None:
        if message.author.bot and message.author.id != WORDLE_BOT_ID:
            return

        if isinstance(message.channel, discord.Thread):
            return

        if message.author.id == WORDLE_BOT_ID:
            handled = await handle_wordle_message(message)
            if handled:
                return
        
        if not is_bot_active(str(message.guild.id) if message.guild else None, str(message.channel.id)):
            return
        
        if not is_user_opted_in(str(message.author.id)):
            return
        
        await handle_trigger_message(message)

    # Fires once per shared server whenever a member's status or activities change.
    @client.event
    async def on_presence_update(before: discord.Member, after: discord.Member) -> None:
        if after.bot:
            return
        record_seen_activities(after)
        record_sessions(after)

        # Deadlock Mod Manager phases (queue, match start, requeue). Tracked for everyone so the
        # state stays accurate; opt-in is only checked once there's something to post.
        deadlock_messages = deadlock_updates(after)
        if deadlock_messages and is_user_opted_in(str(after.id)):
            channel = find_announce_channel(after.guild)
            if channel is None:
                print(f"{after} Deadlock update in {after.guild.name}: skipped, no channel to post in", flush=True)
            for text in deadlock_messages if channel else []:
                print(f"{after} Deadlock update in {after.guild.name}: {text}", flush=True)
                try:
                    await channel.send(
                        f"{after.mention} {text}",
                        allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=[after]),
                    )
                except (discord.Forbidden, discord.HTTPException) as e:
                    print(f"Couldn't send Deadlock update in {after.guild.name}: {e}", flush=True)

        started = tracked_activities(after) - tracked_activities(before)
        if not started:
            return
        # Checked first and silently: presence plugins flicker on and off, which would flood the log
        if not is_user_opted_in(str(after.id)):
            return
        games = tracked_games(after.guild.id)
        who = f"{after} started {', '.join(sorted(games[key][0] for key in started))} in {after.guild.name}"

        now = time.monotonic()
        due = []
        for name in started:
            last = _activity_last_ping.get((after.guild.id, after.id, name))
            if last is None or now - last >= ACTIVITY_PING_COOLDOWN:
                due.append(name)
        if not due:
            print(f"{who}: skipped, on cooldown", flush=True)
            return

        channel = find_announce_channel(after.guild)
        if channel is None:
            print(f"{who}: skipped, no channel to post in", flush=True)
            return
        print(f"{who}: pinging in #{channel.name}", flush=True)

        for key in due:
            _activity_last_ping[(after.guild.id, after.id, key)] = now
            name, message = games[key]
            message = await playtime_message(after, name, message)
            try:
                # Messages are user-written, so only allow pinging the player (no @everyone or roles)
                await channel.send(
                    f"{after.mention} {message}",
                    allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=[after]),
                )
            except (discord.Forbidden, discord.HTTPException) as e:
                print(f"Couldn't send {name} ping in {after.guild.name}: {e}", flush=True)

    @client.event
    async def on_message_edit(before: discord.Message, after: discord.Message) -> None:
        if after.author.id == WORDLE_BOT_ID:
            return

        if isinstance(after.channel, discord.Thread):
            return

        if after.author.bot:
            return

        if before.content == after.content:
            return
        
        if not is_bot_active(str(after.guild.id) if after.guild else None, str(after.channel.id)):
            return
        
        if not is_user_opted_in(str(after.author.id)):
            return

        await after.reply(random.choice(EDIT_RESPONSES))
