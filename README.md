# Lolroaster

A Discord bot for gaming friend groups. Lolroaster links Discord users to their Riot and Steam accounts, shows League ranks and champion mastery, tracks live games as they happen, keeps a server leaderboard and a weekly playtime leaderboard, and calls people out when they start playing, with a bit of roasting along the way.

Everything social is opt-in: the bot only reacts to, replies to, or shows the games of people who turn it on with `/roast toggle`. Run `/help` in Discord for a quick tour, with a page for each category.

## Features

### League of Legends (`/lol`)

| Command | What it does |
| --- | --- |
| `/lol link <game_name> <tag_line>` | Links your Riot ID and shows your level, Solo/Duo rank and a top-3 mastery banner |
| `/lol account` | Shows your linked account with Solo/Duo and Flex ranks |
| `/lol mastery` | Lists your top champion masteries |
| `/lol live` | Posts a live-game card for you or an opted-in player, refreshes it every 60 seconds, and swaps in the final result (win/loss, KDA, duration) when the game ends |
| `/lol lastgame` | Shows the result of the most recent game for you or an opted-in player |
| `/lol leaderboard` | Ranks the server's opted-in players by Solo/Duo, then Flex |

Riot IDs are cleaned of invisible Unicode characters that sneak in when they're copied, and failed lookups explain what went wrong: an expired API key, an account that doesn't exist, a rate limit, or a Riot outage.

### Deadlock (`/deadlock`)

| Command | What it does |
| --- | --- |
| `/deadlock leaderboard` | Ranks the server's opted-in players by Deadlock badge, with each player's rank change and win streak from their last ranked match |

It uses the Steam accounts from `/steam link`, so there's no separate account to link. Ranks come from the community [Deadlock API](https://deadlock-api.com), which needs no API key.

### Roasts and the weekly leaderboard

| Command | What it does |
| --- | --- |
| `/roast wordle` | Roasts the players from a Wordle group result |
| `/roast leaderboard show` | Shows this week's playtime standings, or last week's results |
| `/roast leaderboard toggle` | (Admin) Turns the Monday leaderboard post on or off |
| `/roast leaderboard timezone` | (Admin) Sets the time zone weeks follow (default `America/Los_Angeles`) |

Every Monday at midnight, the bot posts the past week's playtime leaderboard for opted-in players. It ranks:

- most hours played
- most launches
- longest session
- night owl hours (midnight to 6am)
- biggest jump from last week

The first page shows the top 3 for each stat, and a dropdown jumps to any stat's full ranking. League is tracked but left off the board for now, since Riot development API keys expire.

### Game activity pings and Steam

When an opted-in member starts playing a tracked game, the bot posts a ping, mentioning their recent playtime when it's high. League of Legends, Deadlock and Neovim are tracked by default. Deadlock pings group party members into one message, name each player's hero, and update during the match through Deadlock Mod Manager's presence.

| Command | What it does |
| --- | --- |
| `/roast game add` / `remove` / `list` | Chooses which games trigger pings in the server |
| `/roast game channel` | (Admin) Picks the channel pings are posted in |
| `/roast game mentions` | Chooses whether game pings notify you (off by default) |
| `/steam link` / `unlink` | Links your Steam account so playtime numbers come from Steam |

### Opt-in and server settings

| Command | What it does |
| --- | --- |
| `/help` | Shows what the bot can do, with a dropdown for each category |
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
- **[Deadlock API](https://deadlock-api.com)** (community-run) for Deadlock ranks
- **PostgreSQL** on [Neon](https://neon.com), accessed with psycopg
- **Pillow** for the generated mastery banners
- **asyncio** for concurrent API calls and background tasks (live-game polling, playtime tracking, the weekly leaderboard)

## Project layout

```
run_bot.py          entry point
run_bot.sh          start script: picks the right Python, clears stale instances, shuts down cleanly
Procfile            tells Heroku to run the bot as a worker
test_db.py          smoke test for the database layer
bot/
  main.py           builds the Discord client and starts the bot
  config.py         loads environment variables and constants
  commands.py       slash commands and their interactive views
  help.py           /help pages and category dropdown
  events.py         message, edit, presence and server-join listeners
  settings_ui.py    /settings flow and new-server onboarding
  store.py          PostgreSQL data layer
  riot_api.py       Riot API and Data Dragon calls, mastery banner
  steam.py          Steam Web API calls
  activities.py     which games trigger pings, per server
  playtime.py       game session and playtime tracking
  leaderboard.py    weekly playtime leaderboard and its scheduled post
  deadlock.py       Deadlock match updates from Mod Manager presence
  deadlock_api.py   Deadlock API calls for ranks
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

## Hosting on Heroku

The repo is set up to run on Heroku as a background worker (`Procfile`), with the Python version in `.python-version`. One Basic dyno ($7/month) keeps the bot online 24/7; the GitHub Student Developer Pack's Heroku credit ($13/month) covers it. Eco dynos can sleep, so use Basic.

1. Install the [Heroku CLI](https://devcenter.heroku.com/articles/heroku-cli) and log in with `heroku login`.
2. Create the app and force the Python buildpack (`package.json` would otherwise make Heroku treat it as a Node app):

   ```bash
   heroku create your-app-name
   heroku buildpacks:set heroku/python
   ```

3. Set the same values as `.env`. Keep using your existing Postgres (e.g. Neon); don't add Heroku Postgres.

   ```bash
   heroku config:set DISCORD_TOKEN=... RIOT_API_KEY=... STEAM_API_KEY=... DATABASE_URL=...
   ```

4. Deploy, then start one Basic worker. Worker dynos don't start on their own.

   ```bash
   git push heroku main
   heroku ps:type worker=basic
   heroku ps:scale worker=1
   ```

5. Check it logged in with `heroku logs --tail`, then stop any copy running on your own computer so pings aren't posted twice.

Later deploys are just `git push heroku main`. Heroku restarts the bot about once a day; it shuts down cleanly and picks up where it left off.

## Testing

`python test_db.py` checks the core data layer (Riot links, opt-in, and server and channel settings) against the database in `DATABASE_URL`. It uses throwaway IDs and deletes them when it finishes. The newer Steam, playtime and leaderboard tables aren't covered yet.
