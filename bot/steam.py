from __future__ import annotations

import re

import aiohttp

from .config import STEAM_API_KEY

API = "https://api.steampowered.com"
TIMEOUT = aiohttp.ClientTimeout(total=10)


async def _get(path: str, **params) -> dict:
    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        async with session.get(f"{API}/{path}", params={"key": STEAM_API_KEY, **params}) as resp:
            resp.raise_for_status()
            return (await resp.json()).get("response", {})


# Accepts a SteamID64, a profile URL (/profiles/<id> or /id/<name>), or a custom URL name.
# Returns the SteamID64, or None if it doesn't match a Steam account.
async def resolve_steam_id(text: str) -> str | None:
    text = text.strip().rstrip("/")
    if match := re.search(r"steamcommunity\.com/profiles/(\d{17})", text):
        return match.group(1)
    if re.fullmatch(r"\d{17}", text):
        return text
    if match := re.search(r"steamcommunity\.com/id/([^/?#]+)", text):
        text = match.group(1)
    response = await _get("ISteamUser/ResolveVanityURL/v1/", vanityurl=text)
    return response.get("steamid") if response.get("success") == 1 else None


# Returns {"name": persona name, "public": bool}, or None if the account doesn't exist.
async def get_profile(steam_id: str) -> dict | None:
    players = (await _get("ISteamUser/GetPlayerSummaries/v2/", steamids=steam_id)).get("players", [])
    if not players:
        return None
    return {"name": players[0]["personaname"], "public": players[0].get("communityvisibilitystate") == 3}


# Returns the user's games as {lowercased name: {"two_weeks": minutes, "forever": minutes}}.
# Empty when their game details are private.
async def get_owned_games(steam_id: str) -> dict[str, dict]:
    response = await _get(
        "IPlayerService/GetOwnedGames/v1/",
        steamid=steam_id, include_appinfo=1, include_played_free_games=1,
    )
    return {
        game["name"].lower(): {
            "two_weeks": game.get("playtime_2weeks", 0),
            "forever": game.get("playtime_forever", 0),
        }
        for game in response.get("games", [])
        if game.get("name")
    }
