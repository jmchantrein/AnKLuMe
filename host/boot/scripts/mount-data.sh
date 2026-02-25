#!/usr/bin/env bash
# mount-data.sh — Mount LUKS-encrypted data partition (ZFS or BTRFS)
# Called by: anklume-data-mount.service
#
# This script:
#   1. Ensures persist partition is mounted
#   2. Reads pool configuration from pool.conf
#   3. Opens LUKS encrypted data partition
#   4. Detects and imports/mounts the filesystem (ZFS or BTRFS)
#   5. Verifies mount succeeded and logs success

set -euo pipefail

# ── Helper functions ──────────────────────────────────────

info()  { echo -e "\033[0;34m[INFO]\033[0m $*"; }
ok()    { echo -e "\033[0;32m[ OK ]\033[0m $*"; }
warn()  { echo -e "\033[1;33m[WARN]\033[0m $*"; }
err()   { echo -e "\033[0;31m[ERR ]\033[0m $*" >&2; }

# ── Source shared library ─────────────────────────────────

# Try to source from /opt/anklume/scripts first, then fallback to relative path
if [ -f /opt/anklume/scripts/live-os-lib.sh ]; then
    source /opt/anklume/scripts/live-os-lib.sh
else
    # Fallback: assume this script is in host/boot/scripts/
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
    if [ -f "$PROJECT_ROOT/scripts/live-os-lib.sh" ]; then
        source "$PROJECT_ROOT/scripts/live-os-lib.sh"
    else
        err "Could not source live-os-lib.sh"
        exit 1
    fi
fi

# ── Main function ─────────────────────────────────────────

main() {
    info "=== anklume Data Mount ==="

    # Step 1: Ensure persist partition is mounted
    info "Step 1: Mounting persist partition..."
    if ! ensure_persist_mounted; then
        err "Failed to mount persist partition"
        exit 1
    fi
    ok "Persist partition ready"

    # Step 2: Read pool configuration
    info "Step 2: Reading pool configuration from $POOL_CONF..."
    if [ ! -f "$POOL_CONF" ]; then
        err "Pool config not found: $POOL_CONF"
        exit 1
    fi

    local pool_name pool_type pool_uuid data_device

    # Parse pool.conf (expected format: key=value pairs)
    pool_name=$(grep "^pool_name=" "$POOL_CONF" | cut -d= -f2 | tr -d ' ')
    pool_type=$(grep "^pool_type=" "$POOL_CONF" | cut -d= -f2 | tr -d ' ')
    pool_uuid=$(grep "^pool_uuid=" "$POOL_CONF" | cut -d= -f2 | tr -d ' ')
    data_device=$(grep "^data_device=" "$POOL_CONF" | cut -d= -f2 | tr -d ' ')

    if [ -z "$pool_name" ] || [ -z "$pool_type" ] || [ -z "$data_device" ]; then
        err "Incomplete pool configuration"
        err "  pool_name=$pool_name, pool_type=$pool_type, data_device=$data_device"
        exit 1
    fi

    info "Pool config: name=$pool_name type=$pool_type device=$data_device"

    # Step 3: Open LUKS encrypted partition
    info "Step 3: Opening LUKS partition $data_device..."
    local luks_mapper_name="anklume-data-${pool_name}"

    # Check if already open
    if [ -e "/dev/mapper/$luks_mapper_name" ]; then
        ok "LUKS partition already open: $luks_mapper_name"
    else
        # Attempt to open LUKS partition (will prompt for passphrase interactively)
        if ! cryptsetup luksOpen "$data_device" "$luks_mapper_name"; then
            err "Failed to open LUKS partition $data_device"
            exit 1
        fi
        ok "LUKS partition opened: $luks_mapper_name"
    fi

    local decrypted_device="/dev/mapper/$luks_mapper_name"

    # Step 4: Mount/import the filesystem based on type
    info "Step 4: Mounting $pool_type filesystem..."

    case "$pool_type" in
        zfs)
            # Import ZFS pool
            info "Importing ZFS pool: $pool_name"
            if ! zpool list "$pool_name" &>/dev/null; then
                # Pool not imported, attempt import
                if ! zpool import -f "$pool_name"; then
                    err "Failed to import ZFS pool: $pool_name"
                    exit 1
                fi
                ok "ZFS pool imported: $pool_name"
            else
                ok "ZFS pool already imported: $pool_name"
            fi
            ;;
        btrfs)
            # Mount BTRFS filesystem
            info "Mounting BTRFS filesystem from $decrypted_device"

            # Create mount point if necessary
            if [ ! -d "$DATA_MNT" ]; then
                mkdir -p "$DATA_MNT" || {
                    err "Failed to create mount point $DATA_MNT"
                    exit 1
                }
            fi

            # Attempt mount
            if ! mount -t btrfs "$decrypted_device" "$DATA_MNT"; then
                err "Failed to mount BTRFS filesystem at $DATA_MNT"
                exit 1
            fi
            ok "BTRFS filesystem mounted at $DATA_MNT"
            ;;
        *)
            err "Unknown filesystem type: $pool_type (expected 'zfs' or 'btrfs')"
            exit 1
            ;;
    esac

    # Step 5: Verify mount/import succeeded
    info "Step 5: Verifying mount/import..."

    case "$pool_type" in
        zfs)
            if zpool list "$pool_name" &>/dev/null; then
                local pool_status
                pool_status=$(zpool status "$pool_name" 2>/dev/null | head -3)
                ok "ZFS pool verified as imported"
                printf "\033[0;34m[INFO]\033[0m Pool status:\n%s\n" "$pool_status"
            else
                err "ZFS pool import verification failed"
                exit 1
            fi
            ;;
        btrfs)
            if mountpoint -q "$DATA_MNT" 2>/dev/null; then
                ok "BTRFS filesystem verified as mounted at $DATA_MNT"
                local fs_info
                fs_info=$(df -h "$DATA_MNT" 2>/dev/null | tail -1)
                info "Filesystem info: $fs_info"
            else
                err "BTRFS filesystem mount verification failed"
                exit 1
            fi
            ;;
    esac

    # Success summary
    info "=== anklume Data Mount Complete ==="
    ok "Data partition successfully mounted/imported"
    ok "Pool: $pool_name ($pool_type)"
    ok "LUKS device: $luks_mapper_name"

    return 0
}

# ── Execute main ──────────────────────────────────────────

main "$@"
