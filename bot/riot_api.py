from pyke import Continent, Region, Pyke

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
