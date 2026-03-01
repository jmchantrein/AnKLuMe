#!/usr/bin/env bash
# Tmux Console
# Color-coded tmux console with domain windows.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../guide-lib.sh
source "$SCRIPT_DIR/../guide-lib.sh"

box_header 2 "$GUIDE_TOTAL_CHAPTERS" "Tmux Console"

# ── Prerequisites ─────────────────────────────────────────────
check_prerequisite "incus"
check_incus_socket
check_deployed_domains

if ! command -v tmux &>/dev/null; then
    skip_chapter "tmux not installed — $(install_hint tmux)"
    exit 0
fi

# ── Explain ───────────────────────────────────────────────────
section_title "How it works"
echo "  The tmux console opens one window per domain, each colored"
echo "  by trust level — just like QubesOS window borders."
echo ""
echo "  Trust level colors:"
key_value "admin" "blue"
key_value "trusted" "green"
key_value "semi-trusted" "yellow"
key_value "untrusted" "red"
key_value "disposable" "magenta"

# ── Demo ──────────────────────────────────────────────────────
section_title "Live demo"
echo "  Preview what the console would create (dry-run):"
echo ""
if [[ -f "$GUIDE_PROJECT_DIR/scripts/console.py" ]]; then
    run_demo "python3 $GUIDE_PROJECT_DIR/scripts/console.py --dry-run"
else
    check_warn "console.py not found"
fi

# ── Try it ────────────────────────────────────────────────────
section_title "Your turn"
echo "  Launch the console:"
echo ""
check_info "anklume console"
echo ""
echo "  Inside tmux:"
check_info "Ctrl+b, n — next window (next domain)"
check_info "Ctrl+b, p — previous window"
check_info "Ctrl+b, d — detach (leave console running)"

# ── Recap ─────────────────────────────────────────────────────
chapter_recap "The tmux console organizes your domains visually"
next_chapter
