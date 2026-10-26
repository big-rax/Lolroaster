import asyncio
import sys
from bot.main import main

if __name__ == "__main__":
    # Windows consoles default to cp1252, which can't print emoji or many usernames and would crash logging
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    asyncio.run(main())
