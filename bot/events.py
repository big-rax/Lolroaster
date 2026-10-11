import random

import discord

from .config import WORDLE_BOT_ID
from .triggers import handle_trigger_message
from .wordle import handle_wordle_message
from .store import is_bot_active, is_user_opted_in
from .settings_ui import WelcomeView, WELCOME_TEXT, find_welcome_channel, send_setup_dm


EDIT_RESPONSES = [
    "Caught you editing 😈",
    "🥸",
    "Whatcha editing 🕵️",
    "I know what you are, Light. https://tenor.com/bLgLG.gif",
]


def register_events(client: discord.Client, tree: discord.app_commands.CommandTree) -> None:
    @client.event
    async def on_ready() -> None:
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name="Use /roast toggle if you dare...",
        )
        await client.change_presence(status=discord.Status.online, activity=activity)
        await tree.sync()
        print(f"Logged in as {client.user}", flush=True)

    # Posts the setup prompt when the bot is added to a new server.
    @client.event
    async def on_guild_join(guild: discord.Guild) -> None:
        channel = find_welcome_channel(guild)
        if channel is not None:
            try:
                await channel.send(WELCOME_TEXT, view=WelcomeView())
                return
            except discord.HTTPException as e:
                print(f"Couldn't send welcome message in {guild.name}: {e}", flush=True)

        # Couldn't post in the server, so DM whoever added the bot (or the owner) instead
        reached = await send_setup_dm(guild)
        if reached:
            print(f"Joined {guild.name}: no channel to post in, DMed {reached} instead", flush=True)
        else:
            print(f"Joined {guild.name} but couldn't post anywhere or DM the inviter/owner", flush=True)

    @client.event
    async def on_message(message: discord.Message) -> None:
        if message.author.bot and message.author.id != WORDLE_BOT_ID:
            return

        if isinstance(message.channel, discord.Thread):
            return

        if message.author.id == WORDLE_BOT_ID:
            handled = await handle_wordle_message(message)
            if handled:
                return
        
        if not is_bot_active(str(message.guild.id) if message.guild else None, str(message.channel.id)):
            return
        
        if not is_user_opted_in(str(message.author.id)):
            return
        
        await handle_trigger_message(message)

    @client.event
    async def on_message_edit(before: discord.Message, after: discord.Message) -> None:
        if after.author.id == WORDLE_BOT_ID:
            return

        if isinstance(after.channel, discord.Thread):
            return

        if after.author.bot:
            return

        if before.content == after.content:
            return
        
        if not is_bot_active(str(after.guild.id) if after.guild else None, str(after.channel.id)):
            return
        
        if not is_user_opted_in(str(after.author.id)):
            return

        await after.reply(random.choice(EDIT_RESPONSES))
