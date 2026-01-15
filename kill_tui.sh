#!/bin/bash
# Kill any stuck TUI processes

# Find and kill python processes running the TUI/CLI
pids=$(pgrep -f "src.cli watch|src.cli run|run_tui" 2>/dev/null)

if [ -z "$pids" ]; then
    echo "No TUI processes found"
    exit 0
fi

echo "Found TUI processes: $pids"
echo "Killing..."

for pid in $pids; do
    echo "  Killing PID $pid"
    kill -9 "$pid" 2>/dev/null
done

sleep 1
echo "Done"

# Verify they're gone
remaining=$(pgrep -f "src.cli watch|src.cli run|run_tui" 2>/dev/null)
if [ -n "$remaining" ]; then
    echo "Warning: Some processes still running: $remaining"
fi
