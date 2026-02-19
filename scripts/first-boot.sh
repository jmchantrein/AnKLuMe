#!/usr/bin/env bash
# first-boot.sh: AnKLuMe initial host setup for Incus storage and framework bootstrap
#
# This script initializes Incus storage pools (ZFS or BTRFS), copies the AnKLuMe
# framework into the Incus dataset, bootstraps the initial Incus container,
# and produces a pool configuration file for Ansible.
#
# Usage: first-boot.sh [--yes] [--disk DEVICE] [--backend zfs|btrfs]
#
# Requires: root, Incus daemon running, lsblk, cryptsetup
#
# IMPORTANT: This is a destructive operation. It will format the selected disk.
# Always verify the disk selection with --list before committing.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Source shared library
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
declare -r INCUS_DIR="/var/lib/incus"
declare -r LUKS_NAME="anklume-crypt"
declare -r POOL_CONF_FILE="pool.conf"

# Color codes for output
declare -r RED='\033[0;31m'
declare -r GREEN='\033[0;32m'
declare -r YELLOW='\033[1;33m'
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
Usage: first-boot.sh [--yes] [--disk DEVICE] [--backend zfs|btrfs] [--list] [-h|--help]

Initialize Incus storage pools and bootstrap the AnKLuMe framework.

Options:
  --yes                 Skip all confirmations (dangerous, use with care)
  --disk DEVICE         Specify target disk (e.g., /dev/sdb, /dev/vda)
  --backend zfs|btrfs   Specify storage backend (prompt if omitted)
  --list                List available disks and exit
  -h, --help            Show this help message

Examples:
  first-boot.sh --list
  first-boot.sh --disk /dev/sdb --backend zfs
  first-boot.sh --yes --disk /dev/sdb --backend btrfs

IMPORTANT: This script will DESTROY DATA on the selected disk.
Always run with --list first to verify disk identification.

USAGE
}

list_disks() {
    info "Available disks (excluding system disk):"
    echo ""

    # Get root device
    local root_dev
    root_dev=$(lsblk -no PKNAME "$(stat -c %V /)" 2>/dev/null | head -1 || echo "")

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
    info "Detecting available data disks..."

    local root_dev
    root_dev=$(lsblk -no PKNAME "$(stat -c %V /)" 2>/dev/null | head -1 || echo "")

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
    mapfile -t disks < <(detect_data_disks)

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

    info "Select storage backend:"
    echo "  [1] ZFS (recommended: snapshots, compression, copy-on-write)"
    echo "  [2] BTRFS (subvolume-based, simpler, no snapshots)"
    echo ""

    local selection
    while true; do
        read -r -p "Choose backend [1-2]: " selection
        case "$selection" in
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
            ((attempts++))
            continue
        fi

        local password_confirm
        read -rs -p "Confirm password: " password_confirm
        echo ""

        if [[ "$LUKS_PASSWORD" != "$password_confirm" ]]; then
            warn "Passwords do not match. Try again."
            ((attempts++))
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

    local pool_device="$DISK"

    if [[ "$LUKS_ENABLED" == "true" ]]; then
        info "Formatting and encrypting $DISK with LUKS..."
        cryptsetup luksFormat --batch-mode "$DISK" <<<"$LUKS_PASSWORD" || \
            die "Failed to create LUKS volume on $DISK"

        info "Opening LUKS volume..."
        cryptsetup luksOpen "$DISK" "$LUKS_NAME" <<<"$LUKS_PASSWORD" || \
            die "Failed to open LUKS volume"

        pool_device="/dev/mapper/$LUKS_NAME"
        success "LUKS volume open at $pool_device"
    fi

    # Create ZFS pool
    info "Creating ZFS pool..."
    if ! prompt_yes_no "Create ZFS pool $POOL_NAME on $pool_device?"; then
        die "User cancelled pool creation"
    fi

    zpool create -f -m none "$POOL_NAME" "$pool_device" || \
        die "Failed to create ZFS pool on $pool_device"

    success "ZFS pool created: $POOL_NAME"

    # Enable compression and other optimizations
    info "Configuring ZFS pool..."
    zfs set compression=lz4 "$POOL_NAME"
    zfs set atime=off "$POOL_NAME"

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
        cryptsetup luksFormat --batch-mode "$DISK" <<<"$LUKS_PASSWORD" || \
            die "Failed to create LUKS volume on $DISK"

        info "Opening LUKS volume..."
        cryptsetup luksOpen "$DISK" "$LUKS_NAME" <<<"$LUKS_PASSWORD" || \
            die "Failed to open LUKS volume"

        pool_device="/dev/mapper/$LUKS_NAME"
        success "LUKS volume open at $pool_device"
    fi

    # Create BTRFS filesystem
    info "Creating BTRFS filesystem..."
    if ! prompt_yes_no "Create BTRFS pool $POOL_NAME on $pool_device?"; then
        die "User cancelled pool creation"
    fi

    mkfs.btrfs -f -L "$POOL_NAME" "$pool_device" || \
        die "Failed to create BTRFS filesystem on $pool_device"

    success "BTRFS filesystem created: $POOL_NAME"

    POOL_MOUNT_POINT="/mnt/${POOL_NAME}"
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

    # Create Incus storage pool
    local incus_source=""

    case "$BACKEND" in
        zfs)
            incus_source="$POOL_NAME"
            info "Creating Incus ZFS storage pool..."
            if ! incus storage create "$POOL_NAME" zfs source="$incus_source" || true; then
                warn "Could not create pool (may already exist)"
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
            if ! incus storage create "$POOL_NAME" btrfs source="$incus_source" || true; then
                warn "Could not create pool (may already exist)"
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

    info "Writing pool configuration to: $output_file"

    cat > "$output_file" <<EOF
# AnKLuMe pool configuration
# Generated by first-boot.sh on $(date -u +%Y-%m-%dT%H:%M:%SZ)

POOL_NAME=$POOL_NAME
POOL_BACKEND=$BACKEND
POOL_DEVICE=$DISK
POOL_MOUNT_POINT=$POOL_MOUNT_POINT
LUKS_ENABLED=$LUKS_ENABLED
LUKS_NAME=$LUKS_NAME
BOOTSTRAP_IMAGE=$BOOTSTRAP_IMAGE

# Additional metadata
GENERATED_BY=first-boot.sh
GENERATED_DATE=$(date -u +%Y-%m-%d)
HOSTNAME=$(hostname)
EOF

    success "Pool configuration written"
    cat "$output_file"
}

copy_framework() {
    info "Preparing to copy AnKLuMe framework..."

    # Verify source directory exists
    if [[ ! -d "$ANKLUME_REPO" ]]; then
        die "AnKLuMe repository not found at: $ANKLUME_REPO"
    fi

    # Determine destination based on backend
    local dest_dir=""

    case "$BACKEND" in
        zfs)
            # For ZFS, we'll use a dataset
            dest_dir="/mnt/${POOL_NAME}/anklume"
            info "ZFS destination: $dest_dir (via dataset mount)"
            # Note: actual dataset mounting happens during bootstrap
            ;;
        btrfs)
            dest_dir="$POOL_MOUNT_POINT/anklume"
            if [[ ! -d "$dest_dir" ]]; then
                mkdir -p "$dest_dir" || die "Failed to create framework directory"
            fi
            ;;
    esac

    if ! prompt_yes_no "Copy framework from $ANKLUME_REPO to $dest_dir?"; then
        info "Skipping framework copy"
        return 0
    fi

    info "Copying framework files..."
    # Use rsync or tar to preserve permissions
    if command -v rsync &>/dev/null; then
        rsync -av --exclude='.git' --exclude='.venv' "$ANKLUME_REPO/" "$dest_dir/" || \
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
    info "Bootstrapping initial Incus container..."

    # Verify Incus storage pool is available
    if ! incus storage list | grep -q "$POOL_NAME"; then
        die "Incus storage pool $POOL_NAME not found"
    fi

    local container_name="anklume-bootstrap"

    # Check if container already exists
    if incus list | grep -q "$container_name"; then
        warn "Container $container_name already exists, skipping bootstrap"
        return 0
    fi

    if ! prompt_yes_no "Launch bootstrap container ($container_name)?"; then
        info "Skipping container bootstrap"
        return 0
    fi

    info "Launching container..."
    incus launch "$BOOTSTRAP_IMAGE" "$container_name" \
        -s "$POOL_NAME" \
        -c limits.memory=2GiB \
        -c limits.cpu=2 || \
        die "Failed to launch bootstrap container"

    success "Container launched: $container_name"

    # Wait for container to be ready
    info "Waiting for container to be ready..."
    local wait_count=0
    while [[ $wait_count -lt 30 ]]; do
        if incus exec "$container_name" -- /bin/true 2>/dev/null; then
            success "Container is ready"
            break
        fi
        ((wait_count++))
        sleep 1
    done

    if [[ $wait_count -eq 30 ]]; then
        warn "Container did not become ready within 30 seconds"
    fi

    # Initialize basic container configuration (optional)
    info "Running basic container setup..."
    incus exec "$container_name" -- apt update -y >/dev/null 2>&1 || true
    incus exec "$container_name" -- apt install -y curl git >/dev/null 2>&1 || true

    success "Bootstrap container initialized: $container_name"
}

# ─────────────────────────────────────────────────────────────────────────────
# MAIN FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

main() {
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║  AnKLuMe First-Boot Setup (v${SCRIPT_VERSION})                ║"
    echo "║  Incus Storage & Framework Bootstrap                     ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo ""

    # Check root privileges
    if [[ $EUID -ne 0 ]]; then
        die "This script must be run as root (use sudo)"
    fi

    # Process arguments
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

    # Validation
    if [[ -z "$DISK" ]]; then
        select_disk
    fi

    if [[ ! -b "$DISK" ]]; then
        die "Invalid disk device: $DISK (not a block device)"
    fi

    choose_backend

    # Safety warnings
    echo ""
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║  ⚠️  WARNING: DESTRUCTIVE OPERATION ⚠️                     ║"
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
    echo "  5. Copy AnKLuMe framework"
    echo "  6. Bootstrap initial container"
    echo ""
    echo "Target disk: $DISK"
    echo "Backend: $BACKEND"
    echo "Repository: $ANKLUME_REPO"
    echo ""

    if ! prompt_yes_no "Proceed with setup?"; then
        echo "Cancelled by user"
        exit 0
    fi

    # Execute setup
    setup_luks

    case "$BACKEND" in
        zfs)
            setup_zfs_pool
            ;;
        btrfs)
            setup_btrfs_pool
            ;;
    esac

    configure_incus_storage
    write_pool_conf "$POOL_CONF_FILE"
    copy_framework
    bootstrap_incus

    echo ""
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║  ✓ AnKLuMe First-Boot Complete                            ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo ""
    echo "Next steps:"
    echo "  1. Verify pool configuration: cat $POOL_CONF_FILE"
    echo "  2. Check Incus storage: incus storage show $POOL_NAME"
    echo "  3. Review bootstrap container: incus list"
    echo "  4. Run Ansible infra playbook"
    echo ""
}

# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

main "$@"
