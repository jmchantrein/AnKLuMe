#!/usr/bin/env bash
# console.sh — Launch tmux console from anywhere (host or container)
#
# From the host: delegates to console.py inside anklume-instance,
#   then attaches to the tmux session via incus exec.
# From the container: runs console.py directly.
#
# Usage:
#   scripts/console.sh              # Create and attach
#   scripts/console.sh --kill       # Kill existing session first
#   scripts/console.sh --dry-run    # Show config without creating

set -euo pipefail

CONTAINER_NAME="anklume-instance"
SESSION_NAME="anklume"

# Detect if running on the host (not inside a container/VM)
is_on_host() {
    local virt
    virt="$(systemd-detect-virt 2>/dev/null)" || true
    [[ "$virt" == "none" ]]
}

if is_on_host; then
    # ── Running on the host ──────────────────────────────
    # Check anklume-instance is running
    if ! incus list "$CONTAINER_NAME" --format csv -c s 2>/dev/null | grep -q RUNNING; then
        echo >&2 "ERROR: ${CONTAINER_NAME} is not running."
        echo >&2 "  Start it: incus start ${CONTAINER_NAME}"
        exit 1
    fi

    # Handle --kill
    if [[ "${1:-}" == "--kill" ]]; then
        incus exec "$CONTAINER_NAME" -- tmux kill-session -t "$SESSION_NAME" 2>/dev/null || true
        echo "Killed session '${SESSION_NAME}'"
        shift
    fi

    # Handle --dry-run
    if [[ "${1:-}" == "--dry-run" ]]; then
        exec incus exec "$CONTAINER_NAME" -- bash -c \
            "cd /root/anklume && python3 scripts/console.py --dry-run"
    fi

    # Check if session already exists inside the container
    if incus exec "$CONTAINER_NAME" -- tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
        echo "Session '${SESSION_NAME}' exists. Attaching..."
    else
        # Create the session (detached) inside the container
        incus exec "$CONTAINER_NAME" -- bash -c \
            "cd /root/anklume && python3 scripts/console.py --no-attach"
    fi

    # Attach the user's terminal to the tmux session inside the container
    exec incus exec "$CONTAINER_NAME" -t -- tmux attach-session -t "$SESSION_NAME"
else
    # ── Running inside the container ─────────────────────
    # Delegate directly to console.py
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    exec python3 "$SCRIPT_DIR/console.py" "$@"
fi
