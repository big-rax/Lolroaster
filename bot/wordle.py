import random
import re
from .store import is_channel_allowed, is_user_opted_in
import discord

from .data import WORDLE_RESPONSES, fresh_wordle_scores


def parse_wordle_summary(raw_content: str) -> dict[str, list[str]]:
    scores = fresh_wordle_scores()
    lines = raw_content.splitlines()

    for line in lines[1:]:
        line = line.strip()
        if not line or ":" not in line:
            continue

        score = None
        for possible_score in scores.keys():
            if possible_score in line:
                score = possible_score
                break

        if score is None:
            continue

        people_part = line.split(":", 1)[1].strip()
        mention_ids = re.findall(r"<@!?(\d+)>", people_part)

        for user_id in mention_ids:
            scores[score].append(user_id)

    return scores


async def handle_wordle_message(message: discord.Message) -> bool:
    if not is_channel_allowed(message.channel.id):
        return
    
    raw_content = message.content
    content = raw_content.lower()

    if "is playing" in content:
        name_part = raw_content.split(" is playing")[0]
        await message.reply(f"{name_part} is getting they wordle on 🤓")
        return True
    
    if "were playing" in content:
        users_part = raw_content.split(" others were playing")[0]
        other_players = users_part[-1]
        single_name = users_part.split(" ")[0]                              #the [] operator just access the first element since split returns a list
        await message.reply(f"{single_name} is racing against {other_players} other players!")
        return True
    
    if "your group" in content:
        wordle_scores = parse_wordle_summary(raw_content)

        for score, user_ids in wordle_scores.items():
            if not user_ids:
                continue

            # filter to only opted-in users
            opted_in_ids = [uid for uid in user_ids if is_user_opted_in(uid)]

            if not opted_in_ids:
                continue

            mentions = [f"<@{user_id}>" for user_id in user_ids]
            mention_text = " ".join(mentions)
            response = random.choice(WORDLE_RESPONSES[score])

            if score == "X/6":
                await message.reply(f"{mention_text} failed 😭. {response}")
            else:
                tries = score.split("/")[0]
                await message.reply(f"{mention_text} made it in {tries}. {response}")
        return True

    return False
