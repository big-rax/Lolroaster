Refactored Lolroaster bot

Files:
- run_bot.py: entry point you run instead of the old single-file script
- bot/main.py: builds the Discord client and starts the bot
- bot/config.py: token loading and constants
- bot/commands.py: slash commands
- bot/events.py: event listeners
- bot/triggers.py: normal trigger-word logic
- bot/wordle.py: Wordle-specific parsing and responses
- bot/data.py: trigger/response dictionaries

Notes:
- Keep your .env file in the project root alongside run_bot.py.
- Keep your gifs/ folder in the project root alongside run_bot.py.
- You can keep using your existing run_bot.sh, just point it at run_bot.py instead of Lolroaster.py.
