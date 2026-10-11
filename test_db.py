# Smoke test for the Neon Postgres connection and every function in bot/store.py.
# Uses throwaway IDs and deletes them afterwards, so it's safe to run against production.
# Run with: python test_db.py

import uuid
from bot import store

PREFIX = f"test-{uuid.uuid4().hex[:8]}"
USER = f"{PREFIX}-user"
CHANNEL = f"{PREFIX}-channel"
OTHER_CHANNEL = f"{PREFIX}-channel-2"
GUILD = f"{PREFIX}-guild"

passed = 0

def check(name: str, condition: bool) -> None:
    global passed
    if not condition:
        raise AssertionError(f"FAILED: {name}")
    passed += 1
    print(f"  ok  {name}")

def cleanup() -> None:
    store._execute("DELETE FROM riot_links WHERE discord_id = %s", (USER,))
    store._execute("DELETE FROM allowed_channels WHERE guild_id = %s", (GUILD,))
    store._execute("DELETE FROM guild_settings WHERE guild_id = %s", (GUILD,))
    store._execute("DELETE FROM opted_in_users WHERE discord_id = %s", (USER,))

def main() -> None:
    print("Connecting to Neon...")
    version = store._execute("SELECT version()").fetchone()[0]
    print(f"  {version.split(',')[0]}")

    store.init_db()
    tables = {r[0] for r in store._execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
    ).fetchall()}
    check("tables exist", {"riot_links", "allowed_channels", "opted_in_users", "guild_settings"} <= tables)

    try:
        print("Riot links:")
        check("no link before save", store.get_link(USER) is None)
        store.save_link(USER, "puuid-1", "Faker", "KR1")
        check("link saved", store.get_link(USER) == {"puuid": "puuid-1", "game_name": "Faker", "tag_line": "KR1"})
        store.save_link(USER, "puuid-2", "Faker", "T1")
        check("link overwritten", store.get_link(USER)["tag_line"] == "T1")
        check("link in get_all_links", any(l["discord_id"] == USER for l in store.get_all_links()))

        print("Allowed channels:")
        check("no channels initially", store.get_allowed_channels(GUILD) == [])
        store.set_allowed_channels(GUILD, [CHANNEL, CHANNEL])  # duplicate should be ignored
        check("channel listed for guild", store.get_allowed_channels(GUILD) == [CHANNEL])
        store.set_allowed_channels(GUILD, [])
        check("channels cleared", store.get_allowed_channels(GUILD) == [])

        print("Server settings:")
        check("defaults when unset", store.get_guild_settings(GUILD) == {"enabled": True, "mode": "specific"})
        check("unset server uses channel list", not store.is_bot_active(GUILD, CHANNEL))
        check("DMs never active", not store.is_bot_active(None, CHANNEL))
        store.set_allowed_channels(GUILD, [CHANNEL])
        check("specific: allowed channel active", store.is_bot_active(GUILD, CHANNEL))
        check("specific: other channel inactive", not store.is_bot_active(GUILD, OTHER_CHANNEL))
        store.set_allowed_channels(GUILD, [OTHER_CHANNEL])
        check("set_allowed_channels replaces list", store.get_allowed_channels(GUILD) == [OTHER_CHANNEL])
        store.set_guild_settings(GUILD, enabled=True, mode="all")
        check("all: any channel active", store.is_bot_active(GUILD, CHANNEL))
        store.set_guild_settings(GUILD, enabled=False, mode="all")
        check("off: nothing active", not store.is_bot_active(GUILD, OTHER_CHANNEL))

        print("Opt-in:")
        check("not opted in initially", not store.is_user_opted_in(USER))
        check("toggle opts in", store.toggle_user_opt_in(USER) is True)
        check("is opted in", store.is_user_opted_in(USER))
        check("toggle opts out", store.toggle_user_opt_in(USER) is False)
        check("is opted out", not store.is_user_opted_in(USER))
    finally:
        cleanup()

    print(f"\nAll {passed} checks passed.")

if __name__ == "__main__":
    main()
