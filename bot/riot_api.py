from pyke import Continent, Region, Pyke, DataDragon
import aiohttp

async def get_account_info(api: Pyke, game_name:str, tag_line:str) -> dict | None:
    try:
        account = await api.account.by_riot_id(Continent.AMERICAS, game_name, tag_line) #game_name is really the players in game username
        summoner = await api.summoner.by_puuid(Region.NA, account["puuid"])
        entries = await api.league.by_puuid(Region.NA, account["puuid"]) #summoner.id contains a lot of info about the summoner, such as level
        
        rank_info = None
        for entry in entries:
            if entry["queueType"] == "RANKED_SOLO_5x5":
                rank_info = entry
                break
        
        return {
            "puuid" : account["puuid"],
            "gameName": account["gameName"],
            "tagLine": account["tagLine"],
            "summonerLevel": summoner["summonerLevel"],
            "rank": rank_info,
        }
    except Exception as e:
        print(f"Riot API ERROR: {e}")
        return None
    
async def get_champion_mastery(api: Pyke, ddragon: DataDragon, puuid: str) -> list | None:
    try:
        masteries = await api.champion_mastery.masteries_by_puuid(Region.NA, puuid)
        champions = await ddragon.champion.get_all("en_US")

        result = []
        for mastery in masteries[:3]:
            champ_name = str(mastery["championId"])  # fallback
            for name, data in champions["data"].items():
                if int(data["key"]) == mastery["championId"]:
                    champ_name = name
                    break
            result.append({
                "championName": champ_name,
                "championLevel": mastery["championLevel"],
                "championPoints": mastery["championPoints"],
            })

        return result
    except Exception as e:
        print(f"Riot API ERROR: {e}", flush=True)
        return None
    

async def get_champion_name_map() -> dict | None:
    try:
        async with aiohttp.ClientSession() as session:
            # first get the latest version
            async with session.get("https://ddragon.leagueoflegends.com/api/versions.json") as resp:
                versions = await resp.json()
                latest = versions[0]

            # then fetch champion data for that version
            async with session.get(f"https://ddragon.leagueoflegends.com/cdn/{latest}/data/en_US/champion.json") as resp:
                data = await resp.json()

        # build a dict mapping champion ID (int) to champion name (str)
        champion_map = {}
        for champ_name, champ_data in data["data"].items():
            champion_map[int(champ_data["key"])] = champ_name

        return champion_map
    except Exception as e:
        print(f"Data Dragon ERROR: {e}", flush=True)
        return None

TIER_ORDER = [
    "IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM",
    "EMERALD", "DIAMOND", "MASTER", "GRANDMASTER", "CHALLENGER"
]
DIVISION_ORDER = {"IV": 0, "III": 1, "II": 2, "I": 3}

def rank_sort_key(entry: dict) -> tuple:
    if not entry or "tier" not in entry:
        return (-1, -1, -1)
    tier_index = TIER_ORDER.index(entry["tier"])
    division_index = DIVISION_ORDER.get(entry.get("rank", ""), 0)
    return (tier_index, division_index, entry["leaguePoints"])

# Fetches the current live game for a player by PUUID.
# Returns the full game data dict if in a game, or None if not in one.
async def get_live_game(api: Pyke, puuid: str) -> dict | None:
    try:
        return await api.spectator.by_puuid(Region.NA, puuid)
    except Exception:
        return None

async def get_all_ranks(api: Pyke, puuid: str) -> dict:
    try:
        entries = await api.league.by_puuid(Region.NA, puuid)
        solo = next((e for e in entries if e["queueType"] == "RANKED_SOLO_5x5"), None)
        flex = next((e for e in entries if e["queueType"] == "RANKED_FLEX_SR"), None)
        return {"solo": solo, "flex": flex}
    except Exception as e:
        print(f"Riot API ERROR: {e}", flush=True)
        return {"solo": None, "flex": None}