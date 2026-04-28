import os
import random

import discord

from .config import BASE_DIR
from .data import TRIGGERS


async def handle_trigger_message(message: discord.Message) -> bool:
    content = message.content.lower()

    for word, data in TRIGGERS.items():
        if word not in content:
            continue

        trigger_type = data["type"]

        if trigger_type == "reaction":
            chosen = random.choice(data["responses"])
            await message.add_reaction(chosen)

        elif trigger_type == "reply":
            chosen = random.choice(data["responses"])
            await message.reply(chosen)

        elif trigger_type == "file":
            text = random.choice(data["texts"])
            relative_path = random.choice(data["files"])
            file_path = os.path.join(BASE_DIR, relative_path)
            file = discord.File(file_path)
            await message.reply(content=text, file=file)

        return True

    return False
