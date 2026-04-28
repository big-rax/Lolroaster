import sqlite3
import os
from .config import BASE_DIR

DB_PATH = os.path.join(BASE_DIR, "riot_links.db")

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

def get_link(discord_id: str) -> dict | None:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT puuid, game_name, tag_line FROM riot_links WHERE discord_id = ?",
            (discord_id,)
        ).fetchone()
    if row:
        return {"puuid": row[0], "game_name": row[1], "tag_line": row[2]}
    return None