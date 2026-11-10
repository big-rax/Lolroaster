# Lolroaster

A Discord bot for gaming friend groups. Lolroaster links Discord users to their Riot and Steam accounts, shows League ranks and champion mastery, tracks live games as they happen, keeps a server leaderboard, and calls people out when they start playing, with a bit of roasting along the way.

Everything social is opt-in: the bot only reacts to, replies to, or shows the games of people who turn it on with `/roast toggle`.

## Features

New here? Run `/help` in Discord for a quick tour of every command.

### League commands (`/lol`)

| Command | What it does |
| --- | --- |
| `/lol link <game_name> <tag_line>` | Links your Riot ID and shows your level, Solo/Duo rank and a top-3 mastery banner |
| `/lol account` | Shows your linked account with Solo/Duo and Flex ranks |
| `/lol mastery` | Lists your top champion masteries |
| `/lol leaderboard` | Ranks the server's opted-in players by Solo/Duo, then Flex |
| `/lol live` | Posts a live-game card for you or an opted-in player, refreshes it every 60 seconds, and swaps in the final result (win/loss, KDA, duration) when the game ends |
| `/lol lastgame` | Shows the result of the most recent game for you or an opted-in player |

### Roasts

| Command | What it does |
| --- | --- |
| `/roast wordle` | Roasts the players from a Wordle group result |

### Game activity pings

When an opted-in member starts playing a tracked game, the bot posts a ping, mentioning their recent playtime when it's high. League of Legends, Deadlock and Neovim are tracked by default, and Deadlock matches get live updates through Deadlock Mod Manager's presence.

| Command | What it does |
| --- | --- |
| `/roast game add` / `remove` / `list` | Chooses which games trigger pings in the server |
| `/roast game channel` | (Admin) Picks the channel pings are posted in |
| `/steam link` / `unlink` | Links your Steam account so playtime numbers come from Steam |

### Opt-in and server settings

| Command | What it does |
| --- | --- |
| `/roast toggle` | Opts you in or out of bot interactions |
| `/roast toggle-user <user>` | (Admin) Opts a user out |
| `/settings` | (Manage Server) Turns the bot on or off for the server and picks which channels it talks in |
| `/channel list` | Lists the channels the bot is allowed to talk in |

When the bot joins a server, it posts a setup prompt. If it can't post anywhere, it DMs whoever added it (or the server owner) instead.

### Chat reactions

In allowed channels and for opted-in users, the bot:

- reacts to trigger words
- calls out edited messages
- comments on results from the Wordle bot

## Tech stack

- **Python** with [discord.py](https://github.com/Rapptz/discord.py): slash commands, buttons, select menus and Components V2 layouts
- **Riot Games API** through [Pyke](https://pypi.org/project/pyke-lol/), with Data Dragon for champion data and images
- **Steam Web API** for linked accounts and playtime
- **PostgreSQL** on [Neon](https://neon.com), accessed with psycopg
- **Pillow** for the generated mastery banners
- **asyncio** for concurrent API calls and background tasks (live-game polling, playtime tracking)

## Project layout

```
run_bot.py          entry point
run_bot.sh          start script: picks the right Python, clears stale instances, shuts down cleanly
test_db.py          smoke test for the database layer
bot/
  main.py           builds the Discord client and starts the bot
  config.py         loads environment variables and constants
  commands.py       slash commands and their interactive views
  events.py         message, edit, presence and server-join listeners
  settings_ui.py    /settings flow and new-server onboarding
  store.py          PostgreSQL data layer
  riot_api.py       Riot API and Data Dragon calls, mastery banner
  steam.py          Steam Web API calls
  activities.py     which games trigger pings, per server
  playtime.py       game session and playtime tracking
  deadlock.py       Deadlock match updates from Mod Manager presence
  triggers.py       trigger-word replies
  wordle.py         Wordle bot responses
  data.py           trigger words, GIF links and canned responses
```

## Running it yourself

1. Create a bot in the [Discord Developer Portal](https://discord.com/developers/applications) and turn on the **Message Content**, **Server Members** and **Presence** intents.
2. Get a Riot API key from the [Riot Developer Portal](https://developer.riotgames.com) and a [Steam Web API key](https://steamcommunity.com/dev/apikey).
3. Create a PostgreSQL database. Any Postgres works; this project uses Neon.
4. Add a `.env` file in the project root:

   ```
   DISCORD_TOKEN=your-discord-bot-token
   RIOT_API_KEY=your-riot-api-key
   STEAM_API_KEY=your-steam-api-key
   DATABASE_URL=postgresql://user:password@host/dbname
   ```

5. Install dependencies and start the bot. Tables are created automatically on first run.

   ```bash
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ./run_bot.sh
   ```

Riot lookups use the NA region.

## Testing

`python test_db.py` checks every function in the data layer against the database in `DATABASE_URL`. It uses throwaway IDs and deletes them when it finishes.
