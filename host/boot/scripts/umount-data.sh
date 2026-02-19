#!/usr/bin/env bash
# umount-data.sh — Unmount AnKLuMe data partition and close LUKS encryption
# Usage: umount-data.sh
#
# This script safely unmounts the encrypted data partition and closes the
# LUKS device. It is called by anklume-data-mount.service during system shutdown.
#
# Behavior:
#   1. Detects pool type (ZFS or BTRFS) from /mnt/anklume-persist/pool.conf
#   2. Exports ZFS pool OR unmounts BTRFS filesystem
#   3. Closes LUKS encrypted partition
#   4. Handles graceful degradation if mount doesn't exist

set -euo pipefail

# ── Constants ──────────────────────────────────────────────

PERSIST_MNT="/mnt/anklume-persist"
DATA_MNT="/mnt/anklume-data"
POOL_CONF="$PERSIST_MNT/pool.conf"

# ── Logging helpers (ANSI colors) ──────────────────────────

info()  { echo -e "\033[0;34m[INFO]\033[0m $*"; }
ok()    { echo -e "\033[0;32m[ OK ]\033[0m $*"; }
warn()  { echo -e "\033[1;33m[WARN]\033[0m $*"; }
err()   { echo -e "\033[0;31m[ERR ]\033[0m $*" >&2; }

# ── Helper: Detect pool type ───────────────────────────────

detect_pool_type() {
    if [ ! -f "$POOL_CONF" ]; then
        warn "Pool config not found at $POOL_CONF"
        echo "unknown"
        return 0
    fi

    local pool_type
    pool_type=$(grep -oP '(?<=^POOL_TYPE=)\w+' "$POOL_CONF" 2>/dev/null || echo "unknown")

    case "$pool_type" in
        zfs|btrfs)
            echo "$pool_type"
            ;;
        *)
            warn "Unknown pool type in $POOL_CONF: $pool_type"
            echo "unknown"
            ;;
    esac
}

# ── Helper: Unmount or export data ─────────────────────────

umount_data() {
    local pool_type="$1"

    # Check if data mount point exists and is mounted
    if ! mountpoint -q "$DATA_MNT" 2>/dev/null; then
        info "Data partition not mounted at $DATA_MNT (nothing to do)"
        return 0
    fi

    case "$pool_type" in
        zfs)
            info "Exporting ZFS pool..."
            local pool_name
            pool_name=$(df "$DATA_MNT" 2>/dev/null | tail -1 | awk '{print $1}' | cut -d'/' -f1) || {
                warn "Could not determine ZFS pool name from mount"
                return 1
            }

            if [ -z "$pool_name" ] || [ "$pool_name" = "Filesystem" ]; then
                warn "Invalid pool name: $pool_name"
                return 1
            fi

            if zpool export "$pool_name" 2>/dev/null; then
                ok "ZFS pool $pool_name exported"
            else
                warn "Failed to export ZFS pool $pool_name (may retry on next boot)"
                return 1
            fi
            ;;

        btrfs)
            info "Unmounting BTRFS filesystem..."
            if umount "$DATA_MNT" 2>/dev/null; then
                ok "BTRFS filesystem unmounted from $DATA_MNT"
            else
                warn "Failed to unmount BTRFS filesystem (may retry on next boot)"
                return 1
            fi
            ;;

        *)
            info "Unknown pool type, attempting generic unmount..."
            if umount "$DATA_MNT" 2>/dev/null; then
                ok "Data partition unmounted from $DATA_MNT"
            else
                warn "Failed to unmount data partition (may retry on next boot)"
                return 1
            fi
            ;;
    esac

    return 0
}

# ── Helper: Close LUKS device ──────────────────────────────

close_luks() {
    # Find LUKS device backing the data mount
    local luks_dev

    # Try to find the device from mount
    luks_dev=$(df "$DATA_MNT" 2>/dev/null | tail -1 | awk '{print $1}') || {
        info "Could not determine underlying device (may not be LUKS encrypted)"
        return 0
    }

    if [ -z "$luks_dev" ] || [ "$luks_dev" = "Filesystem" ]; then
        info "No underlying device found (may not be encrypted)"
        return 0
    fi

    # Check if it's a LUKS device
    if cryptsetup isLuks "$luks_dev" 2>/dev/null; then
        info "Closing LUKS device: $luks_dev"

        # Extract mapper name if full path given
        local mapper_name
        mapper_name=$(basename "$luks_dev")

        # Try to close via cryptsetup
        if cryptsetup luksClose "$mapper_name" 2>/dev/null; then
            ok "LUKS device $mapper_name closed"
        else
            warn "Failed to close LUKS device $mapper_name (may retry on next boot)"
            return 1
        fi
    else
        info "Device $luks_dev is not LUKS encrypted"
    fi

    return 0
}

# ── Main function ─────────────────────────────────────────

main() {
    info "Starting AnKLuMe data partition unmount sequence..."

    # Detect pool type
    local pool_type
    pool_type=$(detect_pool_type)
    info "Detected pool type: $pool_type"

    # Unmount or export data
    if ! umount_data "$pool_type"; then
        warn "Unmount/export failed, continuing with LUKS close attempt..."
    fi

    # Close LUKS device
    if ! close_luks; then
        warn "LUKS close failed, but continuing gracefully..."
    fi

    ok "Data partition unmount sequence complete"
    return 0
}

main "$@"
