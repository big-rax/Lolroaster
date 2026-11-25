from __future__ import annotations

import aiohttp

# Community Deadlock API (deadlock-api.com): free, no key needed, built from Valve's game data but not
# endorsed by Valve. It identifies players by their 32-bit Steam account id.
API = "https://api.deadlock-api.com"
TIMEOUT = aiohttp.ClientTimeout(total=15)
# A SteamID64 minus this is the 32-bit account id the Deadlock API uses
STEAM_ID64_BASE = 76561197960265728
MAX_BATCH = 1000  # the batch rank endpoint takes up to this many accounts per request

# Rank tiers by number (from /v1/assets/ranks). Each has subranks 1-6; tier 0 means unranked.
RANK_NAMES = [
    "Obscurus", "Initiate", "Seeker", "Acolyte", "Sentinel", "Mystic",
    "Ritualist", "Emissary", "Oracle", "Phantom", "Ascendant", "Eternus",
]
RANK_COLORS = [
    0x333333, 0x6A3E1E, 0x882355, 0x5C6DAB, 0x719C47, 0xDDA326,
    0xEE4F57, 0xB47FEB, 0x955138, 0x7C7C7C, 0xC39751, 0x5CE9A9,
]


class DeadlockAPIError(Exception):
    def __init__(self, status: int):
        super().__init__(f"Deadlock API returned HTTP {status}")
        self.status = status


def account_id_from_steam_id(steam_id: str) -> int:
    return int(steam_id) - STEAM_ID64_BASE


# Badge image for a tier and subrank, e.g. Ascendant 4. Unranked has a single image.
def rank_image_url(rank: int, subrank: int) -> str:
    if rank == 0 or subrank == 0:
        return f"https://assets-bucket.deadlock-api.com/assets-api-res/images/ranks/rank{rank:02d}_lg.png"
    return f"{API}/v1/assets/ranks/{rank}/{subrank}/image"


def rank_name(rank: int, subrank: int) -> str:
    if rank == 0 or rank >= len(RANK_NAMES):
        return "Obscurus"
    return f"{RANK_NAMES[rank]} {subrank}" if subrank else RANK_NAMES[rank]


# Each account's rank after its latest ranked match, as {account_id: rank dict}. A rank dict has
# "rank" (tier), "subrank", "badge" and "last_match" (None when the player has no ranked games).
# Accounts protected on deadlock-api.com are missing from the result. Raises DeadlockAPIError on failure.
async def get_ranks(account_ids: list[int]) -> dict[int, dict]:
    ranks: dict[int, dict] = {}
    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        for i in range(0, len(account_ids), MAX_BATCH):
            batch = ",".join(str(a) for a in account_ids[i:i + MAX_BATCH])
            async with session.get(f"{API}/v1/players/rank", params={"account_ids": batch}) as resp:
                if resp.status != 200:
                    raise DeadlockAPIError(resp.status)
                for entry in await resp.json():
                    ranks[entry["account_id"]] = entry
    return ranks


# Orders players best first: by badge, then by rank progress within it.
def rank_sort_key(entry: dict) -> tuple[int, int]:
    last = entry.get("last_match") or {}
    return entry.get("badge", 0), last.get("player_rank_final_flat_progress", 0)


# Turns a Deadlock API failure into a message for the user.
def deadlock_error_message(e: Exception) -> str:
    status = e.status if isinstance(e, DeadlockAPIError) else None
    if status == 429:
        return "The Deadlock API is rate-limiting the bot right now. Try again in a minute."
    if status in (503, 504) or (status is not None and status >= 500):
        return "The Deadlock API is busy or down right now. Try again in a bit."
    if isinstance(e, (aiohttp.ClientError, TimeoutError)):
        return "Couldn't reach the Deadlock API. Try again in a bit."
    return "Something went wrong building the Deadlock leaderboard. Reach out to brax."
