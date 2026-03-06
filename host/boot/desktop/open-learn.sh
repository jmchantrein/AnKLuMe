#!/bin/bash
# Open the anklume learn platform in a browser.
# Called from bash_profile BEFORE KDE starts (runs in background).
# Waits for KDE compositor, starts the host web server, opens browser.

[ -f ~/.anklume/welcome-done ] && exit 0

PORT=8890
URL="http://localhost:$PORT"

# Wait for KDE compositor to be ready
for _ in $(seq 1 60); do
    pgrep -x kwin_wayland >/dev/null 2>&1 && break
    sleep 1
done
sleep 3  # Let plasmashell stabilize

# Start the host bootstrap web server (landing page)
python3 /opt/anklume/scripts/platform_server.py --port "$PORT" \
    >/dev/null 2>&1 &
SERVER_PID=$!
disown

# Wait for server to be reachable
for _ in $(seq 1 20); do
    curl -s --max-time 1 "$URL" >/dev/null 2>&1 && break
    sleep 1
done

# Open browser (Wayland env is available — KDE is running)
xdg-open "$URL" 2>/dev/null || firefox-esr "$URL" 2>/dev/null &

# Mark as done so it doesn't reopen on next login
mkdir -p ~/.anklume
touch ~/.anklume/welcome-done
