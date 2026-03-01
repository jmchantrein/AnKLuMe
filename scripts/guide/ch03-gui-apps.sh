#!/usr/bin/env bash
# GUI App Forwarding
# Forward graphical applications from containers to your host display.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../guide-lib.sh
source "$SCRIPT_DIR/../guide-lib.sh"

box_header 3 "$GUIDE_TOTAL_CHAPTERS" "GUI App Forwarding"

# ── Prerequisites ─────────────────────────────────────────────
check_prerequisite "incus"
check_incus_socket
check_deployed_domains

if [[ -z "${WAYLAND_DISPLAY:-}" ]]; then
    skip_chapter "No Wayland session detected (WAYLAND_DISPLAY not set)"
    exit 0
fi

# ── Explain ───────────────────────────────────────────────────
section_title "How it works"
echo "  anklume can forward GUI apps from containers to your host"
echo "  display — like QubesOS, but using native Wayland."
echo ""
echo "  The mechanism:"
echo "    ${ARROW} Host Wayland socket is shared read-only"
echo "    ${ARROW} Apps render in their own window on the host"
echo "    ${ARROW} Each window gets a colored border (trust level)"
echo "    ${ARROW} No X11 needed — pure Wayland forwarding"

# ── Demo ──────────────────────────────────────────────────────
section_title "Live demo"
echo "  Check which instances have GUI-forwarding profiles:"
echo ""
run_demo "incus list --all-projects --format compact -c nsPt"
echo ""
echo "  To launch a GUI app from a container, use:"
echo ""
check_info "scripts/domain-exec.sh <instance> --gui -- xterm"
check_info "scripts/domain-exec.sh <instance> --gui -- firefox"
echo ""
if [[ "$GUIDE_AUTO" == "true" ]]; then
    check_info "Auto-mode: skipping interactive GUI demo"
else
    echo "  (GUI apps require a running Wayland compositor on the host)"
fi

# ── Try it ────────────────────────────────────────────────────
section_title "Your turn"
echo "  Try launching a GUI app from one of your containers:"
echo ""
check_info "scripts/domain-exec.sh <instance> --gui -- xterm"
echo ""
echo "  The app should appear on your host desktop, with a colored"
echo "  border matching the domain's trust level."

# ── Recap ─────────────────────────────────────────────────────
chapter_recap "GUI apps display as if they were local"
next_chapter
