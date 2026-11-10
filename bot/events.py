import asyncio
import random
import time

import discord

from .config import WORDLE_BOT_ID
from .triggers import handle_trigger_message
from .wordle import handle_wordle_message
from .store import is_bot_active, is_user_opted_in, get_guild_settings, get_allowed_channels, wants_ping_mentions
from .settings_ui import WelcomeView, WELCOME_TEXT, find_welcome_channel, send_setup_dm
from .activities import record_seen_activities, tracked_activities, tracked_games
from .deadlock import PartyEvent, deadlock_updates, group_message, party_message, seed_deadlock_state
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


# Posts "@player <text>". The mention always shows as a clickable @name, but only notifies players who
# turned that on with /roast game mentions. Messages can be user-written, so nobody else is ever pinged.
async def send_game_ping(channel: discord.TextChannel, member: discord.Member, text: str) -> None:
    await send_ping(channel, f"{member.mention} {text}", [member])


# Sends a message that @s the given members, notifying only the ones who turned mentions on.
async def send_ping(channel: discord.TextChannel, content: str, members: list[discord.Member]) -> None:
    notify = [m for m in members if wants_ping_mentions(str(m.id))]
    allowed = discord.AllowedMentions(everyone=False, roles=False, users=notify)
    await channel.send(content, allowed_mentions=allowed)


# Party members' presences change a few seconds apart, so Deadlock events for parties are held this long
# and members of the same server who did the same thing with the same party size are posted together.
PARTY_GROUP_WINDOW = 15
# (guild_id, "queue" or "match", party size) -> {user_id: (member, event)} waiting to be posted.
# Queue and requeue share a group, since one party member may have been tracked through the last match
# and another not (e.g. they joined the server's tracking after a restart).
_pending_parties: dict[tuple[int, str, int], dict[int, tuple[discord.Member, PartyEvent]]] = {}
_party_tasks: set[asyncio.Task] = set()


async def post_deadlock_event(member: discord.Member, event: PartyEvent) -> None:
    if event.size <= 1:
        await _post_deadlock([(member, event)], member.guild, event.event, event.size)
        return
    key = (member.guild.id, "match" if event.event == "match" else "queue", event.size)
    if key not in _pending_parties:
        _pending_parties[key] = {}
        task = asyncio.create_task(_flush_party(key, member.guild))
        _party_tasks.add(task)  # kept referenced until done so it isn't garbage collected
        task.add_done_callback(_party_tasks.discard)
    _pending_parties[key][member.id] = (member, event)


async def _flush_party(key: tuple[int, str, int], guild: discord.Guild) -> None:
    await asyncio.sleep(PARTY_GROUP_WINDOW)
    group = list(_pending_parties.pop(key, {}).values())
    # A single requeue in the group makes it a requeue message: someone's back right after a match
    event = "requeue" if any(e.event == "requeue" for _, e in group) else key[1]
    await _post_deadlock(group, guild, event, key[2])


async def _post_deadlock(
    group: list[tuple[discord.Member, PartyEvent]], guild: discord.Guild, event: str, size: int
) -> None:
    names = ", ".join(str(m) for m, _ in group)
    channel = find_announce_channel(guild)
    if channel is None:
        print(f"{names} Deadlock {event} in {guild.name}: skipped, no channel to post in", flush=True)
        return
    if len(group) == 1:
        member, single = group[0]
        content = f"{member.mention} {party_message(single)}"
    else:
        content = group_message(event, size, [(m.mention, e.hero) for m, e in group])
    print(f"{names} Deadlock {event} in {guild.name}: {content}", flush=True)
    try:
        await send_ping(channel, content, [m for m, _ in group])
    except (discord.Forbidden, discord.HTTPException) as e:
        print(f"Couldn't send Deadlock update in {guild.name}: {e}", flush=True)


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
        deadlock_events = deadlock_updates(after)
        if deadlock_events and is_user_opted_in(str(after.id)):
            for event in deadlock_events:
                await post_deadlock_event(after, event)

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
                await send_game_ping(channel, after, message)
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
