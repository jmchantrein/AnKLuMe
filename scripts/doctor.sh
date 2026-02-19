#!/usr/bin/env bash
# doctor.sh — AnKLuMe infrastructure health checker and auto-fixer
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

# shellcheck disable=SC2317  # cleanup is called via trap
cleanup() {
    if incus info "$REPAIR_CONTAINER" &>/dev/null; then
        incus delete "$REPAIR_CONTAINER" --force &>/dev/null || true
        verbose "Temporary container $REPAIR_CONTAINER deleted"
    fi
}
trap cleanup EXIT

setup_repair_container() {
    $REPAIR_READY && return 0
    # NOTE: This creates a privileged container for nsenter access to the host
    # network namespace. This is a documented exception to ADR-020 (like
    # incus-guard.sh is to ADR-004): ephemeral diagnostic container that
    # exists only for the duration of the check, auto-deleted on exit.
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

# ── Network checks (need privileged container) ──────────────

check_orphan_veths() {
    setup_repair_container
    local veth_list orphan_count=0
    veth_list="$(host_cmd ip -br link show type veth)" || return 0

    # Collect container veths (@ifNN) and their MACs
    declare -A container_macs
    while IFS= read -r line; do
        local iface="${line%% *}"
        if [[ "$iface" == *"@if"* ]]; then
            local bare="${iface%%@*}"
            local mac
            mac="$(host_cmd ip link show "$bare" 2>/dev/null | grep 'link/ether' | awk '{print $2}')" || continue
            container_macs["$mac"]+="$bare "
        fi
    done <<< "$veth_list"

    # Find orphan veths (@vethXXX) with matching MACs
    while IFS= read -r line; do
        local iface="${line%% *}"
        if [[ "$iface" == *"@veth"* ]]; then
            local bare="${iface%%@*}"
            local mac
            mac="$(host_cmd ip link show "$bare" 2>/dev/null | grep 'link/ether' | awk '{print $2}')" || continue
            if [[ -n "${container_macs[$mac]:-}" ]]; then
                ((orphan_count++)) || true
                result_warn "Orphan veth $bare (MAC $mac collides with ${container_macs[$mac]}) — fixable"
                if $FIX; then
                    if host_cmd ip link del "$bare"; then verbose "  Deleted $bare"; fi
                fi
            fi
        fi
    done <<< "$veth_list"

    [[ $orphan_count -eq 0 ]] && result_ok "No orphan veth pairs"
}

check_stale_routes() {
    setup_repair_container
    local routes stale_count=0
    routes="$(host_cmd ip route)" || return 0

    while IFS= read -r line; do
        # Stale route: 10.100.x.x/24 dev vethXXX with src 10.100.x.x
        if [[ "$line" =~ ^10\.100\..+dev\ veth.+src\ 10\.100 ]]; then
            ((stale_count++)) || true
            result_warn "Stale route: $line — fixable"
            if $FIX; then
                # shellcheck disable=SC2086  # $line must word-split for ip route del
                if host_cmd ip route del $line; then verbose "  Deleted route"; fi
            fi
        fi
        # Stale default route via veth
        if [[ "$line" =~ ^default.*dev\ veth ]]; then
            ((stale_count++)) || true
            result_warn "Stale default route via veth: $line — fixable"
            if $FIX; then
                # shellcheck disable=SC2086  # $line must word-split for ip route del
                if host_cmd ip route del $line; then verbose "  Deleted route"; fi
            fi
        fi
    done <<< "$routes"

    [[ $stale_count -eq 0 ]] && result_ok "No stale routes"
}

check_nat_rules() {
    setup_repair_container
    local bridges nft_rules missing=0
    bridges="$(host_cmd ip -br link show type bridge | awk '/^net-/{print $1}')" || return 0
    nft_rules="$(host_cmd nft list table inet incus 2>/dev/null)" || {
        result_err "Cannot read nftables table inet incus"
        return 0
    }

    while IFS= read -r bridge; do
        [[ -z "$bridge" ]] && continue
        if ! echo "$nft_rules" | grep -q "chain pstrt\.$bridge"; then
            ((missing++)) || true
            result_err "Missing NAT chain for $bridge — try restarting Incus"
        else
            verbose "NAT chain present for $bridge"
        fi
    done <<< "$bridges"

    [[ $missing -eq 0 ]] && result_ok "NAT rules present for all bridges"
}

check_dns_dhcp_chains() {
    setup_repair_container
    local bridges nft_rules missing=0
    bridges="$(host_cmd ip -br link show type bridge | awk '/^net-/{print $1}')" || return 0
    nft_rules="$(host_cmd nft list table inet incus 2>/dev/null)" || return 0

    while IFS= read -r bridge; do
        [[ -z "$bridge" ]] && continue
        if ! echo "$nft_rules" | grep -q "chain in\.$bridge"; then
            ((missing++)) || true
            result_err "Missing DNS/DHCP input chain for $bridge"
        fi
    done <<< "$bridges"

    [[ $missing -eq 0 ]] && result_ok "DNS/DHCP chains present for all bridges"
}

check_bridge_health() {
    setup_repair_container
    local bridges unhealthy=0
    bridges="$(host_cmd ip -br link show type bridge | awk '/^net-/{print $1, $2}')" || return 0

    while read -r bridge state; do
        [[ -z "$bridge" ]] && continue
        if [[ "$state" != "UP" ]]; then
            ((unhealthy++)) || true
            result_err "Bridge $bridge is $state (expected UP)"
            continue
        fi
        local ip
        ip="$(host_cmd ip -4 addr show "$bridge" | grep -oP 'inet \K[0-9.]+')" || ip=""
        if [[ -z "$ip" || ! "$ip" =~ \.254$ ]]; then
            ((unhealthy++)) || true
            result_err "Bridge $bridge missing .254 gateway IP (has: ${ip:-none})"
        else
            verbose "Bridge $bridge UP with IP $ip"
        fi
    done <<< "$bridges"

    [[ $unhealthy -eq 0 ]] && result_ok "All bridges healthy (UP with .254 gateway)"
}

# ── Instance checks (no privilege needed) ───────────────────

check_incus_running() {
    if incus list --format csv -c n &>/dev/null; then
        result_ok "Incus daemon reachable"
    else
        result_err "Incus daemon not reachable"
    fi
}

check_anklume_running() {
    local status
    status="$(incus list anklume-instance --project anklume --format csv -c s 2>/dev/null)" || status=""
    if [[ "$status" == *"RUNNING"* ]]; then
        result_ok "anklume-instance is running"
    else
        result_err "anklume-instance not running (status: ${status:-unknown})"
    fi
}

check_container_connectivity() {
    local fail_count=0 total=0 skip_count=0
    # Use JSON for reliable project extraction
    local json
    json="$(incus list --all-projects --format json 2>/dev/null)" || return 0

    while IFS=$'\t' read -r name project status; do
        [[ -z "$name" || "$name" == "anklume-doctor"* ]] && continue
        [[ "$status" != "Running" ]] && continue
        ((total++)) || true
        local gw
        gw="$(incus exec "$name" --project "$project" -- \
            ip route 2>/dev/null | awk '/^default/{print $3}' | head -1)" || gw=""
        if [[ -z "$gw" ]]; then
            ((skip_count++)) || true
            verbose "$name ($project): no default route, skipped"
            continue
        fi
        if ! incus exec "$name" --project "$project" -- \
            ping -c1 -W2 "$gw" &>/dev/null; then
            ((fail_count++)) || true
            result_warn "$name ($project): cannot reach gateway $gw"
        else
            verbose "$name ($project): gateway $gw reachable"
        fi
    done < <(echo "$json" | python3 -c "
import json, sys
for i in json.loads(sys.stdin.read()):
    print(f\"{i['name']}\t{i.get('project','default')}\t{i['status']}\")
" 2>/dev/null)

    if [[ $fail_count -eq 0 ]]; then
        local tested=$((total - skip_count))
        result_ok "All $tested/$total running containers can reach their gateway"
    fi
}

# ── Config checks ───────────────────────────────────────────

check_ip_drift() {
    [[ ! -f infra.yml ]] && { verbose "No infra.yml found, skipping IP drift check"; return 0; }
    local drift=0 data
    data="$(incus list --all-projects --format csv -c ns4p 2>/dev/null)" || return 0

    while IFS=, read -r name status ipv4 project; do
        [[ "$status" != "RUNNING" || -z "$ipv4" ]] && continue
        local actual_ip="${ipv4%% *}"
        actual_ip="${actual_ip%%/*}"
        [[ -z "$actual_ip" ]] && continue
        # Check if this IP matches infra.yml (fixed-string match to avoid regex injection)
        local expected
        expected="$(grep -F -A5 "${name}:" infra.yml 2>/dev/null | grep 'ip:' | head -1 | grep -oP '"\K[^"]+' || true)"
        if [[ -n "$expected" && "$actual_ip" != "$expected" ]]; then
            ((drift++)) || true
            result_warn "$name: IP $actual_ip (expected $expected from infra.yml)"
        fi
    done <<< "$data"

    [[ $drift -eq 0 ]] && result_ok "No IP drift detected"
}

# ── Dependency checks ───────────────────────────────────────

check_container_deps() {
    local missing=()
    for dep in tmux python3 make; do
        if ! incus exec anklume-instance --project anklume -- \
            which "$dep" &>/dev/null; then
            missing+=("$dep")
        fi
    done

    if [[ ${#missing[@]} -gt 0 ]]; then
        result_warn "Missing in anklume-instance: ${missing[*]} — fixable"
        if $FIX; then
            incus exec anklume-instance --project anklume -- \
                apt-get update -qq &>/dev/null
            if incus exec anklume-instance --project anklume -- \
                apt-get install -y -qq "${missing[@]}" &>/dev/null; then
                result_ok "Installed ${missing[*]}"
            else
                result_err "Failed to install ${missing[*]}"
            fi
        fi
    else
        result_ok "Dependencies present in anklume-instance (tmux, python3, make)"
    fi
}

# ── Category runners ────────────────────────────────────────

run_network_checks() {
    printf "\n%bNetwork%b\n" "$BOLD" "$RESET"
    check_orphan_veths
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

printf "%bAnKLuMe Doctor%b — checking infrastructure health...\n" "$BOLD" "$RESET"
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
