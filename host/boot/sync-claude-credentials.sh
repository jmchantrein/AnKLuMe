#!/bin/bash
# Sync Claude Code OAuth credentials from host to anklume-instance.
#
# Claude Code CLI refreshes tokens interactively but not in -p mode.
# This script copies the host's (fresh) credentials to the container
# so the OpenClaw proxy can call Claude Code without 401 errors.
#
# Run via systemd timer (every 2h) or manually:
#   host/boot/sync-claude-credentials.sh
#
# Install the timer:
#   host/boot/sync-claude-credentials.sh --install
set -euo pipefail

CREDS_FILE="${HOME}/.claude/.credentials.json"
CONTAINER="anklume-instance"
PROJECT="anklume"
DEST="/root/.claude/.credentials.json"

sync_credentials() {
    if [[ ! -f "$CREDS_FILE" ]]; then
        echo "ERROR: $CREDS_FILE not found" >&2
        return 1
    fi

    # Check if token is still valid (skip sync if expired on host too)
    local expires_at
    expires_at=$(python3 -c "
import json, time
with open('$CREDS_FILE') as f:
    d = json.load(f)
oauth = d.get('claudeAiOauth', {})
print(oauth.get('expiresAt', 0))
" 2>/dev/null || echo "0")

    local now_ms
    now_ms=$(python3 -c "import time; print(int(time.time() * 1000))")

    if [[ "$expires_at" -le "$now_ms" ]]; then
        echo "WARN: Host token is also expired. Run 'claude' interactively to refresh." >&2
        return 1
    fi

    # Check container is running
    if ! incus list "$CONTAINER" --project "$PROJECT" --format csv -c s 2>/dev/null | grep -q RUNNING; then
        echo "SKIP: $CONTAINER not running" >&2
        return 0
    fi

    # Push credentials
    incus file push "$CREDS_FILE" "${CONTAINER}${DEST}" --project "$PROJECT"
    echo "OK: Credentials synced to $CONTAINER (expires in $(( (expires_at - now_ms) / 1000 / 60 ))min)"
}

install_timer() {
    local script_path
    script_path=$(realpath "$0")

    sudo tee /etc/systemd/system/anklume-sync-creds.service > /dev/null << EOF
[Unit]
Description=Sync Claude Code credentials to anklume-instance

[Service]
Type=oneshot
User=$USER
ExecStart=$script_path
EOF

    sudo tee /etc/systemd/system/anklume-sync-creds.timer > /dev/null << EOF
[Unit]
Description=Periodic Claude Code credential sync

[Timer]
OnBootSec=5min
OnUnitActiveSec=2h
Persistent=true

[Install]
WantedBy=timers.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable --now anklume-sync-creds.timer
    echo "Timer installed and started (every 2h)"
    systemctl list-timers anklume-sync-creds.timer
}

case "${1:-sync}" in
    --install)
        install_timer
        ;;
    sync|"")
        sync_credentials
        ;;
    *)
        echo "Usage: $0 [--install|sync]"
        echo "  sync       Sync credentials now (default)"
        echo "  --install  Install systemd timer (every 2h)"
        exit 1
        ;;
esac
