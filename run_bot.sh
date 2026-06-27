#!/bin/bash

# Kill any leftover bot instances from previous runs before starting
pkill -f "python run_bot.py" 2>/dev/null
sleep 0.5

# Start the bot in the background and capture its PID
python run_bot.py &
BOT_PID=$!

# On Ctrl+C or kill, shut down the bot and any stale copies
cleanup() {
    echo ""
    echo "Shutting down bot..."
    kill -SIGINT "$BOT_PID" 2>/dev/null  # send SIGINT first (cleaner shutdown)
    sleep 1
    kill -9 "$BOT_PID" 2>/dev/null       # force kill if still running
    pkill -f "python run_bot.py" 2>/dev/null
    wait "$BOT_PID" 2>/dev/null
    exit 0
}

trap cleanup SIGINT SIGTERM

# Block here so the trap fires on Ctrl+C
wait "$BOT_PID"
