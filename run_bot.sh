#!/bin/bash

# Works on macOS/Linux and on Windows via Git Bash.
# Run from the script's own folder so run_bot.py and .env are found
cd "$(dirname "$0")"

# Prefer the project's virtual environment (.venv) if it exists, otherwise fall back
# to the system Python: Windows usually has "python", macOS only has "python3".
if [ -x .venv/bin/python ]; then
    PYTHON=.venv/bin/python
elif [ -x .venv/Scripts/python.exe ]; then
    PYTHON=.venv/Scripts/python.exe
elif command -v python >/dev/null 2>&1; then
    PYTHON=python
elif command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
else
    echo "Python not found. Install Python 3 and try again."
    exit 1
fi

# Matches "python run_bot.py", "python3 run_bot.py" and ".venv/bin/python run_bot.py"
BOT_PATTERN="python[0-9.]*(\.exe)? run_bot.py"

# Kill any leftover bot instances from previous runs before starting
pkill -f "$BOT_PATTERN" 2>/dev/null
sleep 0.5

# Start the bot in the background and capture its PID
"$PYTHON" run_bot.py &
BOT_PID=$!

# On Ctrl+C or kill, shut down the bot and any stale copies
cleanup() {
    echo ""
    echo "Shutting down bot..."
    kill -SIGINT "$BOT_PID" 2>/dev/null  # send SIGINT first (cleaner shutdown)
    sleep 1
    kill -9 "$BOT_PID" 2>/dev/null       # force kill if still running
    pkill -f "$BOT_PATTERN" 2>/dev/null
    wait "$BOT_PID" 2>/dev/null
    exit 0
}

trap cleanup SIGINT SIGTERM

# Block here so the trap fires on Ctrl+C
wait "$BOT_PID"
