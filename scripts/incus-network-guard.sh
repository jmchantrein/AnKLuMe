#!/usr/bin/env bash
# incus-network-guard.sh — Prevent Incus bridges from breaking host network
#
# Runs as ExecStartPost in incus.service. Detects and removes any Incus
# managed bridge whose subnet conflicts with the host's real network.
# Uses only local kernel calls (ip link) — works even if network is broken.
#
# Install: sudo scripts/install-incus-guard.sh
set -euo pipefail

LOGFILE="/var/log/incus-network-guard.log"
log() { echo "$(date -Iseconds) $*" | tee -a "$LOGFILE"; }

# ── Detect host network interface and subnet ──────────────────
# Find the interface with the default route
DEFAULT_DEV=$(ip route show default 2>/dev/null | awk 'NR==1{print $5}')
if [[ -z "$DEFAULT_DEV" ]]; then
    # Default route already gone — try to find it from saved state
    if [[ -f /run/incus-guard-host-dev ]]; then
        DEFAULT_DEV=$(cat /run/incus-guard-host-dev)
    else
        log "ERROR: No default route and no saved state. Cannot determine host network."
        exit 0  # Don't block Incus startup
    fi
fi

# Save host interface name for recovery
echo "$DEFAULT_DEV" > /run/incus-guard-host-dev

# Get host subnet prefix (e.g., "10.100.0")
HOST_PREFIX=$(ip -4 addr show "$DEFAULT_DEV" 2>/dev/null \
    | grep -oP 'inet \K[0-9]+\.[0-9]+\.[0-9]+' | head -1)
if [[ -z "$HOST_PREFIX" ]]; then
    log "WARNING: Cannot determine host subnet on $DEFAULT_DEV"
    exit 0
fi

# Get default gateway
DEFAULT_GW=$(ip route show default dev "$DEFAULT_DEV" 2>/dev/null | awk 'NR==1{print $3}')

log "Host network: ${HOST_PREFIX}.0/24 on $DEFAULT_DEV (gw: ${DEFAULT_GW:-unknown})"

# ── Delete conflicting bridges at kernel level ────────────────
# ip link is a local kernel call — works even with broken network
# Check ALL bridges (not just net-*) because incus network create
# without explicit ipv4.address auto-assigns a random subnet
CONFLICTS_FOUND=0
CONFLICT_NAMES=()
for iface in $(ip -o link show type bridge 2>/dev/null \
        | grep -oP '\d+: \K[a-z0-9][a-z0-9-]+' || true); do
    # Skip the host's own interface
    [[ "$iface" == "$DEFAULT_DEV" ]] && continue
    bridge_prefix=$(ip -4 addr show "$iface" 2>/dev/null \
        | grep -oP 'inet \K[0-9]+\.[0-9]+\.[0-9]+' || true)
    if [[ "$bridge_prefix" == "$HOST_PREFIX" ]]; then
        log "CONFLICT: Bridge $iface uses ${bridge_prefix}.x — same as host. Removing."
        ip link set "$iface" down 2>/dev/null || true
        ip link delete "$iface" 2>/dev/null || true
        CONFLICTS_FOUND=$((CONFLICTS_FOUND + 1))
        CONFLICT_NAMES+=("$iface")
    fi
done

# ── Also delete via Incus CLI to clean the database ───────────
if [[ $CONFLICTS_FOUND -gt 0 ]]; then
    sleep 1  # Give Incus a moment
    for net in $(incus network list --format csv 2>/dev/null \
            | cut -d, -f1 || true); do
        net_addr=$(incus network get "$net" ipv4.address 2>/dev/null || true)
        if [[ "$net_addr" == "${HOST_PREFIX}."* ]]; then
            log "Cleaning Incus DB: deleting network $net ($net_addr)"
            incus network delete "$net" 2>/dev/null || true
        fi
    done
fi

# ── Restore default route if it was lost ──────────────────────
if [[ -n "$DEFAULT_GW" ]]; then
    if ! ip route show default 2>/dev/null | grep -q "$DEFAULT_GW"; then
        log "WARNING: Default route lost. Restoring via $DEFAULT_GW dev $DEFAULT_DEV"
        ip route add default via "$DEFAULT_GW" dev "$DEFAULT_DEV" 2>/dev/null || true
    fi
fi

if [[ $CONFLICTS_FOUND -eq 0 ]]; then
    log "OK: No conflicting bridges found."
else
    log "OK: Removed $CONFLICTS_FOUND conflicting bridge(s). Network restored."
fi
