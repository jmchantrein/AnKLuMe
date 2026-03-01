#!/usr/bin/env bash
# Clipboard Transfer
# Copy and paste between host and containers.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../guide-lib.sh
source "$SCRIPT_DIR/../guide-lib.sh"

box_header 4 "$GUIDE_TOTAL_CHAPTERS" "Clipboard Transfer"

# ── Prerequisites ─────────────────────────────────────────────
check_prerequisite "incus"
check_incus_socket
check_deployed_domains

# ── Explain ───────────────────────────────────────────────────
section_title "How it works"
echo "  Unlike QubesOS where clipboard is shared automatically,"
echo "  anklume transfers clipboard explicitly — no silent leaks."
echo ""
echo "  The clipboard flow:"
echo "    ${ARROW} Copy text on host (Ctrl+C)"
echo "    ${ARROW} Push to container: clipboard.sh copy-to <instance>"
echo "    ${ARROW} Pull from container: clipboard.sh copy-from <instance>"
echo "    ${ARROW} Each transfer is logged and auditable"

# ── Demo ──────────────────────────────────────────────────────
section_title "Live demo"
if [[ -f "$GUIDE_PROJECT_DIR/scripts/clipboard.sh" ]]; then
    check_info "Clipboard script available at scripts/clipboard.sh"
    echo ""
    run_demo "head -5 $GUIDE_PROJECT_DIR/scripts/clipboard.sh"
else
    check_warn "clipboard.sh not yet implemented"
    check_info "This feature is planned for a future release."
fi

# ── Try it ────────────────────────────────────────────────────
section_title "Your turn"
echo "  Transfer clipboard between host and a container:"
echo ""
check_info "scripts/clipboard.sh copy-to <instance>"
check_info "scripts/clipboard.sh copy-from <instance>"
echo ""
echo "  The clipboard is never shared automatically — you control"
echo "  every transfer explicitly."

# ── Recap ─────────────────────────────────────────────────────
chapter_recap "Clipboard is transferable between domains"
next_chapter
