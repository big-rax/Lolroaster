import sqlite3
import os
from .config import BASE_DIR

DB_PATH = os.path.join(BASE_DIR, "riot_links.db")

# Creates the three DB tables if they don't already exist: riot_links (linked accounts),
# allowed_channels (channels the bot can operate in), and opted_in_users (opt-in list).
def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS riot_links (
                discord_id TEXT PRIMARY KEY,
                puuid TEXT NOT NULL,
                game_name TEXT NOT NULL,
                tag_line TEXT NOT NULL
            )
        """)
        conn.execute("""
                CREATE TABLE IF NOT EXISTS allowed_channels (
                     channel_id TEXT PRIMARY KEY,
                     guild_id TEXT NOT NULL
                    )
                """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS opted_in_users (
                discord_id TEXT PRIMARY KEY
            )
        """)

# Adds a channel to the allowed list for the bot to operate in. Silently ignores duplicates.
def add_allowed_channel(channel_id: str, guild_id: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
                INSERT OR IGNORE INTO allowed_channels (channel_id, guild_id)
                VALUES (?, ?)
                """, (channel_id, guild_id))
        print(f"Added channel {channel_id} to allowed channels",)

# Removes a channel from the allowed list so the bot will no longer operate in it.
def remove_allowed_channel(channel_id: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM allowed_channels WHERE channel_id = ?", (channel_id,))

# Returns True if the given channel is in the allowed list, False otherwise.
def is_channel_allowed(channel_id: str) -> bool:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT channel_id FROM allowed_channels").fetchall()
        row = conn.execute(
            "SELECT 1 FROM allowed_channels WHERE channel_id = ?", (channel_id,)
        ).fetchone()
    return row is not None

# Returns a list of all allowed channel IDs for a given server (guild).
def get_allowed_channels(guild_id: str) -> list:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT channel_id FROM allowed_channels WHERE guild_id = ?", (guild_id,)
        ).fetchall()
    return [row[0] for row in rows]

# Saves a Discord user's linked Riot account. If the user already has a link, it overwrites it.
def save_link(discord_id: str, puuid: str, game_name: str, tag_line: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            INSERT INTO riot_links (discord_id, puuid, game_name, tag_line)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(discord_id) DO UPDATE SET
                puuid=excluded.puuid,
                game_name=excluded.game_name,
                tag_line=excluded.tag_line
        """, (discord_id, puuid, game_name, tag_line))

# Returns the Riot account info linked to a Discord user, or None if they haven't linked one.
def get_link(discord_id: str) -> dict | None:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT puuid, game_name, tag_line FROM riot_links WHERE discord_id = ?",
            (discord_id,)
        ).fetchone()
    if row:
        return {"puuid": row[0], "game_name": row[1], "tag_line": row[2]}
    return None

# Toggles a user's opt-in status. If they were opted in they are removed, and vice versa.
# Returns True if the user is now opted in, False if they are now opted out.
def toggle_user_opt_in(discord_id: str) -> bool:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT 1 FROM opted_in_users WHERE discord_id = ?", (discord_id,)
        ).fetchone()
        if row is not None:
            conn.execute("DELETE FROM opted_in_users WHERE discord_id = ?", (discord_id,))
            return False  # opted out
        else:
            conn.execute("INSERT INTO opted_in_users (discord_id) VALUES (?)", (discord_id,))
            return True  # opted in

# Returns True if the user is currently opted in to bot interactions, False otherwise.
def is_user_opted_in(discord_id: str) -> bool:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT 1 FROM opted_in_users WHERE discord_id = ?", (discord_id,)
        ).fetchone()
    return row is not None

# Returns every linked Riot account across all users as a list of dicts.
def get_all_links() -> list[dict]:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT discord_id, puuid, game_name, tag_line FROM riot_links"
        ).fetchall()
    return [
        {"discord_id": r[0], "puuid": r[1], "game_name": r[2], "tag_line": r[3]}
        for r in rows
    ]
