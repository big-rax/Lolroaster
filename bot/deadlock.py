from __future__ import annotations

import time
from dataclasses import dataclass

import discord

# Deadlock Mod Manager's in-game presence (github.com/deadlock-mod-manager/deadlock-mod-manager,
# packages/deadlock-discord-presence). It reads the game's logs and reports a phase in the text lines.
# Players can customize that text, so detection relies on the default wording; custom text that keeps
# the {mode} placeholder still works for matches.
MOD_MANAGER_APP_ID = 1474302474474094634

QUEUE_DETAILS = "Looking for Match"
QUEUE_STATE = "In Queue"
POST_MATCH = "Post-Match"
# Mode text shown during a match. The mod manager labels every 6v6 as Standard (it can't detect ranked),
# so 6v6 stands in for ranked until it can.
SIX_V_SIX_MODES = ("Playing Standard (6v6)", "Playing Ranked (6v6)")
OTHER_MATCH_MODES = (
    "Playing a Match", "Playing Hero Labs", "Playing in Private Lobby", "Playing Bot Match",
    "Viewing Tutorial", "Training in Sandbox Mode", "Playing Placement Match", "Playing Street Brawl (4v4)",
)

REQUEUE_WINDOW = 5 * 60  # seconds after a 6v6 ends that queueing counts as "back for more"
QUEUE_COOLDOWN = 10 * 60  # queue/cancel/queue again shouldn't ping every time
MATCH_COOLDOWN = 20 * 60  # guards against the presence flickering mid-match


@dataclass
class _PlayerState:
    phase: str | None = None  # "queue", "match", "post", "other", or None when not in Deadlock
    match_announced: bool = False
    six_v_six_match: bool = False
    last_six_v_six_end: float | None = None
    last_queue_ping: float | None = None
    last_match_ping: float | None = None


# (guild_id, user_id) -> state. Presence updates arrive once per shared server, so each server
# follows the player separately, matching how the other activity pings work.
_players: dict[tuple[int, int], _PlayerState] = {}


def _mod_manager_activity(member: discord.Member) -> discord.Activity | None:
    for a in member.activities:
        if isinstance(a, discord.Activity) and a.application_id == MOD_MANAGER_APP_ID:
            return a
    return None


def _party_size(activity: discord.Activity) -> int:
    size = (activity.party or {}).get("size")
    return size[0] if size else 1


def _hero(activity: discord.Activity) -> str | None:
    # During matches the hero's name is the small image's hover text, which players can't customize
    return activity.small_image_text or None


def _read_phase(activity: discord.Activity) -> tuple[str, str | None]:
    text = f"{activity.details or ''} | {activity.state or ''}"
    if QUEUE_DETAILS in text or QUEUE_STATE in text:
        return "queue", None
    for mode in SIX_V_SIX_MODES:
        if mode in text:
            return "match", "6v6"
    for mode in OTHER_MATCH_MODES:
        if mode in text:
            return "match", "other"
    if POST_MATCH in text:
        return "post", None
    return "other", None


def _current_phase(member: discord.Member) -> tuple[str | None, str | None]:
    activity = _mod_manager_activity(member)
    return _read_phase(activity) if activity else (None, None)


# Records what a member is already doing in Deadlock without posting anything. Called at startup
# (and on reconnect) so a queue or match already in progress isn't announced late as if it just began.
def seed_deadlock_state(member: discord.Member) -> None:
    phase, mode = _current_phase(member)
    player = _players.setdefault((member.guild.id, member.id), _PlayerState())
    player.phase = phase
    in_six_v_six = phase == "match" and mode == "6v6"
    player.six_v_six_match = in_six_v_six
    # A match whose mode isn't known yet is left unannounced, so it's still announced once it turns out to be 6v6
    player.match_announced = in_six_v_six


def _party_text(size: int) -> str:
    return "solo" if size <= 1 else f"in a party of {size}"


# Updates what this player is doing in Deadlock and returns any messages to post (text after the mention).
def deadlock_updates(member: discord.Member) -> list[str]:
    key = (member.guild.id, member.id)
    player = _players.setdefault(key, _PlayerState())
    now = time.monotonic()

    activity = _mod_manager_activity(member)
    phase, mode = _current_phase(member)

    messages = []
    previous = player.phase

    # Leaving a match: remember when a 6v6 ended for the requeue check
    if previous == "match" and phase != "match":
        if player.six_v_six_match:
            player.last_six_v_six_end = now
        player.match_announced = False
        player.six_v_six_match = False

    if phase == "queue" and previous != "queue":
        party = _party_text(_party_size(activity))
        requeue = player.last_six_v_six_end is not None and now - player.last_six_v_six_end <= REQUEUE_WINDOW
        if requeue:
            player.last_six_v_six_end = None
            player.last_queue_ping = now
            messages.append(f"just finished a 6v6 and is already queuing again ({party}) 😭")
        elif player.last_queue_ping is None or now - player.last_queue_ping >= QUEUE_COOLDOWN:
            player.last_queue_ping = now
            messages.append(f"is queuing up for Deadlock {party}")

    if phase == "match":
        # The mode is only worked out a little after the match loads, so check on every update
        if mode == "6v6":
            player.six_v_six_match = True
        if mode == "6v6" and not player.match_announced:
            player.match_announced = True
            if player.last_match_ping is None or now - player.last_match_ping >= MATCH_COOLDOWN:
                player.last_match_ping = now
                hero = _hero(activity)
                as_hero = f" as {hero}" if hero else ""
                size = _party_size(activity)
                party = f" with a party of {size}" if size > 1 else ""
                messages.append(f"just started a 6v6 Deadlock match{as_hero}{party}. ")

    player.phase = phase
    return messages
