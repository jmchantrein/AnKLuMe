#!/usr/bin/env bash
# Network Isolation
# Inter-domain traffic is blocked by nftables.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../guide-lib.sh
source "$SCRIPT_DIR/../guide-lib.sh"

box_header 5 "$GUIDE_TOTAL_CHAPTERS" "Network Isolation"

# ── Prerequisites ─────────────────────────────────────────────
check_prerequisite "incus"
check_incus_socket
check_deployed_domains

# ── Explain ───────────────────────────────────────────────────
section_title "How it works"
echo "  By default, ALL inter-domain traffic is dropped by nftables."
echo "  Each domain bridge is isolated — no forwarding between them."
echo ""
echo "  The isolation stack:"
echo "    ${ARROW} Incus creates one bridge per domain (net-<domain>)"
echo "    ${ARROW} nftables 'inet anklume' table at priority -1"
echo "    ${ARROW} Default: DROP all forwarding between bridges"
echo "    ${ARROW} network_policies in infra.yml add ACCEPT exceptions"
echo ""
echo "  Defense in depth: even with a firewall VM (Phase 11),"
echo "  host-level nftables still block direct bridge-to-bridge traffic."

# ── Demo ──────────────────────────────────────────────────────
section_title "Live demo"
echo "  Current nftables rules for anklume:"
echo ""
if nft list table inet anklume 2>/dev/null | head -30 | sed 's/^/    /'; then
    check_ok "anklume nftables table found"
else
    check_warn "No anklume nftables table (deploy with: anklume network deploy)"
fi

echo ""
echo "  Network bridges:"
echo ""
run_demo "incus network list --format compact 2>/dev/null | head -15"

# ── Try it ────────────────────────────────────────────────────
section_title "Your turn"
echo "  Test isolation — ping between domains should FAIL:"
echo ""
check_info "incus exec <src-instance> --project <domain> -- ping -c1 <dst-ip>"
echo ""
echo "  Generate and deploy nftables rules:"
echo ""
check_info "anklume network rules     # Generate rules"
check_info "anklume network deploy    # Apply on host"

# ── Recap ─────────────────────────────────────────────────────
chapter_recap "Network isolation is active by default between domains"
next_chapter
