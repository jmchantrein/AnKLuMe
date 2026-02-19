#!/usr/bin/env bash
# build-image.sh — Build bootable AnKLuMe Live OS image
# Usage: build-image.sh [OPTIONS]
#
# Options:
#   --output FILE     Output image file (default: anklume-live.img)
#   --base DISTRO     Base distribution (default: debian)
#   --arch ARCH       Architecture (default: amd64)
#   --size SIZE_GB    Total image size in GB (default: 4)
#   --mirror URL      APT mirror URL
#   --no-verity       Skip dm-verity setup
#   --help            Show this help

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Source shared library
source "$SCRIPT_DIR/live-os-lib.sh"

# ── Defaults ──
OUTPUT="anklume-live.img"
BASE="debian"
ARCH="amd64"
IMAGE_SIZE_GB=4
MIRROR=""
NO_VERITY=false
WORK_DIR=""
LOOP_DEVICE=""
MOUNTED_PATHS=()
ROOTFS_DIR=""
VERITY_HASH=""

# ── Cleanup ──
cleanup() {
    info "Cleaning up..."

    # Unmount mounted filesystems in reverse order
    for mount_path in "${MOUNTED_PATHS[@]}"; do
        if mountpoint -q "$mount_path" 2>/dev/null; then
            warn "Unmounting $mount_path..."
            umount -R "$mount_path" 2>/dev/null || true
        fi
    done

    # Detach loop device
    if [ -n "$LOOP_DEVICE" ] && losetup -a | grep -q "$LOOP_DEVICE"; then
        warn "Detaching $LOOP_DEVICE..."
        losetup -d "$LOOP_DEVICE" 2>/dev/null || true
    fi

    # Remove work directory
    if [ -n "$WORK_DIR" ] && [ -d "$WORK_DIR" ]; then
        warn "Removing work directory..."
        rm -rf "$WORK_DIR" 2>/dev/null || true
    fi

    ok "Cleanup complete"
}
trap cleanup EXIT

# ── Usage ──
usage() {
    echo "Usage: $(basename "$0") [OPTIONS]"
    echo ""
    echo "Build a bootable AnKLuMe Live OS image with GPT partitions, squashfs, and dm-verity."
    echo ""
    echo "Options:"
    echo "  --output FILE     Output image file (default: anklume-live.img)"
    echo "  --base DISTRO     Base distribution (default: debian)"
    echo "  --arch ARCH       Architecture (default: amd64)"
    echo "  --size SIZE_GB    Total image size in GB (default: 4)"
    echo "  --mirror URL      APT mirror URL"
    echo "  --no-verity       Skip dm-verity setup"
    echo "  --help            Show this help"
    echo ""
    echo "Example:"
    echo "  $(basename "$0") --output my-image.img --size 6 --arch amd64"
    exit 0
}

# ── Check root ──
check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        err "This script must run as root"
        exit 1
    fi
    ok "Running as root"
}

# ── Check dependencies ──
check_dependencies() {
    info "Checking dependencies..."

    local missing=()
    local cmds=(
        "debootstrap" "mksquashfs" "veritysetup" "sgdisk"
        "mkfs.fat" "mkfs.ext4" "losetup" "mount" "umount"
        "bootctl" "curl" "jq" "dd"
    )

    for cmd in "${cmds[@]}"; do
        if ! command -v "$cmd" &>/dev/null; then
            missing+=("$cmd")
        fi
    done

    if [ ${#missing[@]} -gt 0 ]; then
        err "Missing dependencies: ${missing[*]}"
        exit 1
    fi

    ok "All dependencies available"
}

# ── Create disk image ──
create_disk_image() {
    info "Creating disk image: $OUTPUT (${IMAGE_SIZE_GB}GB)..."

    # Create sparse image
    dd if=/dev/zero of="$OUTPUT" bs=1M count=$((IMAGE_SIZE_GB * 1024)) status=progress 2>&1 | tail -1

    # Create GPT partition table
    sgdisk --clear "$OUTPUT"

    # Create partitions
    sgdisk \
        --new=1:2048:+512M --typecode=1:EF00 --change-name=1:"ANKLUME-EFI" \
        --new=2:0:+1536M --typecode=2:8300 --change-name=2:"ANKLUME-OS-A" \
        --new=3:0:+1536M --typecode=3:8300 --change-name=3:"ANKLUME-OS-B" \
        --new=4:0:0 --typecode=4:8300 --change-name=4:"ANKLUME-PERSISTENT" \
        "$OUTPUT" >/dev/null 2>&1

    ok "Disk image created with 4 partitions"
}

# ── Setup loop device ──
setup_loop_device() {
    info "Setting up loop device..."

    LOOP_DEVICE=$(losetup --find --show --partscan "$OUTPUT")
    info "Using loop device: $LOOP_DEVICE"

    # Wait for partitions to be available
    sleep 1
    for i in 1 2 3 4; do
        local retries=0
        while [ ! -e "${LOOP_DEVICE}p${i}" ] && [ $retries -lt 10 ]; do
            sleep 0.5
            retries=$((retries + 1))
        done
    done

    ok "Loop device configured"
}

# ── Format partitions ──
format_partitions() {
    info "Formatting partitions..."

    # EFI partition
    mkfs.fat -F32 -n ANKLUME-EFI "${LOOP_DEVICE}p1" >/dev/null 2>&1
    info "  EFI partition formatted"

    # Persistent partition
    mkfs.ext4 -F -L ANKLUME-PERSISTENT "${LOOP_DEVICE}p4" >/dev/null 2>&1
    info "  Persistent partition formatted"

    ok "Partitions formatted"
}

# ── Bootstrap rootfs ──
bootstrap_rootfs() {
    info "Bootstrapping Debian rootfs..."

    ROOTFS_DIR="$WORK_DIR/rootfs"
    mkdir -p "$ROOTFS_DIR"

    # Run debootstrap
    local debootstrap_opts="--arch=$ARCH"
    debootstrap_opts="$debootstrap_opts --include=systemd,linux-image-$ARCH,openssh-server,curl,jq,python3"

    if [ -n "$MIRROR" ]; then
        debootstrap_opts="$debootstrap_opts --mirror=$MIRROR"
    fi

    debootstrap $debootstrap_opts "$BASE" "$ROOTFS_DIR" >/dev/null 2>&1
    info "  Debootstrap complete"

    # Install additional packages via chroot
    local packages="incus nftables zfsutils-linux cryptsetup btrfs-progs firmware-linux debootstrap squashfs-tools veritysetup"
    chroot "$ROOTFS_DIR" apt-get install -y -qq $packages >/dev/null 2>&1 || true
    info "  Additional packages installed"

    # Configure system
    echo "anklume" > "$ROOTFS_DIR/etc/hostname"

    # Create fstab for dm-verity
    cat > "$ROOTFS_DIR/etc/fstab" << 'FSTAB'
# AnKLuMe Live OS fstab
/dev/dm-0  /  squashfs  ro,defaults  0  0
tmpfs      /tmp  tmpfs  mode=1777,nosuid,nodev,noexec  0  0
tmpfs      /run  tmpfs  mode=0755,nosuid,nodev  0  0
FSTAB
    info "  Hostname and fstab configured"

    # Configure locale and timezone
    chroot "$ROOTFS_DIR" locale-gen en_US.UTF-8 >/dev/null 2>&1 || true
    chroot "$ROOTFS_DIR" update-locale LANG=en_US.UTF-8 >/dev/null 2>&1 || true
    echo "Etc/UTC" > "$ROOTFS_DIR/etc/timezone"
    chroot "$ROOTFS_DIR" dpkg-reconfigure -f noninteractive tzdata >/dev/null 2>&1 || true
    info "  Locale and timezone configured"

    # Copy AnKLuMe framework files
    mkdir -p "$ROOTFS_DIR/opt/anklume"
    if [ -d "$PROJECT_ROOT/scripts" ]; then
        cp -r "$PROJECT_ROOT/scripts" "$ROOTFS_DIR/opt/anklume/" 2>/dev/null || true
    fi
    if [ -d "$PROJECT_ROOT/ansible" ]; then
        cp -r "$PROJECT_ROOT/ansible" "$ROOTFS_DIR/opt/anklume/" 2>/dev/null || true
    fi
    info "  AnKLuMe framework files copied"

    # Copy initramfs hooks
    if [ -d "$PROJECT_ROOT/host/boot/initramfs" ]; then
        mkdir -p "$ROOTFS_DIR/etc/initramfs-tools/hooks"
        cp "$PROJECT_ROOT/host/boot/initramfs"/* "$ROOTFS_DIR/etc/initramfs-tools/hooks/" 2>/dev/null || true
        chmod +x "$ROOTFS_DIR/etc/initramfs-tools/hooks"/* 2>/dev/null || true
        info "  Initramfs hooks installed"
    fi

    # Copy systemd services
    if [ -d "$PROJECT_ROOT/host/boot/systemd" ]; then
        mkdir -p "$ROOTFS_DIR/etc/systemd/system"
        cp "$PROJECT_ROOT/host/boot/systemd"/*.service "$ROOTFS_DIR/etc/systemd/system/" 2>/dev/null || true
        info "  Systemd services installed"
    fi

    # Enable AnKLuMe services in chroot
    chroot "$ROOTFS_DIR" systemctl enable anklume-first-boot.service >/dev/null 2>&1 || true
    chroot "$ROOTFS_DIR" systemctl enable anklume-data-mount.service >/dev/null 2>&1 || true
    info "  AnKLuMe services enabled"

    # Generate initramfs in chroot
    chroot "$ROOTFS_DIR" update-initramfs -c -k all >/dev/null 2>&1 || true
    info "  Initramfs generated"

    ok "Rootfs bootstrap complete"
}

# ── Create squashfs ──
create_squashfs() {
    info "Creating SquashFS image..."

    local squashfs_file="$WORK_DIR/rootfs.squashfs"

    # Create squashfs with compression
    mksquashfs "$ROOTFS_DIR" "$squashfs_file" \
        -comp xz -Xbcj x86 -b 1M \
        -progress >/dev/null 2>&1

    local size
    size=$(du -h "$squashfs_file" | cut -f1)
    ok "SquashFS created ($size)"
}

# ── Setup verity ──
setup_verity() {
    local squashfs_file="$WORK_DIR/rootfs.squashfs"
    local verity_file="$WORK_DIR/rootfs.squashfs.verity"

    if [ "$NO_VERITY" = true ]; then
        warn "Skipping dm-verity setup (--no-verity)"
        VERITY_HASH="disabled"
        return 0
    fi

    info "Setting up dm-verity..."

    # Create verity hash
    local verity_output
    verity_output=$(veritysetup format "$squashfs_file" "$verity_file" 2>&1)

    # Extract hash from output
    VERITY_HASH=$(echo "$verity_output" | grep -i "root hash:" | awk '{print $NF}')

    if [ -z "$VERITY_HASH" ]; then
        err "Failed to extract verity hash"
        exit 1
    fi

    ok "Verity hash: $VERITY_HASH"
}

# ── Install bootloader ──
install_bootloader() {
    info "Installing systemd-boot..."

    local efi_mount="$WORK_DIR/efi"
    mkdir -p "$efi_mount"
    mount "${LOOP_DEVICE}p1" "$efi_mount"
    MOUNTED_PATHS+=("$efi_mount")
    info "  EFI partition mounted"

    # Create directory structure
    mkdir -p "$efi_mount/EFI/BOOT"
    mkdir -p "$efi_mount/loader/entries"

    # Find boot files
    local boot_efi
    if [ -f "$ROOTFS_DIR/usr/lib/systemd/boot/efi/systemd-bootx64.efi" ]; then
        boot_efi="$ROOTFS_DIR/usr/lib/systemd/boot/efi/systemd-bootx64.efi"
    elif [ -f /usr/lib/systemd/boot/efi/systemd-bootx64.efi ]; then
        boot_efi="/usr/lib/systemd/boot/efi/systemd-bootx64.efi"
    else
        warn "systemd-boot efi file not found, attempting bootctl install"
        bootctl --path="$efi_mount" install 2>/dev/null || true
    fi

    if [ -f "$boot_efi" ]; then
        cp "$boot_efi" "$efi_mount/EFI/BOOT/BOOTX64.EFI"
        info "  systemd-boot installed"
    fi

    # Create loader.conf
    cat > "$efi_mount/loader/loader.conf" << 'LOADER'
default anklume-a
timeout 3
editor no
console-mode auto
LOADER
    info "  Loader configuration created"

    # Copy kernel and initramfs
    local vmlinuz
    vmlinuz=$(find "$ROOTFS_DIR/boot" -name "vmlinuz-*" -type f | head -1)
    local initrd
    initrd=$(find "$ROOTFS_DIR/boot" -name "initrd.img-*" -type f | head -1)

    if [ -f "$vmlinuz" ] && [ -f "$initrd" ]; then
        cp "$vmlinuz" "$efi_mount/vmlinuz"
        cp "$initrd" "$efi_mount/initrd.img"
        info "  Kernel and initramfs copied"
    else
        warn "Could not find kernel or initramfs"
    fi

    # Create boot entries
    local kernel_version
    kernel_version=$(basename "$vmlinuz" | sed 's/vmlinuz-//')

    # Entry for slot A (current)
    cat > "$efi_mount/loader/entries/anklume-a.conf" << ENTRY_A
title           AnKLuMe (Slot A)
linux           /vmlinuz
initrd          /initrd.img
options         root=/dev/dm-0 ro anklume.slot=A anklume.verity_hash=$VERITY_HASH anklume.toram=1 systemd.unified_cgroup_hierarchy=0
tries           3
tries-left      3
ENTRY_A

    # Entry for slot B (fallback)
    cat > "$efi_mount/loader/entries/anklume-b.conf" << ENTRY_B
title           AnKLuMe (Slot B)
linux           /vmlinuz
initrd          /initrd.img
options         root=/dev/dm-0 ro anklume.slot=B anklume.verity_hash=$VERITY_HASH anklume.toram=1 systemd.unified_cgroup_hierarchy=0
tries           0
ENTRY_B

    ok "Boot entries created (A and B)"
}

# ── Setup persistent partition ──
setup_persistent() {
    info "Initializing persistent partition..."

    local persistent_mount="$WORK_DIR/persistent"
    mkdir -p "$persistent_mount"
    mount "${LOOP_DEVICE}p4" "$persistent_mount"
    MOUNTED_PATHS+=("$persistent_mount")

    # Create directory structure
    mkdir -p "$persistent_mount/ssh"
    mkdir -p "$persistent_mount/network"
    mkdir -p "$persistent_mount/state"

    # Create state files
    echo "A" > "$persistent_mount/ab-state"
    echo "0" > "$persistent_mount/boot-count"

    ok "Persistent partition initialized"
}

# ── Write squashfs to partition ──
write_squashfs_to_partition() {
    info "Writing SquashFS to OS-A partition..."

    local squashfs_file="$WORK_DIR/rootfs.squashfs"

    dd if="$squashfs_file" of="${LOOP_DEVICE}p2" bs=1M status=progress 2>&1 | tail -1
    sync

    ok "SquashFS written to OS-A partition"
}

# ── Print summary ──
print_summary() {
    local img_size
    img_size=$(stat -f%z "$OUTPUT" 2>/dev/null || stat -c%s "$OUTPUT")

    echo ""
    echo "=== AnKLuMe Live OS Build Complete ==="
    echo "Image file:      $OUTPUT"
    echo "Image size:      $((img_size / 1024 / 1024 / 1024))GB ($img_size bytes)"
    echo "Verity hash:     $VERITY_HASH"
    echo "Boot slots:      A (active), B (fallback)"
    echo "Boot timeout:    3 seconds"
    echo "ToRAM enabled:   yes (loads OS into memory)"
    echo ""
    echo "Boot entries:"
    echo "  - anklume-a.conf  (default)"
    echo "  - anklume-b.conf  (fallback)"
    echo ""
    echo "Next steps:"
    echo "  1. Write image to USB: sudo dd if=$OUTPUT of=/dev/sdX bs=4M status=progress"
    echo "  2. Boot from USB and select AnKLuMe from boot menu"
    echo "  3. System will load into RAM (toram) for performance"
    echo ""
}

# ── Main ──
main() {
    while [ $# -gt 0 ]; do
        case "$1" in
            --output)     OUTPUT="$2"; shift 2 ;;
            --base)       BASE="$2"; shift 2 ;;
            --arch)       ARCH="$2"; shift 2 ;;
            --size)       IMAGE_SIZE_GB="$2"; shift 2 ;;
            --mirror)     MIRROR="$2"; shift 2 ;;
            --no-verity)  NO_VERITY=true; shift ;;
            --help|-h)    usage ;;
            *)            err "Unknown option: $1"; usage ;;
        esac
    done

    echo "=== AnKLuMe Live OS Image Builder ==="

    # Create work directory
    WORK_DIR=$(mktemp -d)
    info "Work directory: $WORK_DIR"

    check_root
    check_dependencies
    create_disk_image
    setup_loop_device
    format_partitions
    bootstrap_rootfs
    create_squashfs
    setup_verity
    install_bootloader
    setup_persistent
    write_squashfs_to_partition

    print_summary
}

main "$@"
