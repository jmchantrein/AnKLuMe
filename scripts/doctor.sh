#!/usr/bin/env bash
# doctor.sh — anklume infrastructure health checker and auto-fixer
#
# Usage:
#   scripts/doctor.sh                    # Diagnose all categories
#   scripts/doctor.sh --fix              # Diagnose and fix fixable issues
#   scripts/doctor.sh --check network    # Network checks only
#   scripts/doctor.sh --verbose          # Detailed output
#
# Categories: network, instances, config, deps, all (default)
# Network checks use a temporary privileged container (auto-created, auto-deleted).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Colors ──────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
RESET='\033[0m'

# ── Counters ────────────────────────────────────────────────
PASS=0; WARN=0; ERR=0

# ── Arguments ───────────────────────────────────────────────
FIX=false
CATEGORY="all"
VERBOSE=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --fix)     FIX=true ;;
        --check)   CATEGORY="$2"; shift ;;
        --verbose) VERBOSE=true ;;
        -h|--help)
            echo "Usage: $0 [--fix] [--check CATEGORY] [--verbose]"
            echo "Categories: network, instances, config, deps, all"
            exit 0 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
    shift
done

# ── Output helpers ──────────────────────────────────────────
result_ok()   { ((PASS++)) || true; printf " %b[✓]%b %s\n" "$GREEN" "$RESET" "$1"; }
result_warn() { ((WARN++)) || true; printf " %b[!]%b %s\n" "$YELLOW" "$RESET" "$1"; }
result_err()  { ((ERR++))  || true; printf " %b[✗]%b %s\n" "$RED" "$RESET" "$1"; }
verbose()     { if $VERBOSE; then printf "     %s\n" "$1"; fi; }

# ── Privileged container management ─────────────────────────
REPAIR_CONTAINER="anklume-doctor-$$"
REPAIR_READY=false

# shellcheck disable=SC2317,SC2329
cleanup() {
    if incus info "$REPAIR_CONTAINER" &>/dev/null; then
        incus delete "$REPAIR_CONTAINER" --force &>/dev/null || true
        verbose "Temporary container $REPAIR_CONTAINER deleted"
    fi
}
trap cleanup EXIT

setup_repair_container() {
    $REPAIR_READY && return 0
    verbose "Creating temporary privileged container..."
    incus launch images:debian/13 "$REPAIR_CONTAINER" --ephemeral \
        -c security.privileged=true -p default --network net-anklume &>/dev/null
    incus config device add "$REPAIR_CONTAINER" hostproc disk \
        source=/proc path=/hostproc &>/dev/null
    local _i
    for _i in $(seq 1 15); do
        incus exec "$REPAIR_CONTAINER" -- true &>/dev/null && break
        sleep 1
    done
    REPAIR_READY=true
    verbose "Temporary container ready"
}

host_cmd() {
    incus exec "$REPAIR_CONTAINER" -- \
        nsenter --net=/hostproc/1/ns/net --mount=/hostproc/1/ns/mnt -- "$@" 2>/dev/null
}

# ── Source check modules ────────────────────────────────────
# shellcheck source=doctor-network.sh
source "$SCRIPT_DIR/doctor-network.sh"
# shellcheck source=doctor-checks.sh
source "$SCRIPT_DIR/doctor-checks.sh"

# ── Category runners ────────────────────────────────────────

run_network_checks() {
    printf "\n%bNetwork%b\n" "$BOLD" "$RESET"
    check_orphan_veths
    check_stale_fdb_entries
    check_stale_routes
    check_nat_rules
    check_dns_dhcp_chains
    check_bridge_health
}

run_instance_checks() {
    printf "\n%bInstances%b\n" "$BOLD" "$RESET"
    check_incus_running
    check_anklume_running
    check_container_connectivity
}

run_config_checks() {
    printf "\n%bConfiguration%b\n" "$BOLD" "$RESET"
    check_ip_drift
}

run_deps_checks() {
    printf "\n%bDependencies%b\n" "$BOLD" "$RESET"
    check_container_deps
}

# ── Main ────────────────────────────────────────────────────

printf "%banklume Doctor%b — checking infrastructure health...\n" "$BOLD" "$RESET"
if $FIX; then printf "(auto-fix mode enabled)\n"; fi

case "$CATEGORY" in
    all)
        run_instance_checks
        run_network_checks
        run_config_checks
        run_deps_checks
        ;;
    network)   run_network_checks ;;
    instances) run_instance_checks ;;
    config)    run_config_checks ;;
    deps)      run_deps_checks ;;
    *) echo "Unknown category: $CATEGORY"; exit 1 ;;
esac

# ── Summary ─────────────────────────────────────────────────
printf "\n%bSummary:%b " "$BOLD" "$RESET"
printf "%b%s passed%b, " "$GREEN" "$PASS" "$RESET"
printf "%b%s warnings%b, " "$YELLOW" "$WARN" "$RESET"
printf "%b%s errors%b\n" "$RED" "$ERR" "$RESET"

if [[ $WARN -gt 0 ]] && ! $FIX; then
    printf "Run %bmake doctor FIX=1%b to auto-fix warnings.\n" "$BOLD" "$RESET"
fi

exit $(( ERR > 0 ? 1 : 0 ))
