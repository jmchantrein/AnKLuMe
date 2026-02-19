#!/usr/bin/env bash
# incus-guard.sh — Consolidated Incus network safety guard
#
# Prevents Incus bridges from breaking host network connectivity
# when bridge subnets conflict with the host's real network.
#
# Subcommands:
#   start       Safe Incus startup with bridge watcher (replaces safe-incus-start.sh)
#   post-start  Systemd ExecStartPost hook (replaces incus-network-guard.sh)
#   install     Install as systemd drop-in (replaces install-incus-guard.sh)
#
# Usage:
#   scripts/incus-guard.sh start
#   scripts/incus-guard.sh post-start
#   scripts/incus-guard.sh install
set -euo pipefail

LOGFILE="/var/log/incus-network-guard.log"
GUARD_STATE="/run/incus-guard-host-dev"
GUARD_SCRIPT_INSTALL="/opt/anklume/incus-guard.sh"
DROPIN_DIR="/etc/systemd/system/incus.service.d"
DROPIN_FILE="$DROPIN_DIR/network-guard.conf"

# ── Shared helpers ────────────────────────────────────────

log() { echo "$(date -Iseconds) $*" | tee -a "$LOGFILE" 2>/dev/null || echo "$*"; }

detect_host_network() {
    # Detect host default route, interface, subnet prefix, and gateway
    local default_route
    default_route=$(ip route show default 2>/dev/null | head -1)

    if [[ -n "$default_route" ]]; then
        DEFAULT_DEV=$(echo "$default_route" | awk '{print $5}')
        DEFAULT_GW=$(echo "$default_route" | awk '{print $3}')
        echo "$DEFAULT_DEV" > "$GUARD_STATE" 2>/dev/null || true
    elif [[ -f "$GUARD_STATE" ]]; then
        DEFAULT_DEV=$(cat "$GUARD_STATE")
        DEFAULT_GW=""
    else
        return 1
    fi

    HOST_PREFIX=$(ip -4 addr show "$DEFAULT_DEV" 2>/dev/null \
        | grep -oP 'inet \K[0-9]+\.[0-9]+\.[0-9]+' | head -1)
    [[ -n "$HOST_PREFIX" ]] || return 1
    return 0
}

delete_conflicting_bridges() {
    # Delete bridges at kernel level whose subnet conflicts with host
    local conflicts=0
    local iface bridge_prefix
    for iface in $(ip -o link show type bridge 2>/dev/null \
            | grep -oP '\d+: \K[a-z0-9][a-z0-9-]+' || true); do
        [[ "$iface" == "$DEFAULT_DEV" ]] && continue
        bridge_prefix=$(ip -4 addr show "$iface" 2>/dev/null \
            | grep -oP 'inet \K[0-9]+\.[0-9]+\.[0-9]+' || true)
        if [[ "$bridge_prefix" == "$HOST_PREFIX" ]]; then
            log "CONFLICT: Bridge $iface uses ${bridge_prefix}.x — same as host. Removing."
            ip link set "$iface" down 2>/dev/null || true
            ip link delete "$iface" 2>/dev/null || true
            conflicts=$((conflicts + 1))
        fi
    done
    echo "$conflicts"
}

clean_incus_database() {
    # Remove conflicting networks from Incus database
    local net net_addr
    for net in $(incus network list --format csv 2>/dev/null \
            | cut -d, -f1 || true); do
        net_addr=$(incus network get "$net" ipv4.address 2>/dev/null || true)
        if [[ "$net_addr" == "${HOST_PREFIX}."* ]]; then
            log "Cleaning Incus DB: deleting network $net ($net_addr)"
            incus network delete "$net" 2>/dev/null || true
        fi
    done
}

restore_default_route() {
    # Restore default route if it was lost
    if [[ -n "${DEFAULT_GW:-}" ]]; then
        if ! ip route show default 2>/dev/null | grep -q "$DEFAULT_GW"; then
            log "WARNING: Default route lost. Restoring via $DEFAULT_GW dev $DEFAULT_DEV"
            ip route add default via "$DEFAULT_GW" dev "$DEFAULT_DEV" 2>/dev/null || true
        fi
    fi
}

# ── Subcommand: start ─────────────────────────────────────

cmd_start() {
    # Safe Incus startup with kernel-level bridge watcher
    if ! detect_host_network; then
        echo "ERROR: No default route found. Network may already be broken."
        exit 1
    fi

    echo "Host network: ${HOST_PREFIX}.0/24 via $DEFAULT_GW dev $DEFAULT_DEV"

    # Check if Incus is already running
    local do_start=true
    if systemctl is-active --quiet incus 2>/dev/null; then
        echo "Incus is already running."
        do_start=false
    fi

    # Start kernel-level bridge watcher (deletes conflicting bridges every 100ms)
    local watcher_running=true
    (
        while $watcher_running 2>/dev/null; do
            for iface in $(ip -o link show 2>/dev/null \
                    | grep -oP '\d+: \Knet-[a-z0-9-]+' || true); do
                bridge_ip=$(ip -4 addr show "$iface" 2>/dev/null \
                    | grep -oP 'inet \K[0-9]+\.[0-9]+\.[0-9]+' || true)
                if [[ -n "$bridge_ip" && "$bridge_ip" == "$HOST_PREFIX" ]]; then
                    ip link set "$iface" down 2>/dev/null || true
                    ip link delete "$iface" 2>/dev/null || true
                    echo "WATCHER: Deleted conflicting bridge $iface ($bridge_ip.x)"
                fi
            done
            sleep 0.1
        done
    ) &
    local watcher_pid=$!
    trap 'kill '"$watcher_pid"' 2>/dev/null; wait '"$watcher_pid"' 2>/dev/null || true' EXIT

    # Start Incus
    if [[ "$do_start" == "true" ]]; then
        echo "Starting Incus..."
        systemctl start incus.socket
        systemctl start incus
        echo "Incus started. Waiting for initialization..."
        sleep 2
    fi

    # Clean conflicting networks from Incus database
    echo "Cleaning conflicting bridges from Incus database..."
    clean_incus_database

    # Stop watcher
    kill "$watcher_pid" 2>/dev/null || true
    trap - EXIT

    # Verify/restore default route
    restore_default_route

    # Final verification
    if ping -c1 -W2 "$DEFAULT_GW" &>/dev/null; then
        echo "OK: Network connectivity verified (gateway $DEFAULT_GW reachable)."
    else
        echo "ERROR: Gateway $DEFAULT_GW unreachable. Network may be broken."
        echo "Try: sudo ip route add default via $DEFAULT_GW dev $DEFAULT_DEV"
        exit 1
    fi

    echo "Incus started safely."
}

# ── Subcommand: post-start ────────────────────────────────

cmd_post_start() {
    # Systemd ExecStartPost hook — runs after every Incus startup
    if ! detect_host_network; then
        log "ERROR: Cannot determine host network. No default route and no saved state."
        exit 0  # Don't block Incus startup
    fi

    log "Host network: ${HOST_PREFIX}.0/24 on $DEFAULT_DEV (gw: ${DEFAULT_GW:-unknown})"

    # Delete conflicting bridges at kernel level
    local conflicts
    conflicts=$(delete_conflicting_bridges)

    # Also clean Incus database if conflicts found
    if [[ "$conflicts" -gt 0 ]]; then
        sleep 1  # Give Incus a moment
        clean_incus_database
    fi

    # Restore default route if lost
    restore_default_route

    if [[ "$conflicts" -eq 0 ]]; then
        log "OK: No conflicting bridges found."
    else
        log "OK: Removed $conflicts conflicting bridge(s). Network restored."
    fi
}

# ── Subcommand: install ───────────────────────────────────

cmd_install() {
    # Install as systemd drop-in for incus.service
    echo "Installing Incus network guard..."

    # Copy guard script to a stable location
    install -Dm755 "${BASH_SOURCE[0]}" "$GUARD_SCRIPT_INSTALL"

    # Create systemd drop-in
    mkdir -p "$DROPIN_DIR"
    cat > "$DROPIN_FILE" << EOF
[Service]
ExecStartPost=$GUARD_SCRIPT_INSTALL post-start
EOF

    # Reload systemd
    systemctl daemon-reload

    echo "Installed:"
    echo "  Guard script: $GUARD_SCRIPT_INSTALL"
    echo "  Systemd drop-in: $DROPIN_FILE"
    echo ""
    echo "The guard will run automatically after every Incus startup."
    echo "It removes any Incus bridge that conflicts with the host network."
}

# ── Main dispatch ─────────────────────────────────────────

case "${1:-}" in
    start)
        cmd_start
        ;;
    post-start)
        cmd_post_start
        ;;
    install)
        cmd_install
        ;;
    --help|-h|"")
        echo "Usage: $(basename "$0") <start|post-start|install>"
        echo ""
        echo "Subcommands:"
        echo "  start       Safe Incus startup with bridge conflict prevention"
        echo "  post-start  Systemd ExecStartPost hook (run after Incus starts)"
        echo "  install     Install as systemd drop-in for automatic protection"
        [[ -z "${1:-}" ]] && exit 1
        ;;
    *)
        echo "ERROR: Unknown subcommand: $1" >&2
        echo "Usage: $(basename "$0") <start|post-start|install>" >&2
        exit 1
        ;;
esac
