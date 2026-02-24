#!/usr/bin/env bash
# live-update.sh — Live A/B OS image update mechanism for anklume
# Implements atomic slot-based updates with dm-verity, rollback support, and boot counting.
#
# Usage: live-update.sh [OPTIONS]
#
# Options:
#   --url URL               Download and install new OS image from URL
#   --verify-only           Download and verify but don't write or switch
#   --rollback              Rollback to previous active slot
#   --status                Show current update status
#   --help                  Show this help

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC2034  # referenced in sourced library
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Source shared library
# shellcheck source=/dev/null
source "$SCRIPT_DIR/live-os-lib.sh"

# ── Local constants ────────────────────────────────────────

DOWNLOAD_DIR="${DOWNLOAD_DIR:-/tmp/anklume-update}"
UPDATE_TIMESTAMP="$PERSIST_MNT/update-timestamp"
VERITY_HASHES="$PERSIST_MNT/verity-hashes"
PREVIOUS_SLOT_STATE="$PERSIST_MNT/previous-slot"
LAST_UPDATE_LOG="$PERSIST_MNT/last-update.log"

# ── Global state ──────────────────────────────────────────

OPERATION=""
UPDATE_URL=""
IMAGE_FILE=""
VERITY_FILE=""
CHECKSUM_FILE=""
TARGET_SLOT=""
TARGET_PARTITION=""

# ── Cleanup ────────────────────────────────────────────────

cleanup() {
    if [ -d "$DOWNLOAD_DIR" ] && [ -n "$DOWNLOAD_DIR" ]; then
        rm -rf "$DOWNLOAD_DIR" 2>/dev/null || true
    fi
}
trap cleanup EXIT

# ── Usage ──────────────────────────────────────────────────

usage() {
    cat << 'EOF'
Usage: live-update.sh [OPTIONS]

anklume Live OS A/B Update Manager
Safely download, verify, and install new OS images with automatic rollback.

Options:
  --url URL               Download and update OS from URL (without image.squashfs)
                         (will download image.squashfs, image.verity, image.sha256)
  --verify-only           Download and verify image but don't write
  --rollback              Rollback to previous active OS slot
  --status                Display current update and boot status
  --help                  Show this help message

Examples:
  # Download and install latest image
  live-update.sh --url https://releases.anklume.local/latest

  # Verify a new image without committing
  live-update.sh --url https://releases.anklume.local/v1.2.3 --verify-only

  # Check current status
  live-update.sh --status

  # Rollback to previous slot
  live-update.sh --rollback

EOF
    exit 0
}

# ── Logging and error handling ─────────────────────────────

# Note: info(), ok(), warn(), err() are sourced from live-os-lib.sh

log_to_file() {
    local msg="$1"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $msg" >> "$LAST_UPDATE_LOG" 2>/dev/null || true
}

# ── Dependency checking ────────────────────────────────────

check_dependencies() {
    info "Checking dependencies..."
    local missing=()
    local cmds=("curl" "veritysetup" "dd" "sha256sum" "jq" "blkid")

    for cmd in "${cmds[@]}"; do
        if ! command -v "$cmd" &>/dev/null; then
            missing+=("$cmd")
        fi
    done

    if [ ${#missing[@]} -gt 0 ]; then
        err "Missing dependencies: ${missing[*]}"
        return 1
    fi

    ok "All dependencies available"
    return 0
}

# ── Download image and metadata ────────────────────────────

download_image() {
    local url="$1"

    info "Downloading OS image from: $url"

    # Create download directory
    mkdir -p "$DOWNLOAD_DIR" || {
        err "Failed to create download directory: $DOWNLOAD_DIR"
        return 1
    }

    # Download squashfs image
    info "  Downloading image.squashfs..."
    if ! curl -fL --progress-bar "$url/image.squashfs" -o "$IMAGE_FILE"; then
        err "Failed to download image.squashfs"
        return 1
    fi
    local img_size
    img_size=$(du -h "$IMAGE_FILE" | cut -f1)
    ok "  Downloaded: $img_size"

    # Download verity metadata
    info "  Downloading image.verity..."
    if ! curl -fL --progress-bar "$url/image.verity" -o "$VERITY_FILE"; then
        err "Failed to download image.verity"
        return 1
    fi
    local verity_size
    verity_size=$(du -h "$VERITY_FILE" | cut -f1)
    ok "  Downloaded: $verity_size"

    # Download SHA256 checksum file
    info "  Downloading image.sha256..."
    if ! curl -fL --progress-bar "$url/image.sha256" -o "$CHECKSUM_FILE"; then
        err "Failed to download image.sha256"
        return 1
    fi
    ok "  Downloaded"

    ok "All files downloaded"
    return 0
}

# ── Verify downloaded image ────────────────────────────────

verify_image() {
    info "Verifying image integrity..."

    # Check SHA256 checksum
    info "  Checking SHA256 checksum..."
    if ! sha256sum -c "$CHECKSUM_FILE" >/dev/null 2>&1; then
        err "SHA256 checksum verification failed"
        return 1
    fi
    ok "  SHA256 verified"

    # Check for GPG signature (optional)
    if [ -f "$DOWNLOAD_DIR/image.squashfs.sig" ]; then
        info "  Checking GPG signature..."
        if command -v gpg &>/dev/null; then
            if gpg --verify "$DOWNLOAD_DIR/image.squashfs.sig" "$IMAGE_FILE" >/dev/null 2>&1; then
                ok "  GPG signature verified"
            else
                warn "  GPG signature verification failed (continuing anyway)"
            fi
        else
            warn "  GPG not available (skipping signature verification)"
        fi
    fi

    ok "Image verification complete"
    return 0
}

# ── Determine target partition ─────────────────────────────

get_target_partition() {
    info "Determining target partition..."

    # Ensure persist mounted to read active slot
    ensure_persist_mounted || {
        err "Failed to mount persistent partition"
        return 1
    }

    # Get active slot and compute target
    local active_slot
    active_slot=$(get_active_slot)
    TARGET_SLOT=$(get_inactive_slot)

    info "  Active slot: $active_slot"
    info "  Target slot: $TARGET_SLOT"

    # Get the target partition label
    local target_label
    if [ "$TARGET_SLOT" = "A" ]; then
        target_label="$ANKLUME_OSA_LABEL"
    else
        target_label="$ANKLUME_OSB_LABEL"
    fi

    # Find partition device
    TARGET_PARTITION=$(find_partition_by_label "$target_label") || {
        err "Failed to find target partition: $target_label"
        return 1
    }

    if [ -z "$TARGET_PARTITION" ]; then
        err "Target partition not found: $target_label"
        return 1
    fi

    info "  Target partition: $TARGET_PARTITION"
    ok "Target determined"
    return 0
}

# ── Write image to target partition ────────────────────────

write_image() {
    info "Writing image to $TARGET_PARTITION..."

    if [ ! -b "$TARGET_PARTITION" ]; then
        err "Target is not a block device: $TARGET_PARTITION"
        return 1
    fi

    # Write with dd and progress
    info "  Writing squashfs (this may take a while)..."
    if ! dd if="$IMAGE_FILE" of="$TARGET_PARTITION" bs=4M status=progress 2>&1 | tail -1; then
        err "Failed to write image"
        return 1
    fi

    # Sync to ensure all data written
    info "  Syncing filesystem..."
    sync

    ok "Image written"

    # Verify written data
    info "  Verifying written data..."
    local written_checksum
    written_checksum=$(sha256sum "$TARGET_PARTITION" | awk '{print $1}')
    local expected_checksum
    expected_checksum=$(sha256sum "$IMAGE_FILE" | awk '{print $1}')

    if [ "$written_checksum" != "$expected_checksum" ]; then
        err "Verification failed: checksums don't match"
        err "  Expected: $expected_checksum"
        err "  Got:      $written_checksum"
        return 1
    fi

    ok "Verification successful"
    return 0
}

# ── Setup dm-verity for new image ──────────────────────────

setup_verity_for_slot() {
    info "Setting up dm-verity for slot $TARGET_SLOT..."

    # Extract verity hash from metadata file
    if [ ! -f "$VERITY_FILE" ]; then
        err "Verity metadata file not found: $VERITY_FILE"
        return 1
    fi

    # Parse verity hash from JSON metadata
    local verity_hash
    verity_hash=$(jq -r '.verity_hash // empty' "$VERITY_FILE" 2>/dev/null) || {
        # Fallback: try to parse as plain text if first line is hash
        verity_hash=$(head -1 "$VERITY_FILE" 2>/dev/null)
    }

    if [ -z "$verity_hash" ]; then
        err "Failed to extract verity hash from metadata"
        return 1
    fi

    info "  Verity hash: ${verity_hash:0:16}..."

    # Ensure persist mounted to store hash
    ensure_persist_mounted || {
        err "Failed to mount persistent partition"
        return 1
    }

    # Store verity hash for boot entry
    mkdir -p "$(dirname "$VERITY_HASHES")"
    {
        echo "# Verity hashes for A/B slots"
        if [ "$TARGET_SLOT" = "A" ]; then
            echo "SLOT_A_HASH=$verity_hash"
            if grep -q "^SLOT_B_HASH=" "$VERITY_HASHES" 2>/dev/null; then
                grep "^SLOT_B_HASH=" "$VERITY_HASHES"
            fi
        else
            echo "SLOT_B_HASH=$verity_hash"
            if grep -q "^SLOT_A_HASH=" "$VERITY_HASHES" 2>/dev/null; then
                grep "^SLOT_A_HASH=" "$VERITY_HASHES"
            fi
        fi
    } > "$VERITY_HASHES.tmp" 2>/dev/null
    mv "$VERITY_HASHES.tmp" "$VERITY_HASHES" 2>/dev/null || true

    ok "Verity setup complete"
    return 0
}

# ── Update systemd-boot entry ──────────────────────────────

update_bootloader() {
    info "Updating bootloader entry for slot $TARGET_SLOT..."

    # Find EFI partition
    local efi_partition
    efi_partition=$(find_partition_by_label "$ANKLUME_EFI_LABEL") || {
        err "Failed to find EFI partition"
        return 1
    }

    if [ -z "$efi_partition" ]; then
        err "EFI partition not found"
        return 1
    fi

    # Mount EFI partition
    local efi_mount="/mnt/anklume-efi-update"
    mkdir -p "$efi_mount"

    if ! mount "$efi_partition" "$efi_mount" 2>/dev/null; then
        err "Failed to mount EFI partition"
        return 1
    fi

    # Ensure we unmount on exit
    # shellcheck disable=SC2064  # Intentional: expand efi_mount now
    trap "umount '$efi_mount' 2>/dev/null || true" RETURN

    # Get verity hash for target slot
    ensure_persist_mounted || {
        err "Failed to mount persistent partition"
        return 1
    }

    local verity_hash
    if [ "$TARGET_SLOT" = "A" ]; then
        verity_hash=$(grep "^SLOT_A_HASH=" "$VERITY_HASHES" 2>/dev/null | cut -d= -f2)
    else
        verity_hash=$(grep "^SLOT_B_HASH=" "$VERITY_HASHES" 2>/dev/null | cut -d= -f2)
    fi

    if [ -z "$verity_hash" ]; then
        warn "Could not find verity hash, using placeholder"
        verity_hash="unknown"
    fi

    # Update boot entry
    local entry_file="$efi_mount/loader/entries/anklume-${TARGET_SLOT,,}.conf"

    if [ ! -f "$entry_file" ]; then
        warn "Boot entry not found: $entry_file"
    else
        info "  Updating boot entry: $(basename "$entry_file")"

        # Read current entry and update tries-left
        local entry_title="anklume (Slot $TARGET_SLOT)"
        cat > "$entry_file.tmp" << ENTRY_EOF
title           $entry_title
linux           /vmlinuz
initrd          /initrd.img
options         root=/dev/dm-0 ro anklume.slot=$TARGET_SLOT anklume.verity_hash=$verity_hash anklume.toram=1 systemd.unified_cgroup_hierarchy=0
tries           3
tries-left      3
ENTRY_EOF

        mv "$entry_file.tmp" "$entry_file"
        ok "  Boot entry updated"
    fi

    # Update loader.conf to set default boot entry
    local loader_conf="$efi_mount/loader/loader.conf"
    if [ -f "$loader_conf" ]; then
        info "  Updating default boot entry..."
        sed -i "s/^default .*/default anklume-${TARGET_SLOT,,}/" "$loader_conf"
        ok "  Default boot entry set to anklume-${TARGET_SLOT,,}"
    fi

    umount "$efi_mount" 2>/dev/null || true

    ok "Bootloader updated"
    return 0
}

# ── Switch to new slot (atomic) ────────────────────────────

switch_slot() {
    info "Switching active slot to $TARGET_SLOT..."

    ensure_persist_mounted || {
        err "Failed to mount persistent partition"
        return 1
    }

    # Set new active slot
    set_active_slot "$TARGET_SLOT" || {
        err "Failed to set active slot"
        return 1
    }

    # Reset boot counter for new slot
    reset_boot_count || {
        err "Failed to reset boot count"
        return 1
    }

    # Record timestamp
    date +%s > "$UPDATE_TIMESTAMP" 2>/dev/null || true

    # Record previous slot
    local previous_slot
    if [ "$TARGET_SLOT" = "A" ]; then
        previous_slot="B"
    else
        previous_slot="A"
    fi
    echo "$previous_slot" > "$PREVIOUS_SLOT_STATE" 2>/dev/null || true

    log_to_file "Successfully switched to slot $TARGET_SLOT"

    ok "Slot switched successfully"
    return 0
}

# ── Rollback to previous slot ──────────────────────────────

rollback() {
    info "Initiating rollback..."

    ensure_persist_mounted || {
        err "Failed to mount persistent partition"
        return 1
    }

    # Get current active slot
    local current_slot
    current_slot=$(get_active_slot)

    # Determine previous slot
    local previous_slot
    if [ "$current_slot" = "A" ]; then
        previous_slot="B"
    else
        previous_slot="A"
    fi

    info "  Current slot: $current_slot"
    info "  Rollback slot: $previous_slot"

    TARGET_SLOT="$previous_slot"

    # Switch back to previous slot
    set_active_slot "$TARGET_SLOT" || {
        err "Failed to set active slot to $TARGET_SLOT"
        return 1
    }

    # Reset boot counter
    reset_boot_count || {
        err "Failed to reset boot count"
        return 1
    }

    # Update bootloader
    update_bootloader || {
        err "Failed to update bootloader"
        return 1
    }

    log_to_file "Rollback to slot $TARGET_SLOT completed"

    ok "Rollback successful"
    ok "Next boot will use slot $TARGET_SLOT"
    ok "Reboot to complete rollback"
    return 0
}

# ── Display status ─────────────────────────────────────────

status() {
    echo ""
    echo "=== anklume Update Status ==="
    echo ""

    ensure_persist_mounted || {
        warn "Persistent partition not mounted, showing cached info only"
    }

    # Active and inactive slots
    local active_slot
    active_slot=$(get_active_slot)
    local inactive_slot
    inactive_slot=$(get_inactive_slot)

    echo "Boot Status:"
    echo "  Active slot:   $active_slot"
    echo "  Inactive slot: $inactive_slot"

    # Boot count
    local boot_count
    boot_count=$(get_boot_count)
    echo "  Boot count:    $boot_count"

    # Last update time
    if [ -f "$UPDATE_TIMESTAMP" ]; then
        local update_time
        update_time=$(cat "$UPDATE_TIMESTAMP")
        local formatted_time
        formatted_time=$(date -d "@$update_time" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo "unknown")
        echo "  Last update:   $formatted_time"
    else
        echo "  Last update:   Never"
    fi

    # Verity hashes
    echo ""
    echo "Verity Hashes:"
    if [ -f "$VERITY_HASHES" ]; then
        while IFS= read -r line; do
            if [[ "$line" =~ ^SLOT_[AB]_HASH= ]]; then
                local slot
                local hash
                slot=$(echo "$line" | cut -d= -f1 | sed 's/SLOT_//;s/_HASH//')
                hash=$(echo "$line" | cut -d= -f2)
                echo "  Slot $slot: ${hash:0:32}..."
            fi
        done < "$VERITY_HASHES"
    else
        echo "  No hashes recorded"
    fi

    # Last update log
    echo ""
    if [ -f "$LAST_UPDATE_LOG" ]; then
        echo "Recent updates:"
        tail -5 "$LAST_UPDATE_LOG" | sed 's/^/  /'
    else
        echo "No update history recorded"
    fi

    echo ""
}

# ── Main orchestration ─────────────────────────────────────

main() {
    while [ $# -gt 0 ]; do
        case "$1" in
            --url)       UPDATE_URL="$2"; OPERATION="update"; shift 2 ;;
            --verify-only) OPERATION="verify-only"; shift ;;
            --rollback)  OPERATION="rollback"; shift ;;
            --status)    OPERATION="status"; shift ;;
            --help|-h)   usage ;;
            *)           err "Unknown option: $1"; usage ;;
        esac
    done

    # Set image file paths
    IMAGE_FILE="$DOWNLOAD_DIR/image.squashfs"
    VERITY_FILE="$DOWNLOAD_DIR/image.verity"
    CHECKSUM_FILE="$DOWNLOAD_DIR/image.sha256"

    echo "=== anklume Live Update Manager ==="
    echo ""

    case "$OPERATION" in
        status)
            status
            ;;

        rollback)
            check_dependencies || exit 1
            rollback || exit 1
            ;;

        update)
            if [ -z "$UPDATE_URL" ]; then
                err "No URL specified (use --url)"
                usage
            fi

            check_dependencies || exit 1
            download_image "$UPDATE_URL" || exit 1
            verify_image || exit 1
            get_target_partition || exit 1
            write_image || exit 1
            setup_verity_for_slot || exit 1
            update_bootloader || exit 1
            switch_slot || exit 1

            log_to_file "Update completed successfully to slot $TARGET_SLOT"

            echo ""
            ok "Update successful!"
            echo "  New slot:  $TARGET_SLOT"
            echo "  Next boot will use: $(get_active_slot)"
            echo ""
            echo "Reboot now to boot from the new slot:"
            echo "  sudo reboot"
            echo ""
            ;;

        verify-only)
            if [ -z "$UPDATE_URL" ]; then
                err "No URL specified (use --url)"
                usage
            fi

            check_dependencies || exit 1
            download_image "$UPDATE_URL" || exit 1
            verify_image || exit 1
            get_target_partition || exit 1

            echo ""
            ok "Image verification successful!"
            echo "  Target slot: $TARGET_SLOT"
            echo "  To apply: live-update.sh --url $UPDATE_URL"
            echo ""
            ;;

        *)
            err "No operation specified"
            usage
            ;;
    esac

    ok "Operation complete"
}

main "$@"
