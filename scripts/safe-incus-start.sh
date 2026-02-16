#!/usr/bin/env bash
# safe-incus-start.sh — Start Incus without breaking host network
#
# Problem: Incus recreates bridges from its database on startup.
# If those bridges use subnets that conflict with the host network
# (e.g., net-anklume on 10.100.0.x when host is on 10.100.0.0/24),
# the host loses connectivity.
#
# Solution: Run a kernel-level bridge watcher that deletes conflicting
# bridges as fast as they appear, then clean the Incus database.
set -euo pipefail

# ── Detect host network ────────────────────────────────────────
DEFAULT_ROUTE=$(ip route show default 2>/dev/null | head -1)
if [[ -z "$DEFAULT_ROUTE" ]]; then
    echo "ERROR: No default route found. Network may already be broken."
    exit 1
fi

DEFAULT_GW=$(echo "$DEFAULT_ROUTE" | awk '{print $3}')
DEFAULT_DEV=$(echo "$DEFAULT_ROUTE" | awk '{print $5}')
HOST_SUBNET=$(ip -4 addr show "$DEFAULT_DEV" 2>/dev/null \
    | grep -oP 'inet \K[0-9]+\.[0-9]+\.[0-9]+' | head -1)

echo "Host network: ${HOST_SUBNET}.0/24 via $DEFAULT_GW dev $DEFAULT_DEV"

# ── Check if Incus is already running ──────────────────────────
if systemctl is-active --quiet incus 2>/dev/null; then
    echo "Incus is already running."
    # Still clean conflicting bridges
    _do_cleanup_only=true
else
    _do_cleanup_only=false
fi

# ── Start kernel-level bridge watcher ──────────────────────────
# Deletes net-* interfaces at the kernel level (ip link) before
# they can inject conflicting routes. Runs every 100ms.
_watcher_running=true
(
    while $_watcher_running 2>/dev/null; do
        for iface in $(ip -o link show 2>/dev/null \
                | grep -oP '\d+: \Knet-[a-z0-9-]+' || true); do
            # Check if this bridge uses a conflicting subnet
            bridge_ip=$(ip -4 addr show "$iface" 2>/dev/null \
                | grep -oP 'inet \K[0-9]+\.[0-9]+\.[0-9]+' || true)
            if [[ -n "$bridge_ip" && "$bridge_ip" == "$HOST_SUBNET" ]]; then
                ip link set "$iface" down 2>/dev/null || true
                ip link delete "$iface" 2>/dev/null || true
                echo "WATCHER: Deleted conflicting bridge $iface ($bridge_ip.x)"
            fi
        done
        sleep 0.1
    done
) &
WATCHER_PID=$!

cleanup() {
    kill "$WATCHER_PID" 2>/dev/null || true
    wait "$WATCHER_PID" 2>/dev/null || true
}
trap cleanup EXIT

# ── Start Incus ────────────────────────────────────────────────
if [[ "$_do_cleanup_only" == "false" ]]; then
    echo "Starting Incus..."
    systemctl start incus.socket
    systemctl start incus
    echo "Incus started. Waiting for initialization..."
    sleep 2
fi

# ── Delete conflicting networks from Incus database ────────────
echo "Cleaning conflicting bridges from Incus database..."
for net in $(incus network list --format csv 2>/dev/null \
        | cut -d, -f1 | grep "^net-" || true); do
    # Get bridge subnet
    net_subnet=$(incus network get "$net" ipv4.address 2>/dev/null || true)
    if [[ "$net_subnet" == "${HOST_SUBNET}."* ]]; then
        echo "Deleting conflicting network: $net ($net_subnet)"
        # Force-delete: remove from projects first if needed
        incus network delete "$net" 2>/dev/null || true
    else
        echo "Keeping non-conflicting network: $net ($net_subnet)"
    fi
done

# ── Stop watcher ───────────────────────────────────────────────
kill "$WATCHER_PID" 2>/dev/null || true
trap - EXIT

# ── Verify/restore default route ──────────────────────────────
if ! ip route show default 2>/dev/null | grep -q "$DEFAULT_GW"; then
    echo "WARNING: Default route lost. Restoring..."
    ip route add default via "$DEFAULT_GW" dev "$DEFAULT_DEV" 2>/dev/null || true
fi

# ── Final verification ─────────────────────────────────────────
if ping -c1 -W2 "$DEFAULT_GW" &>/dev/null; then
    echo "OK: Network connectivity verified (gateway $DEFAULT_GW reachable)."
else
    echo "ERROR: Gateway $DEFAULT_GW unreachable. Network may be broken."
    echo "Try: sudo ip route add default via $DEFAULT_GW dev $DEFAULT_DEV"
    exit 1
fi

echo "Incus started safely."
