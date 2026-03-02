#!/usr/bin/env bash
# doctor-network.sh — Network health checks for anklume doctor
#
# Sourced by doctor.sh. Requires: setup_repair_container, host_cmd,
# result_ok, result_warn, result_err, verbose, FIX (from parent).

check_orphan_veths() {
    # Root cause: when Incus restarts a container, the old veth pair may
    # remain in the host network namespace with the same MAC as the new
    # pair. The bridge FDB then has two ports with the same MAC; unicast
    # frames go to the stale port, causing ARP (broadcast) to work but
    # ping/DNS (unicast) to fail. This is likely an Incus race condition
    # during container restart — upstream investigation pending.
    setup_repair_container || return 0
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

check_stale_fdb_entries() {
    # Stale FDB entries are the direct cause of unicast failure after
    # container restart. Even after removing the orphan veth, the bridge
    # may still have stale learned MAC entries pointing to non-existent ports.
    setup_repair_container || return 0
    local stale_count=0

    local bridges
    bridges="$(host_cmd ip -br link show type bridge | awk '/^net-/{print $1}')" || return 0

    while IFS= read -r bridge; do
        [[ -z "$bridge" ]] && continue
        local fdb_entries
        fdb_entries="$(host_cmd bridge fdb show br "$bridge" 2>/dev/null)" || continue

        while IFS= read -r entry; do
            if [[ "$entry" =~ dev\ (veth[a-f0-9]+) ]]; then
                local dev="${BASH_REMATCH[1]}"
                if ! host_cmd ip link show "$dev" &>/dev/null; then
                    ((stale_count++)) || true
                    local mac="${entry%% *}"
                    result_warn "Stale FDB entry on $bridge: $mac -> $dev (device gone) — fixable"
                    if $FIX; then
                        if host_cmd bridge fdb del "$mac" dev "$bridge" 2>/dev/null; then
                            verbose "  Deleted FDB entry $mac from $bridge"
                        fi
                    fi
                fi
            fi
        done <<< "$fdb_entries"
    done <<< "$bridges"

    [[ $stale_count -eq 0 ]] && result_ok "No stale FDB entries"
}

check_stale_routes() {
    setup_repair_container || return 0
    local routes stale_count=0
    routes="$(host_cmd ip route)" || return 0

    while IFS= read -r line; do
        if [[ "$line" =~ ^10\.100\..+dev\ veth.+src\ 10\.100 ]]; then
            ((stale_count++)) || true
            result_warn "Stale route: $line — fixable"
            if $FIX; then
                # shellcheck disable=SC2086  # $line must word-split for ip route del
                if host_cmd ip route del $line; then verbose "  Deleted route"; fi
            fi
        fi
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
    setup_repair_container || return 0
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
    setup_repair_container || return 0
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
    setup_repair_container || return 0
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
