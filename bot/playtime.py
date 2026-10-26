from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import discord

from .activities import all_tracked_names
from .steam import get_owned_games
from .store import (
    close_game_session, close_stale_game_sessions, get_recorded_playtime, get_recording_start,
    get_steam_link, is_user_opted_in, open_game_session, touch_open_game_sessions,
)

HEARTBEAT = 5 * 60  # seconds between marking open sessions as still going

# Hour thresholds for the start-of-game ping. Steam only reports the last 2 weeks, so its are doubled.
WEEK_THRESHOLDS = (5, 15)
STEAM_THRESHOLDS = (10, 30)

# (user_id, lowercased game) -> open session id, or None if they're playing but not being recorded
# (not opted in). Presence updates arrive once per shared server, so this keeps each session from being
# opened or closed more than once, and avoids re-checking opt-in on every update while they play.
_open: dict[tuple[int, str], int | None] = {}


def _tracked_now(member: discord.Member) -> dict[str, discord.BaseActivity]:
    names = all_tracked_names()
    return {
        a.name.lower(): a for a in member.activities
        if a.name and a.name.lower() in names and a.type != discord.ActivityType.custom
    }


# Opens and closes play sessions to match what the member is doing. Only opted-in users are recorded.
def record_sessions(member: discord.Member) -> None:
    now_playing = _tracked_now(member)
    for key in [k for k in _open if k[0] == member.id and k[1] not in now_playing]:
        session_id = _open.pop(key)
        if session_id is not None:
            close_game_session(session_id)

    new = [name for name in now_playing if (member.id, name) not in _open]
    if not new:
        return
    if not is_user_opted_in(str(member.id)):
        for name in new:
            _open[(member.id, name)] = None
        return
    now = datetime.now(timezone.utc)
    for name in new:
        activity = now_playing[name]
        # Discord's start time covers sessions that began before the bot noticed (e.g. after a restart)
        started = getattr(activity, "start", None) or now
        _open[(member.id, name)] = open_game_session(str(member.id), activity.name, min(started, now))


_resumed = False


# Startup: close sessions a previous run left open, then pick up whatever people are playing now.
# Discord fires on_ready again after reconnects; those only catch up on changes, without closing anything.
def resume_sessions(members: list[discord.Member]) -> None:
    global _resumed
    if not _resumed:
        close_stale_game_sessions()
        _resumed = True
    for member in members:
        record_sessions(member)


async def heartbeat_loop() -> None:
    while True:
        await asyncio.sleep(HEARTBEAT)
        try:
            touch_open_game_sessions()
        except Exception as e:
            print(f"Couldn't update open game sessions: {e!r}", flush=True)


async def _steam_hours(discord_id: int, game_name: str) -> tuple[float, float] | None:
    steam_id = get_steam_link(str(discord_id))
    if steam_id is None:
        return None
    try:
        game = (await get_owned_games(steam_id)).get(game_name.lower())
    except Exception as e:
        print(f"Couldn't fetch Steam playtime: {e!r}", flush=True)
        return None
    if game is None:
        return None  # private game details, or the game isn't on Steam
    return game["two_weeks"] / 60, game["forever"] / 60


# Adds a remark to a start-of-game ping based on how much they've played it lately.
# Prefers Steam (complete, but per 2 weeks) and falls back to sessions the bot recorded (past 7 days).
async def playtime_message(member: discord.Member, game_name: str, message: str) -> str:
    steam = await _steam_hours(member.id, game_name)
    if steam is not None:
        hours, forever = steam
        period, (mid, high) = "in the last 2 weeks", STEAM_THRESHOLDS
        # Steam knows their full history, so zero recent hours really means a break
        known_break = hours == 0
    else:
        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)
        hours = get_recorded_playtime(str(member.id), game_name, week_ago) / 3600
        period, (mid, high) = "this week", WEEK_THRESHOLDS
        # Only claim a break once the bot has been recording for a full week
        recording_start = get_recording_start()
        known_break = hours == 0 and recording_start is not None and recording_start <= week_ago

    if known_break:
        return f"{message}?? first time in a while"
    if hours >= high:
        return f"{message}. {hours:.0f} hours {period}, go outside"
    if hours >= mid:
        return f"{message} again ({hours:.0f}h {period})"
    return message
