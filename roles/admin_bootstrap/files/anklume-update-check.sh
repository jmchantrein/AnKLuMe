#!/usr/bin/env bash
# AnKLuMe upgrade notification — runs on login via /etc/profile.d/
# Non-blocking: background git fetch with 5s timeout, exits silently on failure.

# Only check once per day (avoid spamming on every shell open)
STAMP="/tmp/.anklume-update-check-$(date +%Y%m%d)"
[ -f "$STAMP" ] && return 0 2>/dev/null || true

# Must have git and a repo
REPO_DIR="${ANKLUME_DIR:-/root/AnKLuMe}"
[ -d "$REPO_DIR/.git" ] || return 0 2>/dev/null || true
command -v git >/dev/null 2>&1 || return 0 2>/dev/null || true

# Background fetch with timeout (non-blocking)
_anklume_check_update() {
    cd "$REPO_DIR" || return
    # Fetch with 5s timeout — fail silently
    if ! timeout 5 git fetch origin main --quiet 2>/dev/null; then
        return
    fi

    LOCAL=$(git rev-parse HEAD 2>/dev/null)
    REMOTE=$(git rev-parse origin/main 2>/dev/null)

    if [ "$LOCAL" != "$REMOTE" ]; then
        BEHIND=$(git rev-list --count HEAD..origin/main 2>/dev/null || echo "?")
        printf '\033[1;33m'
        echo "╔══════════════════════════════════════════════════╗"
        echo "║  AnKLuMe: $BEHIND commit(s) en retard sur origin/main  "
        echo "║  Exécutez: make upgrade                         ║"
        echo "╚══════════════════════════════════════════════════╝"
        printf '\033[0m'
    fi

    touch "$STAMP"
}

_anklume_check_update
unset -f _anklume_check_update
