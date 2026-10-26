from __future__ import annotations

import asyncio

import aiohttp
import discord

from .store import add_tracked_game, remove_tracked_game, get_all_tracked_games

# Undocumented but public: every game Discord can auto-detect ("Playing X"), with alternate names
DETECTABLE_URL = "https://discord.com/api/v10/applications/detectable"
DETECTABLE_REFRESH = 24 * 60 * 60  # seconds
# lowercased name or alias -> Discord's canonical name. Empty until the first download succeeds.
_known_games: dict[str, str] = {}
# guild_id -> {lowercased name: name} of activities members have shown since the bot started.
# Covers apps Discord can't detect itself, like editors that report presence through a plugin.
_seen: dict[int, dict[str, str]] = {}

# Activities every server tracks. Values are the text posted after the user's mention.
DEFAULT_GAMES = {
    "League of Legends": "is playing league oh no",
    "Neovim": "is coding 🤓",
    "Deadlock": "is playing deadlock 💀",
}
MAX_GAMES_PER_SERVER = 25  # also Discord's cap on autocomplete choices
MAX_GAME_NAME = 100
MAX_MESSAGE = 200

# guild_id -> {lowercased name: (display name, message or None)} for games added with /roast game.
# Presence updates arrive constantly, so this is kept in memory instead of querying per update.
_added: dict[int, dict[str, tuple[str, str | None]]] = {}


def load_tracked_games() -> None:
    _added.clear()
    for guild_id, name, message in get_all_tracked_games():
        _added.setdefault(int(guild_id), {})[name.lower()] = (name, message)


def is_default(name: str) -> bool:
    return name.lower() in {n.lower() for n in DEFAULT_GAMES}


def added_games(guild_id: int) -> dict[str, tuple[str, str | None]]:
    return _added.get(guild_id, {})


# Every tracked game for a server as {lowercased name: (display name, message)}, defaults included.
def tracked_games(guild_id: int) -> dict[str, tuple[str, str]]:
    games = {name.lower(): (name, message) for name, message in DEFAULT_GAMES.items()}
    for key, (name, message) in added_games(guild_id).items():
        games[key] = (name, message or f"is playing {name}")
    return games


def add_game(guild_id: int, name: str, message: str | None, added_by: int) -> bool:
    if not add_tracked_game(str(guild_id), name, message, str(added_by)):
        return False
    _added.setdefault(guild_id, {})[name.lower()] = (name, message)
    return True


def remove_game(guild_id: int, name: str) -> bool:
    if not remove_tracked_game(str(guild_id), name):
        return False
    added_games(guild_id).pop(name.lower(), None)
    return True


# Lowercased names of every game tracked by any server. Playtime is recorded per person, so this has
# to be the same everywhere; otherwise a server that doesn't track a game would seem to end its sessions.
def all_tracked_names() -> set[str]:
    names = {name.lower() for name in DEFAULT_GAMES}
    for games in _added.values():
        names.update(games)
    return names


# Lowercased names of the tracked games a member currently has. Matched by name (ignoring case) rather
# than "playing" only, since editor presence plugins don't all report that type. Custom statuses are
# skipped so typing a game name as your status doesn't count.
def tracked_activities(member: discord.Member) -> set[str]:
    games = tracked_games(member.guild.id)
    return {
        a.name.lower() for a in member.activities
        if a.name and a.name.lower() in games and a.type != discord.ActivityType.custom
    }


# Names of activities members of this server are doing right now, for autocomplete.
def current_activity_names(guild: discord.Guild) -> set[str]:
    return {
        a.name for m in guild.members if not m.bot for a in m.activities
        if a.name and a.type != discord.ActivityType.custom
    }


async def refresh_known_games() -> None:
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(DETECTABLE_URL) as resp:
            resp.raise_for_status()
            apps = await resp.json()
    known = {}
    for app in apps:
        name = app.get("name")
        if not name:
            continue
        for alias in [name, *(app.get("aliases") or [])]:
            known.setdefault(alias.lower(), name)
    _known_games.clear()
    _known_games.update(known)
    print(f"Loaded {len(known)} detectable game names from Discord", flush=True)


# Downloads Discord's game list at startup and once a day after. On failure the previous list is kept
# (or, if there never was one, only activities seen in the server can be added).
async def known_games_loop() -> None:
    while True:
        try:
            await refresh_known_games()
        except Exception as e:
            print(f"Couldn't download Discord's game list: {e!r}", flush=True)
        await asyncio.sleep(DETECTABLE_REFRESH)


def record_seen_activities(member: discord.Member) -> None:
    seen = _seen.setdefault(member.guild.id, {})
    for a in member.activities:
        if a.name and a.type != discord.ActivityType.custom:
            seen.setdefault(a.name.lower(), a.name)


# Activity names this server has shown, now or since the bot started.
def server_activity_names(guild: discord.Guild) -> set[str]:
    return current_activity_names(guild) | set(_seen.get(guild.id, {}).values())


# Returns the name to store for a game, or None if it isn't real: it must be in Discord's game list
# or be something members of this server have actually shown as an activity. Uses the official spelling.
def resolve_game_name(guild: discord.Guild, name: str) -> str | None:
    key = name.strip().lower()
    for seen in server_activity_names(guild):
        if seen.lower() == key:
            return seen
    return _known_games.get(key)


# Autocomplete suggestions: what this server plays first, then matches from Discord's game list.
def suggest_game_names(guild: discord.Guild, current: str, exclude: set[str], limit: int = 25) -> list[str]:
    query = current.strip().lower()
    server = sorted(n for n in server_activity_names(guild) if query in n.lower() and n.lower() not in exclude)
    suggestions = server[:limit]
    if query and len(suggestions) < limit:
        taken = {n.lower() for n in suggestions} | exclude
        # Prefix matches rank above matches elsewhere in the name
        matches = sorted(
            {n for key, n in _known_games.items() if query in key and n.lower() not in taken},
            key=lambda n: (not n.lower().startswith(query), len(n), n.lower()),
        )
        suggestions += matches[:limit - len(suggestions)]
    return suggestions
