#!/usr/bin/env bash
# live-os-lib.sh — Shared library for anklume live OS operations
# This is a library file to be sourced by other scripts, not executed directly.
#
# Provides:
#   - Logging helpers (info, ok, warn, err)
#   - Partition and mount constants
#   - Boot state management functions
#   - RAM encryption detection
#   - Partition discovery utilities

set -euo pipefail

# ── Logging helpers (ANSI colors) ──────────────────────────

info()  { echo -e "\033[0;34m[INFO]\033[0m $*"; }
ok()    { echo -e "\033[0;32m[ OK ]\033[0m $*"; }
warn()  { echo -e "\033[1;33m[WARN]\033[0m $*"; }
err()   { echo -e "\033[0;31m[ERR ]\033[0m $*" >&2; }

# ── Partition label constants ──────────────────────────────

ANKLUME_EFI_LABEL="ANKLUME-EFI"
ANKLUME_OSA_LABEL="ANKLUME-OS-A"
ANKLUME_OSB_LABEL="ANKLUME-OS-B"
ANKLUME_PERSIST_LABEL="ANKLUME-PERSIST"
ANKLUME_DATA_LABEL="ANKLUME-DATA"

# ── Partition size constants (MB) ──────────────────────────

EFI_SIZE_MB=512
OS_SIZE_MB=1536
PERSIST_SIZE_MB=100

# ── Mount point constants ──────────────────────────────────

PERSIST_MNT="/mnt/anklume-persist"
DATA_MNT="/mnt/anklume-data"

# ── Config file paths ──────────────────────────────────────

POOL_CONF="$PERSIST_MNT/pool.conf"
AB_STATE="$PERSIST_MNT/ab-state"
BOOT_COUNT="$PERSIST_MNT/boot-count"

# ── Boot state management ──────────────────────────────────

# get_active_slot() - Reads the active A/B slot from persistent storage
# Returns: "A", "B", or "A" (default if not set)
# Exit status: 0 on success, non-zero if persist not mounted
get_active_slot() {
    if [ ! -f "$AB_STATE" ]; then
        echo "A"
        return 0
    fi
    local slot
    slot=$(<"$AB_STATE")
    case "$slot" in
        A|B) echo "$slot" ;;
        *)   echo "A" ;;
    esac
}

# set_active_slot(slot) - Writes the active A/B slot to persistent storage
# Arguments: slot - "A" or "B"
# Exit status: 0 on success, 1 if invalid slot, 2 if write fails
set_active_slot() {
    local slot="$1"
    if [ "$slot" != "A" ] && [ "$slot" != "B" ]; then
        err "Invalid slot: $slot (must be A or B)"
        return 1
    fi
    if ! echo "$slot" > "$AB_STATE" 2>/dev/null; then
        err "Failed to write active slot to $AB_STATE"
        return 2
    fi
    ok "Active slot set to $slot"
    return 0
}

# get_inactive_slot() - Returns the opposite of the active slot
# Returns: "A" or "B"
get_inactive_slot() {
    local active
    active=$(get_active_slot)
    case "$active" in
        A) echo "B" ;;
        B) echo "A" ;;
        *) echo "B" ;;
    esac
}

# ── Boot counting ──────────────────────────────────────────

# get_boot_count() - Reads the boot counter from persistent storage
# Returns: Non-negative integer, or 0 if not set
get_boot_count() {
    if [ ! -f "$BOOT_COUNT" ]; then
        echo "0"
        return 0
    fi
    local count
    count=$(<"$BOOT_COUNT")
    if ! echo "$count" | grep -qE '^[0-9]+$'; then
        echo "0"
        return 0
    fi
    echo "$count"
}

# increment_boot_count() - Increments the boot counter
# Exit status: 0 on success, 1 if write fails
increment_boot_count() {
    local count
    count=$(get_boot_count)
    count=$((count + 1))
    if ! echo "$count" > "$BOOT_COUNT" 2>/dev/null; then
        err "Failed to increment boot count in $BOOT_COUNT"
        return 1
    fi
    ok "Boot count incremented to $count"
    return 0
}

# reset_boot_count() - Resets the boot counter to 0
# Exit status: 0 on success, 1 if write fails
reset_boot_count() {
    if ! echo "0" > "$BOOT_COUNT" 2>/dev/null; then
        err "Failed to reset boot count in $BOOT_COUNT"
        return 1
    fi
    ok "Boot count reset to 0"
    return 0
}

# ── RAM encryption detection ───────────────────────────────

# detect_ram_encryption() - Detects RAM encryption technology
# Checks for AMD SME/SEV or Intel TME via dmesg and cpuinfo
# Returns: "amd-sme", "amd-sev", "intel-tme", or "none"
# Exit status: Always 0
detect_ram_encryption() {
    # Check AMD Secure Memory Encryption (SME)
    if grep -qi "amd-sme" /proc/cpuinfo 2>/dev/null; then
        echo "amd-sme"
        return 0
    fi

    # Check AMD Secure Encrypted Virtualization (SEV)
    if grep -qi "sev" /proc/cpuinfo 2>/dev/null; then
        echo "amd-sev"
        return 0
    fi

    # Check Intel Total Memory Encryption (TME)
    if grep -qi "tme" /proc/cpuinfo 2>/dev/null; then
        echo "intel-tme"
        return 0
    fi

    # Fallback: check dmesg for encryption indicators
    if dmesg 2>/dev/null | grep -qi "memory encryption enabled"; then
        if dmesg 2>/dev/null | grep -qi "amd"; then
            echo "amd-sme"
        elif dmesg 2>/dev/null | grep -qi "intel"; then
            echo "intel-tme"
        else
            echo "amd-sme"
        fi
        return 0
    fi

    echo "none"
    return 0
}

# ── Partition discovery ────────────────────────────────────

# find_partition_by_label(label) - Locates a partition by filesystem label
# Arguments: label - Partition label to search for
# Returns: Device path (e.g., /dev/sda1), or empty string if not found
# Exit status: 0 if found, 1 if not found, 2 on command failure
find_partition_by_label() {
    local label="$1"

    if [ -z "$label" ]; then
        err "Label argument required"
        return 2
    fi

    # Use blkid to find partition by label
    if ! command -v blkid &>/dev/null; then
        err "blkid command not found"
        return 2
    fi

    local device
    device=$(blkid -L "$label" 2>/dev/null) || {
        return 1
    }

    if [ -n "$device" ]; then
        echo "$device"
        return 0
    fi

    return 1
}

# ── Persistent storage mounting ────────────────────────────

# ensure_persist_mounted() - Mounts the persistent partition if not already mounted
# Uses find_partition_by_label() to locate ANKLUME_PERSIST_LABEL
# Creates mount point if it doesn't exist
# Exit status: 0 on success, 1 if partition not found, 2 if mount fails
ensure_persist_mounted() {
    # Check if already mounted
    if mountpoint -q "$PERSIST_MNT" 2>/dev/null; then
        ok "Persist partition already mounted at $PERSIST_MNT"
        return 0
    fi

    # Find the persistent partition by label
    local persist_dev
    persist_dev=$(find_partition_by_label "$ANKLUME_PERSIST_LABEL") || {
        err "Could not find persistent partition (label: $ANKLUME_PERSIST_LABEL)"
        return 1
    }

    if [ -z "$persist_dev" ]; then
        err "Persistent partition not found"
        return 1
    fi

    info "Found persist partition: $persist_dev"

    # Create mount point if necessary
    if [ ! -d "$PERSIST_MNT" ]; then
        mkdir -p "$PERSIST_MNT" || {
            err "Failed to create mount point $PERSIST_MNT"
            return 2
        }
    fi

    # Mount the partition
    if ! mount "$persist_dev" "$PERSIST_MNT" 2>/dev/null; then
        err "Failed to mount $persist_dev at $PERSIST_MNT"
        return 2
    fi

    ok "Persist partition mounted at $PERSIST_MNT"
    return 0
}

# Export all constants and functions for use by sourcing scripts
export ANKLUME_EFI_LABEL ANKLUME_OSA_LABEL ANKLUME_OSB_LABEL
export ANKLUME_PERSIST_LABEL ANKLUME_DATA_LABEL
export EFI_SIZE_MB OS_SIZE_MB PERSIST_SIZE_MB
export PERSIST_MNT DATA_MNT
export POOL_CONF AB_STATE BOOT_COUNT
export -f info ok warn err
export -f get_active_slot set_active_slot get_inactive_slot
export -f get_boot_count increment_boot_count reset_boot_count
export -f detect_ram_encryption find_partition_by_label ensure_persist_mounted
