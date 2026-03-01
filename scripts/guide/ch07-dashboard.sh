#!/usr/bin/env bash
# Web Dashboard
# Live infrastructure status in your browser.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../guide-lib.sh
source "$SCRIPT_DIR/../guide-lib.sh"

box_header 7 "$GUIDE_TOTAL_CHAPTERS" "Web Dashboard"

# ── Prerequisites ─────────────────────────────────────────────
check_prerequisite "incus"
check_prerequisite "python3"

# ── Explain ───────────────────────────────────────────────────
section_title "How it works"
echo "  The web dashboard shows live infrastructure status in your"
echo "  browser — instances, networks, policies, all auto-refreshing."
echo ""
echo "  Stack:"
echo "    ${ARROW} FastAPI + htmx for reactive updates"
echo "    ${ARROW} Dark theme matching trust-level colors"
echo "    ${ARROW} Auto-refresh every 5 seconds"
echo "    ${ARROW} Reads Incus state + infra.yml in real time"
echo ""
echo "  Launch:"
key_value "anklume dashboard" "http://127.0.0.1:8888"

# ── Demo ──────────────────────────────────────────────────────
section_title "Live demo"
if python3 -c "import fastapi" 2>/dev/null; then
    check_ok "FastAPI available"
    echo ""
    if [[ "$GUIDE_AUTO" == "true" ]]; then
        check_info "Auto-mode: skipping dashboard launch"
    else
        echo "  The dashboard will open in background on port 8888."
        if guide_confirm "Start dashboard now?"; then
            python3 "$GUIDE_PROJECT_DIR/scripts/dashboard.py" --port 8888 &
            _dash_pid=$!
            sleep 1
            check_ok "Dashboard running: http://127.0.0.1:8888"
            check_info "Open this URL in your browser"
            guide_pause
            kill "$_dash_pid" 2>/dev/null || true
            wait "$_dash_pid" 2>/dev/null || true
            check_ok "Dashboard stopped"
        fi
    fi
else
    check_warn "FastAPI not installed"
    check_info "Install: pip install fastapi uvicorn"
fi

# ── Try it ────────────────────────────────────────────────────
section_title "Your turn"
echo "  Start the dashboard and explore:"
echo ""
check_info "anklume dashboard"
echo ""
echo "  The dashboard shows:"
echo "    ${ARROW} Instance cards with status and trust-level colors"
echo "    ${ARROW} Network bridges and their subnets"
echo "    ${ARROW} Network policies with source/destination"

# ── Recap ─────────────────────────────────────────────────────
chapter_recap "The dashboard gives a real-time overview"
next_chapter
