#!/usr/bin/env bash
# Domain Isolation
# Discover how anklume isolates domains in separate networks.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../guide-lib.sh
source "$SCRIPT_DIR/../guide-lib.sh"

box_header 1 "$GUIDE_TOTAL_CHAPTERS" "Domain Isolation"

# ── Prerequisites ─────────────────────────────────────────────
check_prerequisite "incus"
check_incus_socket
check_deployed_domains

# ── Explain ───────────────────────────────────────────────────
section_title "How it works"
echo "  anklume creates isolated domains, each with its own network"
echo "  and Incus project. Machines in one domain cannot reach"
echo "  machines in another by default."
echo ""
echo "  Each domain gets:"
echo "    ${ARROW} A dedicated bridge (net-<domain>)"
echo "    ${ARROW} A separate IP subnet (10.<zone>.<seq>.0/24)"
echo "    ${ARROW} An Incus project for namespace isolation"
echo "    ${ARROW} nftables rules blocking cross-domain traffic"

# ── Demo ──────────────────────────────────────────────────────
section_title "Live demo"
echo "  All instances across all projects:"
echo ""
run_demo "incus list --all-projects --format compact"

echo ""
echo "  Domain networks:"
echo ""
run_demo "incus network list --format compact 2>/dev/null | head -20"

echo ""
echo "  Notice each domain has its own subnet (different second/third octets)."

# ── Try it ────────────────────────────────────────────────────
section_title "Your turn"
echo "  Try these commands:"
echo ""
check_info "incus list --all-projects --format compact"
check_info "incus project list --format compact"
check_info "incus network list --format compact"
echo ""
echo "  Check IPs — each domain uses a different subnet to encode"
echo "  its trust level directly in the IP address."

# ── Recap ─────────────────────────────────────────────────────
chapter_recap "Each domain is isolated in its own network"
next_chapter
