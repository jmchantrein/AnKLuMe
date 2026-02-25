#!/usr/bin/env bash
# tmux-domain-switch.sh — Purge clipboard on domain switch (D-055)
#
# Called by tmux after-select-pane hook. Detects when the user switches
# to a pane in a different domain and purges the clipboard to prevent
# cross-domain data leakage.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
STATE_FILE="${HOME}/.anklume/tmux-last-domain"

# Extract domain from pane title: "[domain] machine" -> "domain"
current_title=$(tmux display-message -p '#{pane_title}' 2>/dev/null || true)
current_domain=$(echo "$current_title" | sed -n 's/^\[\([^]]*\)\].*/\1/p')

# No domain detected (maybe not an anklume pane)
[[ -z "$current_domain" ]] && exit 0

# Read previous domain
previous_domain=""
if [[ -f "$STATE_FILE" ]]; then
    previous_domain=$(cat "$STATE_FILE")
fi

# Update state
mkdir -p "$(dirname "$STATE_FILE")"
printf '%s' "$current_domain" > "$STATE_FILE"

# If domain changed, purge clipboard
if [[ -n "$previous_domain" && "$previous_domain" != "$current_domain" ]]; then
    "${SCRIPT_DIR}/clipboard.sh" purge 2>/dev/null || true
fi
