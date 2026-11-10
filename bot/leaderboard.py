from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from typing import Any, Callable
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, available_timezones

import discord
from discord import app_commands

from .activities import tracked_games
from .events import find_announce_channel
from .store import (
    get_guild_settings, get_opted_in_ids, get_recording_start, get_sessions_between,
    set_leaderboard_enabled, set_leaderboard_last_week, set_leaderboard_tz,
)

DEFAULT_TZ = "America/Los_Angeles"
CHECK_EVERY = 5 * 60  # seconds between checks for servers whose week just ended
# Relaunching a game within this long (crash, restart, the bot reconnecting) counts as the same session
MERGE_GAP = timedelta(minutes=10)
NIGHT_HOURS = (0, 6)  # local hours that count as late night: midnight to 6am
TOP_N = 3
# Tracked, but left off the board for now. League is WIP until there's a Riot API key that doesn't expire.
WIP_GAMES = {"league of legends"}
# Tracked activities that aren't games, so they don't count as time played
NOT_GAMES = {"neovim"}

# A roast for whoever tops each category. One is picked at random.
CAPTIONS = {
    "hours": ["Go outside.", "The chair has a permanent imprint now.", "This is a full-time job at this point."],
    "launches": ["Can't commit to anything, not even a game.", "Alt-F4 speedrun."],
    "longest": ["Hydrate. Please.", "Did they even get up?"],
    "night": ["Sleep is for the weak, apparently.", "Work tomorrow? Never heard of it."],
    "jump": ["Whatever happened this week, are you ok?", "Relapse of the week."],
}
MEDALS = ["🥇", "🥈", "🥉"]

Interval = tuple[datetime, datetime]


@dataclass
class PlayerWeek:
    played: timedelta = timedelta(0)
    by_game: dict[str, timedelta] = field(default_factory=dict)
    launches: int = 0
    longest: timedelta = timedelta(0)
    longest_game: str | None = None
    night: timedelta = timedelta(0)


def _merge(intervals: list[Interval], gap: timedelta = timedelta(0)) -> list[Interval]:
    merged: list[Interval] = []
    for start, end in sorted(intervals):
        if merged and start - merged[-1][1] <= gap:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


# How much of the interval falls inside [start, end).
def _overlap(interval: Interval, start: datetime, end: datetime) -> timedelta:
    return max(timedelta(0), min(interval[1], end) - max(interval[0], start))


# How much of the interval falls in late-night hours, local to tz.
def _night_overlap(interval: Interval, tz: ZoneInfo) -> timedelta:
    total = timedelta(0)
    day = interval[0].astimezone(tz).date()
    while day <= interval[1].astimezone(tz).date():
        total += _overlap(interval, _local_midnight(day, tz, NIGHT_HOURS[0]), _local_midnight(day, tz, NIGHT_HOURS[1]))
        day += timedelta(days=1)
    return total


# Works out each player's stats for [start, end) from (discord_id, game_name, started_at, ended_at) rows.
# Sessions still going (ended_at None) count up to now.
def summarize(rows: list[tuple], start: datetime, end: datetime, tz: ZoneInfo, now: datetime) -> dict[str, PlayerWeek]:
    sessions: dict[str, dict[str, list[Interval]]] = {}
    names: dict[str, str] = {}
    for discord_id, game, started, ended in rows:
        sessions.setdefault(discord_id, {}).setdefault(game.lower(), []).append((started, ended or now))
        names[game.lower()] = game

    players = {}
    for discord_id, games in sessions.items():
        player = PlayerWeek()
        for key, intervals in games.items():
            played = sum((_overlap(i, start, end) for i in _merge(intervals)), timedelta(0))
            if played:
                player.by_game[names[key]] = played
            for session in _merge(intervals, MERGE_GAP):
                if start <= session[0] < end:
                    player.launches += 1
                length = _overlap(session, start, end)
                if length > player.longest:
                    player.longest, player.longest_game = length, names[key]
        # Two games open at once only counts once toward total and late-night time
        for interval in _merge([i for intervals in games.values() for i in intervals]):
            player.played += _overlap(interval, start, end)
            clipped = (max(interval[0], start), min(interval[1], end))
            if clipped[0] < clipped[1]:
                player.night += _night_overlap(clipped, tz)
        if player.played:
            players[discord_id] = player
    return players


# "24m" under an hour, "4.9h" from there up
def _hours(t: timedelta) -> str:
    minutes = round(t.total_seconds() / 60)
    if minutes < 60:
        return f"{minutes}m"
    return f"{t.total_seconds() / 3600:.1f}h"


# A stat the board ranks: key (for captions), title, each player's value, and how a value is shown.
@dataclass
class Category:
    key: str
    title: str
    value: Callable[[str], Any]
    text: Callable[[str, Any], str]
    zero: Any = 0


# The stats the board ranks. last is the week before, or None if recording didn't cover it.
def categories(this: dict[str, PlayerWeek], last: dict[str, PlayerWeek] | None) -> list[Category]:
    stats = [
        Category(
            "hours", "⏱️ Most hours played", lambda uid: this[uid].played,
            lambda uid, v: f"**{_hours(v)}** (mostly {max(this[uid].by_game, key=this[uid].by_game.get)})",
            timedelta(0),
        ),
        Category(
            "launches", "🚀 Most launches", lambda uid: this[uid].launches,
            lambda uid, v: f"**{v}** {'launch' if v == 1 else 'launches'}",
        ),
        Category(
            "longest", "🪑 Longest session", lambda uid: this[uid].longest,
            lambda uid, v: f"**{_hours(v)}** of {this[uid].longest_game}" if v else "**0m**",
            timedelta(0),
        ),
        Category(
            "night", "🌙 Night owl (12am to 6am)", lambda uid: this[uid].night,
            lambda uid, v: f"**{_hours(v)}**", timedelta(0),
        ),
    ]
    if last is not None:
        def change(uid):
            return this[uid].played - (last[uid].played if uid in last else timedelta(0))
        stats.append(Category(
            "jump", "📈 Biggest jump from last week", change,
            lambda uid, v: f"**{'+' if v >= timedelta(0) else '-'}{_hours(abs(v))}** "
                           f"({_hours(this[uid].played - v)} → {_hours(this[uid].played)})",
            timedelta(0),
        ))
    return stats


# Every player who played this week, best first, as [(discord_id, text)]. With top_only, just the top
# few who scored above zero (a drop from last week doesn't earn a spot on the overview).
def ranking(this: dict[str, PlayerWeek], category: Category, top_only: bool = False) -> list[tuple[str, str]]:
    ranked = sorted(this, key=category.value, reverse=True)
    if top_only:
        ranked = [uid for uid in ranked if category.value(uid) > category.zero][:TOP_N]
    return [(uid, category.text(uid, category.value(uid))) for uid in ranked]


def _place(i: int) -> str:
    return MEDALS[i] if i < len(MEDALS) else f"`{i + 1}.`"


def server_tz(settings: dict) -> ZoneInfo:
    return ZoneInfo(settings["leaderboard_tz"] or DEFAULT_TZ)


# Monday of the week that contains `when`, in the server's timezone.
def week_monday(when: datetime, tz: ZoneInfo) -> date:
    local = when.astimezone(tz).date()
    return local - timedelta(days=local.weekday())


def _local_midnight(day: date, tz: ZoneInfo, hour: int = 0) -> datetime:
    # In UTC, since Python subtracts two times in the same zone by clock time, which ignores DST changes
    return datetime.combine(day, time(hour), tz).astimezone(timezone.utc)


def _week_bounds(monday: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    return _local_midnight(monday, tz), _local_midnight(monday + timedelta(days=7), tz)


# Games that count on this server's board: what it tracks, minus WIP games and non-games.
def _counted_games(guild_id: int) -> set[str]:
    return set(tracked_games(guild_id)) - WIP_GAMES - NOT_GAMES


# Page 0 is the overview (top 3 of every stat), then each stat gets a page ranking everyone who played.
# Returns (embed, page count) for the week starting on `monday`, or None if no opted-in member played
# anything. A page past the end shows the last page, since stats nobody scored in are left out.
def build_leaderboard(
    guild: discord.Guild, monday: date, so_far: bool = False, page: int = 0
) -> tuple[discord.Embed, int] | None:
    settings = get_guild_settings(str(guild.id))
    tz = server_tz(settings)
    start, end = _week_bounds(monday, tz)
    last_start, _ = _week_bounds(monday - timedelta(days=7), tz)
    opted_in = get_opted_in_ids()
    members = [str(m.id) for m in guild.members if not m.bot and str(m.id) in opted_in]
    games = _counted_games(guild.id)
    rows = [r for r in get_sessions_between(members, last_start, end) if r[1].lower() in games]

    now = datetime.now(timezone.utc)
    this = summarize(rows, start, end, tz, now)
    if not this:
        return None
    # Only compare with last week if the bot was recording for all of it
    recording_start = get_recording_start()
    covered = recording_start is not None and recording_start <= last_start
    last = summarize(rows, last_start, start, tz, now) if covered else None
    stats = [c for c in categories(this, last) if ranking(this, c, top_only=True)]
    pages = 1 + len(stats)
    page = max(0, min(page, pages - 1))

    sunday = monday + timedelta(days=6)
    dates = f"{monday:%b} {monday.day} to {sunday:%b} {sunday.day} ({tz.key} time)"
    title = "📊 This week so far" if so_far else "📊 Weekly leaderboard"
    if page == 0:
        embed = discord.Embed(title=title, description=dates, color=discord.Color.gold())
        for category in stats:
            entries = ranking(this, category, top_only=True)
            lines = [f"{_place(i)} <@{uid}> {text}" for i, (uid, text) in enumerate(entries)]
            if not so_far:
                # Seeded by week so the caption stays the same when flipping back to this page
                caption = random.Random(f"{monday}{category.key}").choice(CAPTIONS[category.key])
                lines.append(f"-# {caption}")
            embed.add_field(name=category.title, value="\n".join(lines), inline=False)
    else:
        # The description fits far more than a field, so a whole server's ranking goes there
        category = stats[page - 1]
        lines = [f"{_place(i)} <@{uid}> {text}" for i, (uid, text) in enumerate(ranking(this, category))]
        embed = discord.Embed(
            title=f"{title}: {category.title}", description=f"{dates}\n\n" + "\n".join(lines),
            color=discord.Color.gold(),
        )
    embed.set_footer(text="Only opted-in players are ranked. 🚧 League of Legends is WIP and not counted yet")
    return embed, pages


# An arrow that flips the leaderboard to `page`. The week, page and mode live in the custom_id, so arrows
# on old posts keep working after a restart; main.py registers this with client.add_dynamic_items().
class LeaderboardPageButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"lolroaster:lb:(?P<monday>\d{8}):(?P<page>\d+):(?P<mode>[tw]):(?P<arrow>[lr])",
):
    def __init__(self, monday: date, page: int, so_far: bool, arrow: str, disabled: bool = False):
        super().__init__(discord.ui.Button(
            emoji="◀️" if arrow == "l" else "▶️", style=discord.ButtonStyle.secondary, disabled=disabled,
            custom_id=f"lolroaster:lb:{monday:%Y%m%d}:{page}:{'t' if so_far else 'w'}:{arrow}",
        ))
        self.monday, self.page, self.so_far = monday, page, so_far

    @classmethod
    async def from_custom_id(
        cls, interaction: discord.Interaction, item: discord.ui.Button, match
    ) -> LeaderboardPageButton:
        monday = datetime.strptime(match["monday"], "%Y%m%d").date()
        return cls(monday, int(match["page"]), match["mode"] == "t", match["arrow"])

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        result = build_leaderboard(interaction.guild, self.monday, self.so_far, self.page)
        if result is None:
            await interaction.response.send_message("There's nothing on this leaderboard anymore.", ephemeral=True)
            return
        embed, pages = result
        page = max(0, min(self.page, pages - 1))
        await interaction.response.edit_message(embed=embed, view=leaderboard_view(self.monday, self.so_far, page, pages))


# ◀️ page number ▶️ under a leaderboard. Each arrow is greyed out at its end.
def leaderboard_view(monday: date, so_far: bool, page: int, pages: int) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(LeaderboardPageButton(monday, max(page - 1, 0), so_far, "l", disabled=page == 0))
    view.add_item(discord.ui.Button(
        label=f"{page + 1}/{pages}", style=discord.ButtonStyle.secondary, disabled=True,
        custom_id="lolroaster:lb:indicator",
    ))
    view.add_item(LeaderboardPageButton(monday, min(page + 1, pages - 1), so_far, "r", disabled=page >= pages - 1))
    return view


# Posts last week's leaderboard once the server's week has rolled over to Monday.
async def _post_if_due(guild: discord.Guild) -> None:
    settings = get_guild_settings(str(guild.id))
    if not settings["leaderboard_enabled"]:
        return
    current = week_monday(datetime.now(timezone.utc), server_tz(settings))
    last_done = settings["leaderboard_last_week"]
    if last_done is not None and last_done >= current:
        return
    # Marked before posting so a failing post isn't retried every few minutes
    set_leaderboard_last_week(str(guild.id), current)
    if last_done is None:
        return  # first check for this server: its first board is posted when the week in progress ends

    finished = current - timedelta(days=7)
    result = build_leaderboard(guild, finished)
    if result is None:
        print(f"Weekly leaderboard in {guild.name}: skipped, nobody played", flush=True)
        return
    embed, pages = result
    channel = find_announce_channel(guild)
    if channel is None:
        print(f"Weekly leaderboard in {guild.name}: skipped, no channel to post in", flush=True)
        return
    try:
        await channel.send(embed=embed, view=leaderboard_view(finished, False, 0, pages))
        print(f"Weekly leaderboard posted in {guild.name}", flush=True)
    except (discord.Forbidden, discord.HTTPException) as e:
        print(f"Couldn't post weekly leaderboard in {guild.name}: {e}", flush=True)


async def leaderboard_loop(client: discord.Client) -> None:
    await client.wait_until_ready()
    while True:
        for guild in client.guilds:
            try:
                await _post_if_due(guild)
            except Exception as e:
                print(f"Weekly leaderboard check failed in {guild.name}: {e!r}", flush=True)
        await asyncio.sleep(CHECK_EVERY)


# /roast leaderboard show, toggle and timezone.
def register_leaderboard(roast: app_commands.Group) -> None:
    leaderboard = app_commands.Group(name="leaderboard", description="Weekly playtime leaderboard", parent=roast)

    async def _guild_or_reply(interaction: discord.Interaction, admin: bool = False) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message("This command only works in a server I've been added to.", ephemeral=True)
            return False
        if admin and not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("You need the Manage Server permission to change this.", ephemeral=True)
            return False
        return True

    @leaderboard.command(name="show", description="Show this week's standings so far, or last week's results")
    @app_commands.choices(week=[
        app_commands.Choice(name="This week so far", value="this"),
        app_commands.Choice(name="Last week", value="last"),
    ])
    async def show(interaction: discord.Interaction, week: str = "this") -> None:
        if not await _guild_or_reply(interaction):
            return
        await interaction.response.defer()
        settings = get_guild_settings(str(interaction.guild_id))
        monday = week_monday(datetime.now(timezone.utc), server_tz(settings))
        if week == "last":
            monday -= timedelta(days=7)
        result = build_leaderboard(interaction.guild, monday, so_far=week == "this")
        if result is None:
            await interaction.followup.send("Nobody opted in has played anything that counts yet. Suspicious.")
            return
        embed, pages = result
        await interaction.followup.send(embed=embed, view=leaderboard_view(monday, week == "this", 0, pages))

    @leaderboard.command(name="toggle", description="(Admin) Turn the weekly leaderboard post on or off")
    async def toggle(interaction: discord.Interaction) -> None:
        if not await _guild_or_reply(interaction, admin=True):
            return
        enabled = not get_guild_settings(str(interaction.guild_id))["leaderboard_enabled"]
        set_leaderboard_enabled(str(interaction.guild_id), enabled)
        if enabled:
            await interaction.response.send_message(
                "The weekly leaderboard is on. It's posted Monday at midnight in the game ping channel."
            )
        else:
            await interaction.response.send_message("The weekly leaderboard won't be posted anymore.")

    @leaderboard.command(name="timezone", description="(Admin) Set the timezone the leaderboard's weeks follow")
    @app_commands.describe(timezone="e.g. America/New_York. Leave empty to go back to America/Los_Angeles")
    async def set_timezone(interaction: discord.Interaction, timezone: str | None = None) -> None:
        if not await _guild_or_reply(interaction, admin=True):
            return
        if timezone is not None and timezone not in available_timezones():
            await interaction.response.send_message(
                f"`{timezone}` isn't a timezone I know. Pick one from the suggestions.", ephemeral=True
            )
            return
        set_leaderboard_tz(str(interaction.guild_id), timezone)
        await interaction.response.send_message(
            f"Leaderboard weeks now run Monday to Sunday in {timezone or DEFAULT_TZ} time."
        )

    @set_timezone.autocomplete("timezone")
    async def timezone_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        query = current.strip().lower().replace(" ", "_")
        matches = sorted(
            (tz for tz in available_timezones() if query in tz.lower() and "/" in tz),
            key=lambda tz: (not tz.lower().startswith(query), tz),
        )
        return [app_commands.Choice(name=tz, value=tz) for tz in matches[:25]]
