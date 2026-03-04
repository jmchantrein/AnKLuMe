#!/usr/bin/env bash
# start.sh: anklume host setup — storage, framework bootstrap, and resume
#
# Detects existing anklume installations and offers to resume them.
# On fresh disks: creates storage pools (ZFS, BTRFS, or dir), copies the
# framework, and bootstraps the initial Incus container.
#
# Usage: start.sh [--yes] [--disk DEVICE] [--backend zfs|btrfs|dir]
#
# Requires: root, Incus daemon running, lsblk, cryptsetup

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Source shared library
# shellcheck source=/dev/null
source "$SCRIPT_DIR/live-os-lib.sh"

# ─────────────────────────────────────────────────────────────────────────────
# DISTRO DETECTION
# ─────────────────────────────────────────────────────────────────────────────

# Detect host distribution for package manager guidance
detect_distro() {
    if [ -f /etc/os-release ]; then
        # shellcheck source=/dev/null
        . /etc/os-release
        case "$ID" in
            arch|cachyos|endeavouros|manjaro) echo "arch" ;;
            debian|ubuntu|linuxmint)          echo "debian" ;;
            *)                                echo "unknown" ;;
        esac
    else
        echo "unknown"
    fi
}

HOST_DISTRO="$(detect_distro)"

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

declare -r SCRIPT_VERSION="1.0.0"
declare -r ANKLUME_REPO="${ANKLUME_REPO:-$PROJECT_ROOT}"
declare -r BOOTSTRAP_IMAGE="${BOOTSTRAP_IMAGE:-$(
    case "$HOST_DISTRO" in
        arch)   echo "images:archlinux/current/amd64" ;;
        *)      echo "images:debian/12/amd64" ;;
    esac
)}"
declare -r POOL_NAME="anklume-data"
# shellcheck disable=SC2034  # referenced in sourced scripts
declare -r INCUS_DIR="/var/lib/incus"
declare -r LUKS_NAME="anklume-crypt"
declare -r POOL_CONF_FILE="pool.conf"

# Color codes for output
# shellcheck disable=SC2034  # Colors used in helper functions
declare -r RED='\033[0;31m' GREEN='\033[0;32m' YELLOW='\033[1;33m'
declare -r BLUE='\033[0;34m'
declare -r NC='\033[0m' # No Color

# ─────────────────────────────────────────────────────────────────────────────
# GLOBAL STATE
# ─────────────────────────────────────────────────────────────────────────────

DISK=""
BACKEND=""
CONFIRM_YES=false
LUKS_ENABLED=false
LUKS_PASSWORD=""
POOL_MOUNT_POINT=""

# ─────────────────────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

die() {
    err "$@"
    exit 1
}

# Lock file to prevent concurrent runs (service on tty + manual invocation)
LOCK_FILE="/run/anklume-start.lock"
LOCK_OWNED=false

cleanup_lock() {
    if [[ "$LOCK_OWNED" == "true" ]]; then
        rm -f "$LOCK_FILE" 2>/dev/null || true
    fi
}

# info(), ok(), warn(), err() provided by live-os-lib.sh
success() { ok "$@"; }

prompt_yes_no() {
    local prompt="$1"
    local response

    if [[ "$CONFIRM_YES" == "true" ]]; then
        echo -e "${BLUE}[AUTO-YES]${NC} ${prompt}"
        return 0
    fi

    while true; do
        read -r -p "${prompt} (y/n): " response
        case "${response}" in
            [yY]) return 0 ;;
            [nN]) return 1 ;;
            *) echo "Please answer y or n" ;;
        esac
    done
}

# ─────────────────────────────────────────────────────────────────────────────
# DISK AND DETECTION FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

usage() {
    cat <<'USAGE'
Usage: start.sh [--yes] [--disk DEVICE] [--backend zfs|btrfs] [--list] [-h|--help]

Initialize Incus storage pools and bootstrap the anklume framework.

Options:
  --yes                 Skip all confirmations (dangerous, use with care)
  --disk DEVICE         Specify target disk (e.g., /dev/sdb, /dev/vda)
  --backend zfs|btrfs   Specify storage backend (prompt if omitted)
  --list                List available disks and exit
  -h, --help            Show this help message

Examples:
  start.sh --list
  start.sh --disk /dev/sdb --backend zfs
  start.sh --yes --disk /dev/sdb --backend btrfs

IMPORTANT: This script will DESTROY DATA on the selected disk.
Always run with --list first to verify disk identification.

USAGE
}

list_disks() {
    info "Available disks (excluding system disk):"
    echo ""

    # Get root device (findmnt works on live ISO overlayfs too)
    local root_dev root_src
    root_src=$(findmnt -no SOURCE / 2>/dev/null | head -1 || echo "")
    root_dev=$(lsblk -no PKNAME "$root_src" 2>/dev/null | head -1 || echo "")

    # List all block devices
    lsblk -d -o NAME,SIZE,TYPE,MODEL -x NAME | while read -r name size type model; do
        if [[ "$name" == "NAME" ]]; then
            continue
        fi

        local dev="/dev/${name}"

        # Skip the root device
        if [[ -n "$root_dev" ]] && [[ "$dev" == "/dev/$root_dev"* ]]; then
            echo "  $dev  $size  [SKIP: root filesystem]"
            continue
        fi

        # Skip small devices (< 100 GB assumed to be system disks)
        local size_gb
        size_gb=$(echo "$size" | sed 's/[^0-9.].*//' | cut -d. -f1)
        if [[ "$size_gb" -lt 100 ]]; then
            echo "  $dev  $size  [SKIP: too small]"
            continue
        fi

        echo "  $dev  $size  $type  $model"
    done

    echo ""
    echo "Recommendations:"
    echo "  - Use a dedicated disk (not the system disk)"
    echo "  - Minimum 500 GB recommended for production"
    echo "  - Verify the correct disk before proceeding"
}

detect_data_disks() {
    info "Detecting available data disks..." >&2

    # Get root device (findmnt works on live ISO overlayfs too)
    local root_dev root_src
    root_src=$(findmnt -no SOURCE / 2>/dev/null | head -1 || echo "")
    root_dev=$(lsblk -no PKNAME "$root_src" 2>/dev/null | head -1 || echo "")

    local -a candidates=()

    while IFS= read -r line; do
        local dev name size_raw
        name=$(echo "$line" | awk '{print $1}')
        dev="/dev/${name}"
        size_raw=$(echo "$line" | awk '{print $2}')

        # Skip root device
        if [[ -n "$root_dev" ]] && [[ "$dev" == "/dev/$root_dev"* ]]; then
            continue
        fi

        # Skip small devices
        local size_gb
        size_gb=$(echo "$size_raw" | sed 's/[^0-9.].*//' | cut -d. -f1)
        if [[ "$size_gb" -lt 100 ]]; then
            continue
        fi

        candidates+=("$dev")
    done < <(lsblk -d -o NAME,SIZE -x NAME | tail -n +2)

    if [[ ${#candidates[@]} -eq 0 ]]; then
        die "No suitable data disks found. Minimum 100 GB required."
    fi

    printf '%s\n' "${candidates[@]}"
}

select_disk() {
    local -a disks
    mapfile -t disks < <(detect_data_disks) || true

    # Guard: no disks found (detect_data_disks dies in subshell,
    # but mapfile swallows the exit code and produces empty array)
    if [[ ${#disks[@]} -eq 0 ]]; then
        die "No suitable data disks found. Need at least one disk >= 100 GB."
    fi

    if [[ ${#disks[@]} -eq 1 ]]; then
        DISK="${disks[0]}"
        info "Single data disk detected: $DISK"
        return 0
    fi

    info "Multiple disks available. Please select:"
    echo ""

    local i=1
    for disk in "${disks[@]}"; do
        local size
        size=$(lsblk -d -o SIZE -n "$disk" 2>/dev/null || echo "unknown")
        echo "  [$i] $disk ($size)"
        ((i++))
    done

    echo ""
    local selection
    while true; do
        read -r -p "Select disk [1-${#disks[@]}]: " selection
        if [[ "$selection" =~ ^[0-9]+$ ]] && ((selection >= 1 && selection <= ${#disks[@]})); then
            DISK="${disks[$((selection - 1))]}"
            break
        fi
        echo "Invalid selection. Please try again."
    done

    success "Selected disk: $DISK"
}

# ─────────────────────────────────────────────────────────────────────────────
# BACKEND AND CONFIGURATION FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

choose_backend() {
    if [[ -n "$BACKEND" ]]; then
        return 0
    fi

    # Without a terminal (systemd service, piped stdin), default to 'dir'
    # which needs no disk and always works. Interactive users get the menu.
    if [[ ! -t 0 ]]; then
        BACKEND="dir"
        info "No terminal detected — defaulting to 'dir' backend (safe fallback)"
        info "Run start.sh manually for ZFS/BTRFS with disk selection"
        return 0
    fi

    info "Select storage backend:"
    echo "  [1] ZFS (recommended: snapshots, compression, copy-on-write) [default]"
    echo "  [2] BTRFS (subvolume-based, simpler)"
    echo "  [3] dir (no dedicated disk needed — uses a directory on existing filesystem)"
    echo ""

    local selection
    while true; do
        read -r -p "Choose backend [1-3, default=1]: " selection
        case "${selection:-1}" in
            1)
                BACKEND="zfs"
                success "Backend selected: ZFS"
                return 0
                ;;
            2)
                BACKEND="btrfs"
                success "Backend selected: BTRFS"
                return 0
                ;;
            3)
                BACKEND="dir"
                success "Backend selected: dir (directory-based)"
                return 0
                ;;
            *)
                echo "Invalid selection. Please try again."
                ;;
        esac
    done
}

# ─────────────────────────────────────────────────────────────────────────────
# ENCRYPTION FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

setup_luks() {
    # In --yes mode, skip LUKS (no default password — interactive only)
    if [[ "$CONFIRM_YES" == "true" ]]; then
        LUKS_ENABLED=false
        info "Skipping LUKS encryption (--yes mode, use interactive mode for encryption)"
        return 0
    fi
    if ! prompt_yes_no "Encrypt the storage disk with LUKS?"; then
        LUKS_ENABLED=false
        info "Proceeding without LUKS encryption"
        return 0
    fi

    LUKS_ENABLED=true
    info "LUKS encryption enabled"

    # Verify cryptsetup is available
    if ! command -v cryptsetup &>/dev/null; then
        die "cryptsetup not found. Install it with: apt install cryptsetup"
    fi

    local attempts=0
    while [[ $attempts -lt 3 ]]; do
        read -rs -p "Enter LUKS password (will not echo): " LUKS_PASSWORD
        echo ""

        if [[ -z "$LUKS_PASSWORD" ]]; then
            warn "Password cannot be empty. Try again."
            attempts=$((attempts + 1))
            continue
        fi

        local password_confirm
        read -rs -p "Confirm password: " password_confirm
        echo ""

        if [[ "$LUKS_PASSWORD" != "$password_confirm" ]]; then
            warn "Passwords do not match. Try again."
            attempts=$((attempts + 1))
            continue
        fi

        success "Password accepted"
        return 0
    done

    die "Failed to set LUKS password after 3 attempts"
}

# ─────────────────────────────────────────────────────────────────────────────
# POOL SETUP FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

setup_zfs_pool() {
    info "Setting up ZFS pool: $POOL_NAME"

    # Verify zfsutils is installed
    if ! command -v zpool &>/dev/null; then
        case "$HOST_DISTRO" in
            arch)   die "zfsutils not found. Install from archzfs repo or use BTRFS backend." ;;
            *)      die "zfsutils-linux not found. Install it with: apt install zfsutils-linux" ;;
        esac
    fi

    # Load ZFS kernel module (not auto-loaded in live ISO)
    if ! lsmod | grep -q '^zfs '; then
        info "Loading ZFS kernel module..."
        modprobe zfs || die "ZFS kernel module not available. Check that zfs-dkms is installed and built for this kernel."
    fi

    local pool_device="$DISK"

    if [[ "$LUKS_ENABLED" == "true" ]]; then
        info "Formatting and encrypting $DISK with LUKS..."
        printf '%s' "$LUKS_PASSWORD" | cryptsetup luksFormat --batch-mode --key-file - "$DISK" || \
            die "Failed to create LUKS volume on $DISK"

        info "Opening LUKS volume..."
        printf '%s' "$LUKS_PASSWORD" | cryptsetup luksOpen --key-file - "$DISK" "$LUKS_NAME" || \
            die "Failed to open LUKS volume"

        pool_device="/dev/mapper/$LUKS_NAME"
        success "LUKS volume open at $pool_device"
    fi

    # Create ZFS pool
    info "Creating ZFS pool on $pool_device..."

    zpool create -f -m none "$POOL_NAME" "$pool_device" || \
        die "Failed to create ZFS pool on $pool_device"

    success "ZFS pool created: $POOL_NAME"

    # Enable compression, deduplication, and other optimizations
    info "Configuring ZFS pool..."
    zfs set compression=lz4 "$POOL_NAME" || warn "Failed to set ZFS compression (non-fatal)"
    zfs set dedup=on "$POOL_NAME" || warn "Failed to enable ZFS deduplication (non-fatal)"
    zfs set atime=off "$POOL_NAME" || warn "Failed to disable ZFS atime (non-fatal)"

    POOL_MOUNT_POINT="/mnt/${POOL_NAME}"
}

setup_btrfs_pool() {
    info "Setting up BTRFS pool: $POOL_NAME"

    # Verify btrfs-progs is installed
    if ! command -v mkfs.btrfs &>/dev/null; then
        case "$HOST_DISTRO" in
            arch)   die "btrfs-progs not found. Install it with: pacman -S btrfs-progs" ;;
            *)      die "btrfs-progs not found. Install it with: apt install btrfs-progs" ;;
        esac
    fi

    local pool_device="$DISK"

    if [[ "$LUKS_ENABLED" == "true" ]]; then
        info "Formatting and encrypting $DISK with LUKS..."
        printf '%s' "$LUKS_PASSWORD" | cryptsetup luksFormat --batch-mode --key-file - "$DISK" || \
            die "Failed to create LUKS volume on $DISK"

        info "Opening LUKS volume..."
        printf '%s' "$LUKS_PASSWORD" | cryptsetup luksOpen --key-file - "$DISK" "$LUKS_NAME" || \
            die "Failed to open LUKS volume"

        pool_device="/dev/mapper/$LUKS_NAME"
        success "LUKS volume open at $pool_device"
    fi

    # Create BTRFS filesystem
    info "Creating BTRFS filesystem on $pool_device..."

    mkfs.btrfs -f -L "$POOL_NAME" "$pool_device" || \
        die "Failed to create BTRFS filesystem on $pool_device"

    success "BTRFS filesystem created: $POOL_NAME"

    POOL_MOUNT_POINT="/mnt/${POOL_NAME}"
}

setup_dir_pool() {
    info "Setting up directory-based pool: $POOL_NAME"
    POOL_MOUNT_POINT="/var/lib/incus/storage-pools/${POOL_NAME}"
    success "Directory pool — no disk formatting needed"
}

initialize_incus() {
    info "Initializing Incus daemon..."

    # Pre-flight: ensure daemon is running
    if ! systemctl is-active incus.service >/dev/null 2>&1; then
        info "Starting Incus daemon..."
        systemctl start incus.service || true
        sleep 2
    fi

    # Pre-flight: wait for daemon readiness (up to 15s)
    local wait_count=0
    while [ $wait_count -lt 15 ]; do
        if incus info >/dev/null 2>&1; then
            break
        fi
        wait_count=$((wait_count + 1))
        sleep 1
    done
    if [ $wait_count -eq 15 ]; then
        warn "Incus daemon not responding after 15 seconds"
        return 1
    fi

    # Already initialized?
    if incus profile show default 2>/dev/null | grep -q "eth0"; then
        info "Incus already initialized, skipping"
        return 0
    fi

    # Load bridge kernel modules (needed for incusbr0)
    modprobe bridge 2>/dev/null || true
    modprobe br_netfilter 2>/dev/null || true

    # Try preseed (creates incusbr0 + default storage pool + default profile)
    # Use || true to prevent set -e from killing the script before fallback
    local preseed_err preseed_rc=0
    preseed_err=$(cat <<PRESEED | incus admin init --preseed 2>&1
config: {}
networks:
  - config:
      ipv4.address: auto
      ipv6.address: none
    description: Default network
    name: incusbr0
    type: bridge
storage_pools:
  - config: {}
    description: Default storage pool
    driver: dir
    name: default
profiles:
  - config: {}
    description: Default profile
    devices:
      eth0:
        name: eth0
        network: incusbr0
        type: nic
      root:
        path: /
        pool: default
        type: disk
    name: default
PRESEED
) || preseed_rc=$?
    if [ $preseed_rc -eq 0 ]; then
        success "Incus daemon initialized with default network and profile"
        return 0
    fi

    # Fallback: minimal init (creates storage pool but no bridge)
    if incus admin init --minimal 2>/dev/null; then
        success "Incus initialized (minimal — no bridge, run 'incus network create incusbr0' to add one)"
        return 0
    fi

    # Both methods failed — fatal error, stop here
    err "Incus initialization failed (preseed and minimal init both failed)"
    err "Preseed error: ${preseed_err:-unknown}"
    err "Recovery: run 'aa-teardown && systemctl restart incus && incus admin init --minimal'"
    return 1
}

# ─────────────────────────────────────────────────────────────────────────────
# EXISTING POOL DETECTION
# ─────────────────────────────────────────────────────────────────────────────

detect_existing_pool() {
    # Check a single disk for anklume pool signatures.
    # Returns: "persist", "luks", "zfs", "btrfs", or fails (return 1).

    # Check pool.conf on persist partition first (fastest, most reliable)
    if [[ -f /mnt/anklume-persist/pool.conf ]]; then
        # shellcheck source=/dev/null
        source /mnt/anklume-persist/pool.conf 2>/dev/null || true
        if [[ -n "${POOL_BACKEND:-}" ]]; then
            echo "persist"
            return 0
        fi
    fi

    local disk="${1:-}"
    [[ -n "$disk" && -b "$disk" ]] || return 1

    # Check what's on the disk
    local disk_type
    disk_type=$(blkid -o value -s TYPE "$disk" 2>/dev/null || true)

    case "$disk_type" in
        crypto_LUKS)
            echo "luks"
            return 0
            ;;
        zfs_member)
            echo "zfs"
            return 0
            ;;
        btrfs)
            echo "btrfs"
            return 0
            ;;
        "")
            # No filesystem signature — also check ZFS (may not show in blkid)
            if command -v zpool &>/dev/null && zpool import 2>/dev/null | grep -q "pool:"; then
                echo "zfs"
                return 0
            fi
            ;;
    esac

    return 1
}

scan_all_disks_for_pool() {
    # Scan ALL candidate data disks for existing anklume pools.
    # Outputs "type:disk" on success (e.g., "zfs:/dev/vda", "persist:").
    # This runs BEFORE choose_backend and select_disk.

    # Pre-load filesystem modules for detection (not auto-loaded on live ISO)
    if command -v zpool &>/dev/null && ! lsmod | grep -q '^zfs '; then
        modprobe zfs 2>/dev/null || true
    fi

    # 1. Check persist partition first (no disk scan needed)
    if [[ -f /mnt/anklume-persist/pool.conf ]]; then
        local result
        result=$(detect_existing_pool "") || true
        if [[ "$result" == "persist" ]]; then
            echo "persist:"
            return 0
        fi
    fi

    # 2. Scan all candidate disks via lsblk
    local root_src root_dev
    root_src=$(findmnt -no SOURCE / 2>/dev/null | head -1 || echo "")
    root_dev=$(lsblk -no PKNAME "$root_src" 2>/dev/null | head -1 || echo "")

    while IFS= read -r line; do
        local name dev size_raw size_gb
        name=$(echo "$line" | awk '{print $1}')
        dev="/dev/${name}"
        size_raw=$(echo "$line" | awk '{print $2}')

        # Skip root device
        if [[ -n "$root_dev" ]] && [[ "$dev" == "/dev/$root_dev"* ]]; then
            continue
        fi

        # Skip small devices
        size_gb=$(echo "$size_raw" | sed 's/[^0-9.].*//' | cut -d. -f1)
        if [[ -z "$size_gb" ]] || [[ "$size_gb" -lt 100 ]]; then
            continue
        fi

        # Check this disk for existing pool
        local detected
        detected=$(detect_existing_pool "$dev") || true
        if [[ -n "$detected" ]]; then
            echo "${detected}:${dev}"
            return 0
        fi
    done < <(lsblk -d -o NAME,SIZE -x NAME 2>/dev/null | tail -n +2)

    return 1
}

resume_existing_pool() {
    local detected="$1"

    if [[ "$detected" == "persist" ]]; then
        # pool.conf found — read the saved configuration
        # shellcheck source=/dev/null
        source /mnt/anklume-persist/pool.conf 2>/dev/null
        info "Existing anklume configuration found:"
        echo "  Backend:    ${POOL_BACKEND:-unknown}"
        echo "  Pool:       ${POOL_NAME:-unknown}"
        echo "  Device:     ${POOL_DEVICE:-none}"
        echo "  Encrypted:  ${LUKS_ENABLED:-false}"
        echo ""

        if [[ "$CONFIRM_YES" != "true" ]]; then
            if ! prompt_yes_no "Resume this configuration?"; then
                return 1
            fi
        fi

        # Re-assign globals from pool.conf
        BACKEND="${POOL_BACKEND}"
        POOL_NAME="${POOL_NAME:-anklume}"
        DISK="${POOL_DEVICE:-}"
        LUKS_ENABLED="${LUKS_ENABLED:-false}"
        POOL_MOUNT_POINT="${POOL_MOUNT_POINT:-}"

        # Re-mount and import as needed
        case "$BACKEND" in
            zfs)
                if ! lsmod | grep -q '^zfs '; then
                    modprobe zfs || die "ZFS kernel module not available"
                fi
                if ! zpool list "$POOL_NAME" &>/dev/null; then
                    if [[ "$LUKS_ENABLED" == "true" && -n "$DISK" ]]; then
                        info "Opening LUKS volume..."
                        cryptsetup luksOpen "$DISK" "$LUKS_NAME" 2>/dev/null || \
                            cryptsetup luksOpen "$DISK" "$LUKS_NAME" || \
                            die "Failed to open LUKS volume (wrong password?)"
                    fi
                    info "Importing ZFS pool..."
                    zpool import "$POOL_NAME" 2>/dev/null || zpool import -f "$POOL_NAME" || \
                        die "Failed to import ZFS pool"
                fi
                success "ZFS pool '$POOL_NAME' imported"
                ;;
            btrfs)
                if [[ "$LUKS_ENABLED" == "true" && -n "$DISK" ]]; then
                    if [[ ! -e "/dev/mapper/$LUKS_NAME" ]]; then
                        info "Opening LUKS volume..."
                        cryptsetup luksOpen "$DISK" "$LUKS_NAME" || \
                            die "Failed to open LUKS volume"
                    fi
                fi
                local mount_dev="${DISK}"
                [[ "$LUKS_ENABLED" == "true" ]] && mount_dev="/dev/mapper/$LUKS_NAME"
                if [[ -n "$POOL_MOUNT_POINT" ]] && ! mountpoint -q "$POOL_MOUNT_POINT" 2>/dev/null; then
                    mkdir -p "$POOL_MOUNT_POINT"
                    mount "$mount_dev" "$POOL_MOUNT_POINT" || die "Failed to mount BTRFS"
                fi
                success "BTRFS mounted at $POOL_MOUNT_POINT"
                ;;
            dir)
                success "Directory backend — no mount needed"
                ;;
        esac

        # Ensure Incus pool exists
        if ! incus storage show "$POOL_NAME" &>/dev/null; then
            info "Re-creating Incus storage pool reference..."
            configure_incus_storage
        fi

        return 0
    fi

    # Detected via blkid — disk has an existing filesystem
    info "Existing anklume pool detected on $DISK:"
    case "$detected" in
        luks)  echo "  Type: LUKS-encrypted volume" ;;
        zfs)   echo "  Type: ZFS pool" ;;
        btrfs) echo "  Type: BTRFS filesystem" ;;
    esac
    echo ""

    if [[ "$CONFIRM_YES" != "true" ]]; then
        if ! prompt_yes_no "Resume this existing pool?"; then
            warn "User chose not to resume. Proceeding to fresh setup."
            return 1
        fi
    fi

    # Resume based on detected type
    case "$detected" in
        zfs)
            BACKEND="zfs"
            if ! lsmod | grep -q '^zfs '; then
                modprobe zfs || die "ZFS kernel module not available"
            fi
            # Import the pool
            if ! zpool list "$POOL_NAME" &>/dev/null; then
                info "Importing ZFS pool..."
                zpool import "$POOL_NAME" 2>/dev/null || zpool import -f "$POOL_NAME" || \
                    die "Failed to import ZFS pool '$POOL_NAME'"
            fi
            POOL_MOUNT_POINT="/mnt/${POOL_NAME}"
            success "ZFS pool '$POOL_NAME' imported"
            ;;
        btrfs)
            BACKEND="btrfs"
            POOL_MOUNT_POINT="/mnt/${POOL_NAME}"
            if ! mountpoint -q "$POOL_MOUNT_POINT" 2>/dev/null; then
                mkdir -p "$POOL_MOUNT_POINT"
                mount "$DISK" "$POOL_MOUNT_POINT" || die "Failed to mount BTRFS"
            fi
            success "BTRFS mounted at $POOL_MOUNT_POINT"
            ;;
        luks)
            BACKEND="luks"
            LUKS_ENABLED=true
            if [[ ! -e "/dev/mapper/$LUKS_NAME" ]]; then
                info "Opening LUKS volume..."
                cryptsetup luksOpen "$DISK" "$LUKS_NAME" || \
                    die "Failed to open LUKS volume (wrong password?)"
            fi
            local inner_dev="/dev/mapper/$LUKS_NAME"
            # Detect what's inside LUKS
            local inner_type
            inner_type=$(blkid -o value -s TYPE "$inner_dev" 2>/dev/null || true)
            case "$inner_type" in
                zfs_member)
                    BACKEND="zfs"
                    if ! lsmod | grep -q '^zfs '; then
                        modprobe zfs || die "ZFS kernel module not available"
                    fi
                    if ! zpool list "$POOL_NAME" &>/dev/null; then
                        zpool import "$POOL_NAME" 2>/dev/null || zpool import -f "$POOL_NAME" || \
                            die "Failed to import ZFS pool"
                    fi
                    POOL_MOUNT_POINT="/mnt/${POOL_NAME}"
                    success "LUKS+ZFS pool '$POOL_NAME' resumed"
                    ;;
                btrfs)
                    BACKEND="btrfs"
                    POOL_MOUNT_POINT="/mnt/${POOL_NAME}"
                    if ! mountpoint -q "$POOL_MOUNT_POINT" 2>/dev/null; then
                        mkdir -p "$POOL_MOUNT_POINT"
                        mount "$inner_dev" "$POOL_MOUNT_POINT" || die "Failed to mount BTRFS inside LUKS"
                    fi
                    success "LUKS+BTRFS mounted at $POOL_MOUNT_POINT"
                    ;;
                *)
                    warn "Unknown filesystem inside LUKS: ${inner_type:-empty}"
                    return 1
                    ;;
            esac
            ;;
    esac

    # Ensure Incus storage pool exists
    if ! incus storage show "$POOL_NAME" &>/dev/null; then
        info "Re-creating Incus storage pool reference..."
        configure_incus_storage
    fi

    # Write/update pool.conf for future boots
    local pool_conf_path="$POOL_CONF_FILE"
    if grep -q 'boot=anklume' /proc/cmdline 2>/dev/null; then
        pool_conf_path="/mnt/anklume-persist/pool.conf"
        mkdir -p /mnt/anklume-persist 2>/dev/null || true
    fi
    write_pool_conf "$pool_conf_path"

    return 0
}

# ─────────────────────────────────────────────────────────────────────────────
# INCUS STORAGE CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

configure_incus_storage() {
    info "Configuring Incus storage pool..."

    # Verify Incus is running
    if ! incus list >/dev/null 2>&1; then
        die "Incus daemon is not accessible. Check 'incus list' manually."
    fi

    # Check if pool already exists (idempotent)
    if incus storage show "$POOL_NAME" &>/dev/null; then
        info "Incus storage pool '$POOL_NAME' already exists, skipping creation"
        return 0
    fi

    # Create Incus storage pool
    local incus_source="" create_rc=0

    case "$BACKEND" in
        zfs)
            incus_source="$POOL_NAME"
            info "Creating Incus ZFS storage pool..."
            incus storage create "$POOL_NAME" zfs source="$incus_source" 2>&1 || create_rc=$?
            if [[ $create_rc -ne 0 ]]; then
                die "Failed to create Incus ZFS storage pool (exit code $create_rc)"
            fi
            ;;
        btrfs)
            # Mount BTRFS filesystem first
            if [[ ! -d "$POOL_MOUNT_POINT" ]]; then
                mkdir -p "$POOL_MOUNT_POINT" || die "Failed to create mount point"
            fi

            if ! mountpoint -q "$POOL_MOUNT_POINT"; then
                mount "$DISK" "$POOL_MOUNT_POINT" || die "Failed to mount BTRFS filesystem"
                success "Mounted BTRFS at $POOL_MOUNT_POINT"
            fi

            incus_source="$POOL_MOUNT_POINT"
            info "Creating Incus BTRFS storage pool..."
            incus storage create "$POOL_NAME" btrfs source="$incus_source" 2>&1 || create_rc=$?
            if [[ $create_rc -ne 0 ]]; then
                die "Failed to create Incus BTRFS storage pool (exit code $create_rc)"
            fi
            ;;
        dir)
            info "Creating Incus directory storage pool..."
            incus storage create "$POOL_NAME" dir 2>&1 || create_rc=$?
            if [[ $create_rc -ne 0 ]]; then
                die "Failed to create Incus directory storage pool (exit code $create_rc)"
            fi
            ;;
        *)
            die "Unknown backend: $BACKEND"
            ;;
    esac

    success "Incus storage pool configured: $POOL_NAME"
}

# ─────────────────────────────────────────────────────────────────────────────
# FRAMEWORK AND BOOTSTRAP FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

write_pool_conf() {
    local output_file="$1"

    # Write pool configuration (internal — no user-facing output needed)

    cat > "$output_file" <<EOF
# anklume pool configuration
# Generated by start.sh on $(date -u +%Y-%m-%dT%H:%M:%SZ)

POOL_NAME=$POOL_NAME
POOL_BACKEND=$BACKEND
POOL_DEVICE=$DISK
POOL_MOUNT_POINT=$POOL_MOUNT_POINT
LUKS_ENABLED=$LUKS_ENABLED
LUKS_NAME=$LUKS_NAME
BOOTSTRAP_IMAGE=$BOOTSTRAP_IMAGE

# Additional metadata
GENERATED_BY=start.sh
GENERATED_DATE=$(date -u +%Y-%m-%d)
HOSTNAME=$(hostname)
EOF

    success "Pool configuration saved"
}

copy_framework() {
    # Verify source directory exists
    if [[ ! -d "$ANKLUME_REPO" ]]; then
        die "anklume repository not found at: $ANKLUME_REPO"
    fi

    # Determine destination based on backend
    local dest_dir=""

    case "$BACKEND" in
        zfs)
            # For ZFS, create a dataset with a mountpoint
            dest_dir="/${POOL_NAME}/anklume"
            zfs create -o mountpoint="$dest_dir" "${POOL_NAME}/anklume" 2>/dev/null || {
                # Dataset may already exist; ensure mountpoint exists
                mkdir -p "$dest_dir" 2>/dev/null || true
            }
            ;;
        btrfs)
            dest_dir="$POOL_MOUNT_POINT/anklume"
            if [[ ! -d "$dest_dir" ]]; then
                mkdir -p "$dest_dir" || die "Failed to create framework directory"
            fi
            ;;
        dir)
            # dir backend: framework already available at /opt/anklume/ (live ISO)
            # or at the project root (installed host). No separate copy needed.
            return 0
            ;;
    esac

    info "Saving framework to persistent storage..."
    # Use rsync or tar to preserve permissions
    if command -v rsync &>/dev/null; then
        rsync -a --exclude='.git' --exclude='.venv' "$ANKLUME_REPO/" "$dest_dir/" || \
            die "Failed to copy framework with rsync"
    else
        mkdir -p "$dest_dir"
        tar -C "$ANKLUME_REPO" -cf - --exclude='.git' --exclude='.venv' . | \
            tar -C "$dest_dir" -xf - || \
            die "Failed to copy framework with tar"
    fi

    success "Framework copied to $dest_dir"
}

bootstrap_incus() {
    # Verify Incus storage pool is available
    if ! incus storage show "$POOL_NAME" &>/dev/null; then
        die "Incus storage pool $POOL_NAME not found"
    fi

    local container_name="anklume-bootstrap"

    # Check if container already exists
    if incus list | grep -q "$container_name"; then
        warn "Container $container_name already exists, skipping bootstrap"
        return 0
    fi

    info "Launching bootstrap container..."
    if ! incus launch "$BOOTSTRAP_IMAGE" "$container_name" \
        -s "$POOL_NAME" \
        -c limits.memory=2GiB \
        -c limits.cpu=2; then
        # Show container start log for diagnostics
        incus info "$container_name" --show-log 2>&1 | tail -20 || true
        die "Failed to launch bootstrap container"
    fi

    # Wait for container to be ready
    local wait_count=0
    while [[ $wait_count -lt 30 ]]; do
        if incus exec "$container_name" -- /bin/true 2>/dev/null; then
            break
        fi
        wait_count=$((wait_count + 1))
        sleep 1
    done

    if [[ $wait_count -eq 30 ]]; then
        warn "Container did not become ready within 30 seconds"
    fi

    # Initialize basic container configuration
    incus exec "$container_name" -- apt update -y >/dev/null 2>&1 || true
    incus exec "$container_name" -- apt install -y curl git >/dev/null 2>&1 || true

    success "Bootstrap container ready"
}

# ─────────────────────────────────────────────────────────────────────────────
# MAIN FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

main() {
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║  anklume Setup (v${SCRIPT_VERSION})                           ║"
    echo "║  Storage, Framework & Bootstrap                          ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo ""

    # Check root privileges
    if [[ $EUID -ne 0 ]]; then
        die "This script must be run as root (use sudo)"
    fi

    # Process arguments (before lock, so --yes can handle conflicts)
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --yes)
                CONFIRM_YES=true
                shift
                ;;
            --disk)
                [[ $# -ge 2 ]] || die "--disk requires a device path"
                DISK="$2"
                shift 2
                ;;
            --backend)
                [[ $# -ge 2 ]] || die "--backend requires 'zfs' or 'btrfs'"
                BACKEND="$2"
                shift 2
                ;;
            --list)
                list_disks
                exit 0
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                die "Unknown option: $1. Run with --help for usage."
                ;;
        esac
    done

    # Prevent concurrent runs — kill any existing instance
    if [[ -f "$LOCK_FILE" ]]; then
        local lock_pid
        lock_pid=$(<"$LOCK_FILE")
        if kill -0 "$lock_pid" 2>/dev/null; then
            info "Another start.sh is running (PID $lock_pid), stopping it..."
            # Stop the systemd service (sends SIGTERM)
            systemctl stop anklume-start.service 2>/dev/null || true
            # Also kill directly in case it wasn't started by the service
            kill "$lock_pid" 2>/dev/null || true
            # Wait up to 5 seconds for the process to die
            local w=0
            while kill -0 "$lock_pid" 2>/dev/null && [[ $w -lt 5 ]]; do
                sleep 1
                w=$((w + 1))
            done
            # Force kill if still alive
            if kill -0 "$lock_pid" 2>/dev/null; then
                kill -9 "$lock_pid" 2>/dev/null || true
                sleep 1
            fi
        fi
        rm -f "$LOCK_FILE"
    fi
    echo $$ > "$LOCK_FILE"
    LOCK_OWNED=true
    trap cleanup_lock EXIT

    # Initialize Incus daemon if not already done
    initialize_incus

    # Scan ALL candidate disks for existing anklume pools BEFORE
    # asking about backend or disk selection. This prevents the
    # catastrophic scenario of offering to reformat a production disk.
    local scan_result=""
    scan_result=$(scan_all_disks_for_pool 2>/dev/null) || true
    if [[ -n "$scan_result" ]]; then
        local detected="${scan_result%%:*}"
        local detected_disk="${scan_result#*:}"
        # Set DISK from scan (was lost in subshell)
        if [[ -n "$detected_disk" ]]; then
            DISK="$detected_disk"
        fi
        if resume_existing_pool "$detected"; then
            # Pool resumed — skip to framework copy and bootstrap
            copy_framework
            bootstrap_incus

            echo ""
            echo "╔════════════════════════════════════════════════════════════╗"
            echo "║  anklume Setup Complete (resumed)                        ║"
            echo "╠════════════════════════════════════════════════════════════╣"
            echo "║  Storage: $BACKEND pool '$POOL_NAME' ready"
            echo "║  Next: run 'anklume guide' to get started                 ║"
            echo "╚════════════════════════════════════════════════════════════╝"
            echo ""
            return 0
        fi
    fi

    choose_backend

    # Disk selection (not needed for dir backend)
    if [[ "$BACKEND" != "dir" ]]; then
        if [[ -z "$DISK" ]]; then
            select_disk
        fi

        if [[ ! -b "$DISK" ]]; then
            die "Invalid disk device: $DISK (not a block device)"
        fi
    fi

    # Safety warnings
    if [[ "$BACKEND" != "dir" ]]; then
        echo ""
        echo "╔════════════════════════════════════════════════════════════╗"
        echo "║  WARNING: DESTRUCTIVE OPERATION                          ║"
        echo "╚════════════════════════════════════════════════════════════╝"
        echo ""
        echo "This script will:"
        echo "  1. DESTROY all data on $DISK"
        echo "  2. Create a $BACKEND pool: $POOL_NAME"
        if [[ -z "$LUKS_PASSWORD" ]]; then
            echo "  3. Optionally encrypt with LUKS"
        else
            echo "  3. Encrypt with LUKS"
        fi
        echo "  4. Configure Incus storage"
        echo "  5. Copy anklume framework"
        echo "  6. Bootstrap initial container"
        echo ""
        echo "Target disk: $DISK"
        echo "Backend: $BACKEND"
        echo "Repository: $ANKLUME_REPO"
        echo ""

        # No extra confirmation needed — the recap above is the last chance
        # to review before destructive operations begin. The user already
        # chose --backend and --disk explicitly.
        echo "Starting setup in 3 seconds... (Ctrl+C to abort)"
        sleep 3
    else
        info "Using directory backend (no disk formatting needed)"
        info "Backend: $BACKEND"
        info "Repository: $ANKLUME_REPO"
    fi

    # Execute setup
    if [[ "$BACKEND" != "dir" ]]; then
        setup_luks
    fi

    case "$BACKEND" in
        zfs)
            setup_zfs_pool
            ;;
        btrfs)
            setup_btrfs_pool
            ;;
        dir)
            setup_dir_pool
            ;;
    esac

    configure_incus_storage

    # Write pool.conf — on live OS use persist mount, otherwise local
    local pool_conf_path="$POOL_CONF_FILE"
    if grep -q 'boot=anklume' /proc/cmdline 2>/dev/null; then
        pool_conf_path="/mnt/anklume-persist/pool.conf"
        mkdir -p /mnt/anklume-persist 2>/dev/null || true
    fi
    write_pool_conf "$pool_conf_path"
    copy_framework
    bootstrap_incus

    echo ""
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║  anklume First-Boot Complete                              ║"
    echo "╠════════════════════════════════════════════════════════════╣"
    echo "║  Storage: $BACKEND pool '$POOL_NAME' ready"
    if [[ "$LUKS_ENABLED" == "true" ]]; then
    echo "║  Encryption: LUKS enabled"
    fi
    echo "║  Container: anklume-bootstrap running"
    echo "╠════════════════════════════════════════════════════════════╣"
    echo "║  Next: run 'anklume guide' to get started                 ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo ""
}

# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

main "$@"
