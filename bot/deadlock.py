from __future__ import annotations

import random
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
# Messages by event and party size: "solo" (1), "duo" (2), "stack" (3-5) or "full" (6).
# {hero} becomes " as Haze" (or nothing if the hero isn't known) and {size} the party size.
# One of each list is picked at random.
PARTY_MESSAGES = {
    "queue": {
        "solo": ["is queuing up for Deadlock{hero} solo. Nobody wanted to play with them 😔"],
        "duo": ["is duo queuing Deadlock{hero}. Double the feeding"],
        "stack": ["is queuing Deadlock{hero} with a party of {size}"],
        "full": ["is queuing Deadlock{hero} with a full 6-stack. Somebody's getting cooked"],
    },
    "match": {
        "solo": ["just started a 6v6 Deadlock match{hero}, solo. Praying for their teammates 🙏"],
        "duo": ["just started a 6v6 Deadlock match{hero} with their duo. 😭"],
        "stack": ["just started a 6v6 Deadlock match{hero} with a party of {size}. 😭"],
        "full": ["just started a 6v6 Deadlock match{hero} with a full 6-stack. No excuses this time"],
    },
    "requeue": {
        "solo": ["just finished a 6v6{hero} and is already queuing again, solo 😭"],
        "duo": ["just finished a 6v6{hero} and is already duo queuing again 😭"],
        "stack": ["just finished a 6v6{hero} and the party of {size} is already queuing again 😭"],
        "full": ["just finished a 6v6{hero} and the whole 6-stack is already back in queue 😭"],
    },
}
# Used instead when several party members in the same server are combined into one message.
# {players} becomes e.g. "@zach (Haze), @bobo (Vindicta) and @sam" and starts the message.
GROUP_MESSAGES = {
    "queue": {
        "duo": ["{players} are duo queuing Deadlock. Double the feeding"],
        "stack": ["{players} are queuing Deadlock with a party of {size}"],
        "full": ["{players} are queuing Deadlock as a full 6-stack. Somebody's getting cooked"],
    },
    "match": {
        "duo": ["{players} just started a 6v6 Deadlock match together. 😭"],
        "stack": ["{players} just started a 6v6 Deadlock match in a party of {size}. 😭"],
        "full": ["{players} just started a 6v6 Deadlock match as a full 6-stack. No excuses this time"],
    },
    "requeue": {
        "duo": ["{players} just finished a 6v6 and are already duo queuing again 😭"],
        "stack": ["{players} just finished a 6v6 and the party of {size} is already queuing again 😭"],
        "full": ["{players} just finished a 6v6 and the whole 6-stack is already back in queue 😭"],
    },
}


# Something worth posting about one player: event is "queue", "requeue" or "match".
@dataclass(frozen=True)
class PartyEvent:
    event: str
    size: int
    hero: str | None

# The mod manager clears the hero when a match loads and the 6v6 mode can be known first, so the match
# ping waits for the hero. If it still isn't known this long after 6v6 was seen, post without it.
HERO_WAIT = 60


@dataclass
class _PlayerState:
    phase: str | None = None  # "queue", "match", "post", "other", or None when not in Deadlock
    match_announced: bool = False
    six_v_six_match: bool = False
    six_v_six_seen_at: float | None = None  # when the current match was first seen as 6v6
    match_hero: str | None = None  # hero in the current (or just finished) match
    last_six_v_six_end: float | None = None
    last_six_v_six_hero: str | None = None
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
    # The hero's name is the small image's hover text, which players can't customize. It's set in matches,
    # queue and post-match (in queue it's the hero they had in the hideout), and cleared in the hideout.
    return activity.small_image_text or None


def _as_hero(hero: str | None) -> str:
    return f" as {hero}" if hero else ""


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
    activity = _mod_manager_activity(member)
    player.match_hero = _hero(activity) if phase == "match" else None
    in_six_v_six = phase == "match" and mode == "6v6"
    player.six_v_six_match = in_six_v_six
    # A match whose mode isn't known yet is left unannounced, so it's still announced once it turns out to be 6v6
    player.match_announced = in_six_v_six


def _bucket(size: int) -> str:
    return "solo" if size <= 1 else "duo" if size == 2 else "full" if size >= 6 else "stack"


# Text that follows the player's mention in a single-player message.
def party_message(event: PartyEvent) -> str:
    template = random.choice(PARTY_MESSAGES[event.event][_bucket(event.size)])
    return template.format(hero=_as_hero(event.hero), size=event.size)


# Full message for several party members. players is [(mention, hero or None)].
def group_message(event: str, size: int, players: list[tuple[str, str | None]]) -> str:
    names = [f"{mention} ({hero})" if hero else mention for mention, hero in players]
    joined = f"{', '.join(names[:-1])} and {names[-1]}"
    template = random.choice(GROUP_MESSAGES[event][_bucket(max(size, len(players)))])
    return template.format(players=joined, size=size)


# Updates what this player is doing in Deadlock and returns anything worth posting about.
def deadlock_updates(member: discord.Member) -> list[PartyEvent]:
    key = (member.guild.id, member.id)
    player = _players.setdefault(key, _PlayerState())
    now = time.monotonic()

    activity = _mod_manager_activity(member)
    phase, mode = _current_phase(member)

    messages = []
    previous = player.phase

    # Leaving a match: remember when a 6v6 ended (and as who) for the requeue check
    if previous == "match" and phase != "match":
        if player.six_v_six_match:
            player.last_six_v_six_end = now
            player.last_six_v_six_hero = player.match_hero
        player.match_announced = False
        player.six_v_six_match = False
        player.six_v_six_seen_at = None
        player.match_hero = None

    if phase == "queue" and previous != "queue":
        size = _party_size(activity)
        requeue = player.last_six_v_six_end is not None and now - player.last_six_v_six_end <= REQUEUE_WINDOW
        if requeue:
            player.last_six_v_six_end = None
            player.last_queue_ping = now
            messages.append(PartyEvent("requeue", size, player.last_six_v_six_hero))
        elif player.last_queue_ping is None or now - player.last_queue_ping >= QUEUE_COOLDOWN:
            player.last_queue_ping = now
            messages.append(PartyEvent("queue", size, _hero(activity)))

    if phase == "match":
        player.match_hero = _hero(activity) or player.match_hero
        # The mode is only worked out a little after the match loads, so check on every update
        if mode == "6v6":
            player.six_v_six_match = True
            if player.six_v_six_seen_at is None:
                player.six_v_six_seen_at = now
        hero_ready = player.match_hero is not None or (
            player.six_v_six_seen_at is not None and now - player.six_v_six_seen_at >= HERO_WAIT
        )
        if player.six_v_six_match and not player.match_announced and hero_ready:
            player.match_announced = True
            if player.last_match_ping is None or now - player.last_match_ping >= MATCH_COOLDOWN:
                player.last_match_ping = now
                messages.append(PartyEvent("match", _party_size(activity), player.match_hero))

    player.phase = phase
    return messages
