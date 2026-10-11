from __future__ import annotations
import os
import psycopg
from . import config  # noqa: F401  (loads .env so DATABASE_URL is set)

DATABASE_URL = os.getenv("DATABASE_URL")

_conn: psycopg.Connection | None = None

# Returns a shared autocommit connection to Neon, reconnecting if it was dropped
# (Neon scales idle computes to zero, which closes open connections).
def _get_conn() -> psycopg.Connection:
    global _conn
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set. Run `neon link` or add it to .env.")
    if _conn is None or _conn.closed or _conn.broken:
        # prepare_threshold=None disables server-side prepared statements, which the
        # pooled (PgBouncer) endpoint doesn't need.
        _conn = psycopg.connect(DATABASE_URL, autocommit=True, prepare_threshold=None)
    return _conn

# Runs a query, retrying once on a fresh connection if the old one went stale.
def _execute(query: str, params: tuple = ()) -> psycopg.Cursor:
    try:
        return _get_conn().execute(query, params)
    except psycopg.OperationalError:
        global _conn
        _conn = None
        return _get_conn().execute(query, params)

# Creates the three DB tables if they don't already exist: riot_links (linked accounts),
# allowed_channels (channels the bot can operate in), and opted_in_users (opt-in list).
def init_db() -> None:
    _execute("""
        CREATE TABLE IF NOT EXISTS riot_links (
            discord_id TEXT PRIMARY KEY,
            puuid TEXT NOT NULL,
            game_name TEXT NOT NULL,
            tag_line TEXT NOT NULL
        )
    """)
    _execute("""
        CREATE TABLE IF NOT EXISTS allowed_channels (
            channel_id TEXT PRIMARY KEY,
            guild_id TEXT NOT NULL
        )
    """)
    _execute("""
        CREATE TABLE IF NOT EXISTS opted_in_users (
            discord_id TEXT PRIMARY KEY
        )
    """)
    # Per-server bot switch. mode is 'all' (every channel) or 'specific' (allowed_channels only).
    # Servers without a row behave as enabled + 'specific', matching the original behavior.
    _execute("""
        CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id TEXT PRIMARY KEY,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            mode TEXT NOT NULL DEFAULT 'specific' CHECK (mode IN ('all', 'specific'))
        )
    """)

# Saves a server's bot settings. mode is ignored by the bot while enabled is False.
def set_guild_settings(guild_id: str, enabled: bool, mode: str = "specific") -> None:
    _execute("""
        INSERT INTO guild_settings (guild_id, enabled, mode)
        VALUES (%s, %s, %s)
        ON CONFLICT (guild_id) DO UPDATE SET
            enabled = excluded.enabled,
            mode = excluded.mode
    """, (guild_id, enabled, mode))

# Returns a server's settings as {"enabled": bool, "mode": str}, with defaults if none are saved.
def get_guild_settings(guild_id: str) -> dict:
    row = _execute(
        "SELECT enabled, mode FROM guild_settings WHERE guild_id = %s", (guild_id,)
    ).fetchone()
    if row:
        return {"enabled": row[0], "mode": row[1]}
    return {"enabled": True, "mode": "specific"}

# Replaces a server's allowed channel list with exactly the given channels.
def set_allowed_channels(guild_id: str, channel_ids: list[str]) -> None:
    with _get_conn().transaction():
        _execute("DELETE FROM allowed_channels WHERE guild_id = %s", (guild_id,))
        for channel_id in channel_ids:
            _execute("""
                INSERT INTO allowed_channels (channel_id, guild_id)
                VALUES (%s, %s)
                ON CONFLICT (channel_id) DO UPDATE SET guild_id = excluded.guild_id
            """, (channel_id, guild_id))

# Returns True if the bot should interact in this channel, based on the server's settings:
# off -> never, 'all' -> always, 'specific' (or no settings saved) -> only allowed channels.
def is_bot_active(guild_id: str | None, channel_id: str) -> bool:
    if guild_id is None:
        return False  # DMs
    row = _execute("""
        SELECT g.enabled, g.mode,
               EXISTS (SELECT 1 FROM allowed_channels WHERE channel_id = %s)
        FROM (SELECT %s::text AS guild_id) q
        LEFT JOIN guild_settings g USING (guild_id)
    """, (channel_id, guild_id)).fetchone()
    enabled, mode, channel_allowed = row
    if enabled is False:
        return False
    if mode == "all":
        return True
    return channel_allowed

# Returns a list of all allowed channel IDs for a given server (guild).
def get_allowed_channels(guild_id: str) -> list:
    rows = _execute(
        "SELECT channel_id FROM allowed_channels WHERE guild_id = %s", (guild_id,)
    ).fetchall()
    return [row[0] for row in rows]

# Saves a Discord user's linked Riot account. If the user already has a link, it overwrites it.
def save_link(discord_id: str, puuid: str, game_name: str, tag_line: str) -> None:
    _execute("""
        INSERT INTO riot_links (discord_id, puuid, game_name, tag_line)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (discord_id) DO UPDATE SET
            puuid = excluded.puuid,
            game_name = excluded.game_name,
            tag_line = excluded.tag_line
    """, (discord_id, puuid, game_name, tag_line))

# Returns the Riot account info linked to a Discord user, or None if they haven't linked one.
def get_link(discord_id: str) -> dict | None:
    row = _execute(
        "SELECT puuid, game_name, tag_line FROM riot_links WHERE discord_id = %s",
        (discord_id,)
    ).fetchone()
    if row:
        return {"puuid": row[0], "game_name": row[1], "tag_line": row[2]}
    return None

# Toggles a user's opt-in status. If they were opted in they are removed, and vice versa.
# Returns True if the user is now opted in, False if they are now opted out.
def toggle_user_opt_in(discord_id: str) -> bool:
    deleted = _execute(
        "DELETE FROM opted_in_users WHERE discord_id = %s", (discord_id,)
    ).rowcount
    if deleted:
        return False  # opted out
    _execute(
        "INSERT INTO opted_in_users (discord_id) VALUES (%s) ON CONFLICT DO NOTHING",
        (discord_id,)
    )
    return True  # opted in

# Returns True if the user is currently opted in to bot interactions, False otherwise.
def is_user_opted_in(discord_id: str) -> bool:
    row = _execute(
        "SELECT 1 FROM opted_in_users WHERE discord_id = %s", (discord_id,)
    ).fetchone()
    return row is not None

# Returns every linked Riot account across all users as a list of dicts.
def get_all_links() -> list[dict]:
    rows = _execute(
        "SELECT discord_id, puuid, game_name, tag_line FROM riot_links"
    ).fetchall()
    return [
        {"discord_id": r[0], "puuid": r[1], "game_name": r[2], "tag_line": r[3]}
        for r in rows
    ]
