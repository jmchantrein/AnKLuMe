#!/usr/bin/env bash
# update-check.sh — Check for AnKLuMe updates (called at login)
#
# Usage: scripts/update-check.sh
#
# Compares local HEAD with origin/main (or current branch).
# Prints a one-liner if updates are available.
# Designed to be sourced from .bashrc or .profile with minimal latency.
#
# Caches the result for 1 hour to avoid repeated git fetch on every shell.

set -euo pipefail

CACHE_DIR="${HOME}/.anklume"
CACHE_FILE="${CACHE_DIR}/update-check-cache"
CACHE_TTL=3600  # 1 hour in seconds
REPO_DIR="${1:-/root/AnKLuMe}"

# Skip if not a git repo
if [ ! -d "${REPO_DIR}/.git" ]; then
    exit 0
fi

# Skip if cache is fresh
if [ -f "$CACHE_FILE" ]; then
    cache_age=$(( $(date +%s) - $(stat -c %Y "$CACHE_FILE" 2>/dev/null || echo 0) ))
    if [ "$cache_age" -lt "$CACHE_TTL" ]; then
        # Show cached message if any
        cached_msg=$(cat "$CACHE_FILE")
        if [ -n "$cached_msg" ]; then
            echo "$cached_msg"
        fi
        exit 0
    fi
fi

mkdir -p "$CACHE_DIR"

# Fetch silently in background (timeout 5s to not block login)
if ! timeout 5 git -C "$REPO_DIR" fetch origin --quiet 2>/dev/null; then
    # Network unavailable — clear cache and exit silently
    echo -n "" > "$CACHE_FILE"
    exit 0
fi

BRANCH=$(git -C "$REPO_DIR" branch --show-current 2>/dev/null || echo "main")
LOCAL=$(git -C "$REPO_DIR" rev-parse HEAD 2>/dev/null)
REMOTE=$(git -C "$REPO_DIR" rev-parse "origin/${BRANCH}" 2>/dev/null || true)

if [ -z "$REMOTE" ] || [ "$LOCAL" = "$REMOTE" ]; then
    # Up to date
    echo -n "" > "$CACHE_FILE"
    exit 0
fi

# Count commits behind
BEHIND=$(git -C "$REPO_DIR" rev-list --count "HEAD..origin/${BRANCH}" 2>/dev/null || echo "?")

MSG=$'\033[33m'"AnKLuMe: ${BEHIND} update(s) available. Run 'make upgrade' to update."$'\033[0m'
echo "$MSG" > "$CACHE_FILE"
echo "$MSG"
