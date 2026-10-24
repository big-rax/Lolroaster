import random
import re
from datetime import date
from zoneinfo import ZoneInfo
from .store import is_bot_active, is_user_opted_in
import discord

from .data import WORDLE_RESPONSES, fresh_wordle_scores

WORDLE_EPOCH = date(2021, 6, 19)  # Wordle No. 0
WORDLE_TZ = ZoneInfo("America/Los_Angeles")
# The group summary is posted the morning after, so it covers the previous day's puzzle
SUMMARY_DAY_OFFSET = 1


def is_wordle_summary(content: str) -> bool:
    return "your group" in content.lower()


# The Wordle number only appears in the results image, so derive it from when the summary was posted.
def wordle_number_for(message: discord.Message) -> int:
    posted = message.created_at.astimezone(WORDLE_TZ).date()
    return (posted - WORDLE_EPOCH).days - SUMMARY_DAY_OFFSET


def wordle_date(number: int) -> date:
    return date.fromordinal(WORDLE_EPOCH.toordinal() + number)


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


# Builds one roast line per score bucket, mentioning only opted-in players.
def build_wordle_roasts(raw_content: str) -> list[str]:
    roasts = []
    for score, user_ids in parse_wordle_summary(raw_content).items():
        opted_in_ids = [uid for uid in user_ids if is_user_opted_in(uid)]
        if not opted_in_ids:
            continue

        mention_text = " ".join(f"<@{user_id}>" for user_id in opted_in_ids)
        response = random.choice(WORDLE_RESPONSES[score])

        if score == "X/6":
            roasts.append(f"{mention_text} failed 😭. {response}")
        else:
            tries = score.split("/")[0]
            roasts.append(f"{mention_text} made it in {tries}. {response}")
    return roasts


async def handle_wordle_message(message: discord.Message) -> bool:
    if not is_bot_active(str(message.guild.id) if message.guild else None, str(message.channel.id)):
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
    
    if is_wordle_summary(raw_content):
        for roast in build_wordle_roasts(raw_content):
            await message.reply(roast)
        return True

    return False
