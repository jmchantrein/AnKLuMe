#!/usr/bin/env bash
# build-image.sh — Build bootable anklume Live OS image
# Usage: build-image.sh [OPTIONS]
#
# Options:
#   --output FILE     Output image file (default: anklume-live.iso)
#   --format FORMAT   Output format: iso or raw (default: iso)
#   --base DISTRO     Base distribution (default: debian)
#   --arch ARCH       Architecture (default: amd64)
#   --size SIZE_GB    Total image size in GB (default: 4, raw only)
#   --mirror URL      APT mirror URL
#   --no-verity       Skip dm-verity setup
#   --help            Show this help

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Source shared library
# shellcheck source=/dev/null
source "$SCRIPT_DIR/live-os-lib.sh"

# ── Defaults ──
OUTPUT=""
FORMAT="iso"
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
    echo "Build a bootable anklume Live OS image with squashfs and dm-verity."
    echo ""
    echo "Options:"
    echo "  --output FILE     Output image file (default: anklume-live.iso or .img)"
    echo "  --format FORMAT   Output format: iso or raw (default: iso)"
    echo "  --base DISTRO     Base distribution (default: debian, arch)"
    echo "  --arch ARCH       Architecture (default: amd64)"
    echo "  --size SIZE_GB    Total image size in GB (default: 4, raw format only)"
    echo "  --mirror URL      APT mirror URL"
    echo "  --no-verity       Skip dm-verity setup"
    echo "  --help            Show this help"
    echo ""
    echo "Examples:"
    echo "  $(basename "$0") --output anklume.iso --base arch"
    echo "  $(basename "$0") --format raw --output anklume.img --size 6"
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
    local cmds_common=(
        "mksquashfs" "veritysetup"
        "mount" "umount" "curl" "jq" "dd"
    )
    local cmds_distro=()
    local cmds_format=()

    case "$BASE" in
        debian|stable)
            cmds_distro=("debootstrap")
            ;;
        arch)
            cmds_distro=("pacstrap" "pacman")
            ;;
        *)
            err "Unsupported base: $BASE"
            exit 1
            ;;
    esac

    case "$FORMAT" in
        iso)
            cmds_format=("xorriso" "grub-mkimage" "mtools")
            ;;
        raw)
            cmds_format=("sgdisk" "mkfs.fat" "mkfs.ext4" "losetup" "bootctl")
            ;;
    esac

    local cmds=("${cmds_common[@]}" "${cmds_distro[@]}" "${cmds_format[@]}")

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

# ── Create disk image and setup loop device ──
create_disk_image() {
    info "Creating disk image: $OUTPUT (${IMAGE_SIZE_GB}GB)..."

    # Create image file (truncate for sparse)
    truncate -s "${IMAGE_SIZE_GB}G" "$OUTPUT"
    ok "Image file created (sparse ${IMAGE_SIZE_GB}GB)"

    # Attach as loop device BEFORE partitioning — sgdisk needs a block device
    LOOP_DEVICE=$(losetup --find --show "$OUTPUT")
    info "Attached loop device: $LOOP_DEVICE"

    # Create GPT partition table and partitions on the block device
    sgdisk --clear "$LOOP_DEVICE"
    sgdisk \
        --new=1:2048:+"${EFI_SIZE_MB}"M   --typecode=1:EF00 --change-name=1:"$ANKLUME_EFI_LABEL" \
        --new=2:0:+"${OS_SIZE_MB}"M       --typecode=2:8300 --change-name=2:"$ANKLUME_OSA_LABEL" \
        --new=3:0:+"${OS_SIZE_MB}"M       --typecode=3:8300 --change-name=3:"$ANKLUME_OSB_LABEL" \
        --new=4:0:0                      --typecode=4:8300 --change-name=4:"$ANKLUME_PERSIST_LABEL" \
        "$LOOP_DEVICE"

    ok "GPT partition table created"

    # Detach and re-attach with --partscan so the kernel discovers partitions
    losetup -d "$LOOP_DEVICE"
    LOOP_DEVICE=$(losetup --find --show --partscan "$OUTPUT")
    info "Re-attached with partscan: $LOOP_DEVICE"

    # Wait for partition devices to appear
    sleep 2
    blockdev --rereadpt "$LOOP_DEVICE" 2>/dev/null || true
    partprobe "$LOOP_DEVICE" 2>/dev/null || true
    udevadm settle 2>/dev/null || true
    for i in 1 2 3 4; do
        local retries=0
        while [ ! -e "${LOOP_DEVICE}p${i}" ] && [ $retries -lt 15 ]; do
            sleep 1
            partprobe "$LOOP_DEVICE" 2>/dev/null || true
            retries=$((retries + 1))
        done
        if [ ! -e "${LOOP_DEVICE}p${i}" ]; then
            err "Partition ${LOOP_DEVICE}p${i} did not appear"
            exit 1
        fi
    done

    ok "Loop device configured with 4 partitions"
}

# setup_loop_device merged into create_disk_image
setup_loop_device() {
    # Loop device already configured by create_disk_image
    ok "Loop device already set up"
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

# ── Bootstrap rootfs (Debian) ──
bootstrap_rootfs_debian() {
    info "Bootstrapping Debian rootfs..."

    ROOTFS_DIR="$WORK_DIR/rootfs"
    mkdir -p "$ROOTFS_DIR"

    # Resolve suite codename from BASE
    local suite="$BASE"
    case "$BASE" in
        debian)  suite="trixie" ;;
        stable)  suite="bookworm" ;;
    esac

    # Run debootstrap with core packages
    # Workaround: on CachyOS/Arch hosts without dpkg, debootstrap reads
    # pacman-conf Architecture which returns multiple lines (x86_64_v2/v3)
    # and fails. Write the arch hint file so debootstrap skips pacman-conf.
    # Workaround: on CachyOS/Arch hosts without dpkg, debootstrap reads
    # pacman-conf Architecture which returns multiple lines (x86_64_v2/v3)
    # and fails. Write the arch hint file so debootstrap skips pacman-conf.
    local debootstrap_dir="${DEBOOTSTRAP_DIR:-/usr/share/debootstrap}"
    local created_arch_hint=false
    if [ ! -f "$debootstrap_dir/arch" ] && ! command -v dpkg &>/dev/null; then
        echo "$ARCH" > "$debootstrap_dir/arch"
        created_arch_hint=true
        info "  Wrote $debootstrap_dir/arch = $ARCH (CachyOS workaround)"
    fi

    local debootstrap_opts="--arch=$ARCH"
    debootstrap_opts="$debootstrap_opts --include=systemd,linux-image-$ARCH,openssh-server,curl,jq,python3,python3-pip,python3-yaml,ca-certificates"

    if [ -n "$MIRROR" ]; then
        # shellcheck disable=SC2086
        debootstrap $debootstrap_opts "$suite" "$ROOTFS_DIR" "$MIRROR"
    else
        # shellcheck disable=SC2086
        debootstrap $debootstrap_opts "$suite" "$ROOTFS_DIR"
    fi
    # Clean up the workaround arch file
    if [ "$created_arch_hint" = true ]; then
        rm -f "$debootstrap_dir/arch"
    fi
    info "  Debootstrap complete"

    # Bind-mount pseudo-filesystems for chroot operations
    mount --bind /proc "$ROOTFS_DIR/proc"
    mount --bind /sys "$ROOTFS_DIR/sys"
    mount --bind /dev "$ROOTFS_DIR/dev"
    mount --bind /dev/pts "$ROOTFS_DIR/dev/pts"
    MOUNTED_PATHS+=("$ROOTFS_DIR/dev/pts" "$ROOTFS_DIR/dev" "$ROOTFS_DIR/sys" "$ROOTFS_DIR/proc")

    # Install additional packages via chroot (all anklume runtime deps)
    local packages="nftables cryptsetup btrfs-progs squashfs-tools"
    packages="$packages firmware-linux-free"
    packages="$packages ansible git make sudo nano"
    packages="$packages iproute2 dmidecode lsof htop"
    # Incus: Debian Trixie ships incus in official repos
    packages="$packages incus"
    chroot "$ROOTFS_DIR" apt-get update -qq
    # shellcheck disable=SC2086
    chroot "$ROOTFS_DIR" apt-get install -y -qq $packages 2>&1 | tail -5
    info "  Additional packages installed (incl. incus, ansible, git)"

    # Configure system
    echo "anklume" > "$ROOTFS_DIR/etc/hostname"

    # Minimal fstab for live overlay — root is already mounted by initramfs
    cat > "$ROOTFS_DIR/etc/fstab" << 'FSTAB'
# anklume Live OS — root is overlay (squashfs ro + tmpfs rw)
# No entries needed; systemd auto-mounts /proc /sys /dev /run
FSTAB
    info "  Hostname and fstab configured"

    # Set root password for live system (autologin, but needed for emergency/sulogin)
    echo "root:anklume" | chroot "$ROOTFS_DIR" chpasswd 2>/dev/null || true
    info "  Root password set (anklume)"

    # Configure locale and timezone
    chroot "$ROOTFS_DIR" locale-gen en_US.UTF-8 >/dev/null 2>&1 || true
    chroot "$ROOTFS_DIR" update-locale LANG=en_US.UTF-8 >/dev/null 2>&1 || true
    echo "Etc/UTC" > "$ROOTFS_DIR/etc/timezone"
    chroot "$ROOTFS_DIR" dpkg-reconfigure -f noninteractive tzdata >/dev/null 2>&1 || true
    info "  Locale and timezone configured"

    # Copy entire anklume framework (git repo) into rootfs
    mkdir -p "$ROOTFS_DIR/opt/anklume"
    # Use git archive to get a clean copy without .git and gitignored files
    if command -v git &>/dev/null && [ -d "$PROJECT_ROOT/.git" ]; then
        # Allow git archive from a repo owned by a different user (running as root)
        git config --global --add safe.directory "$PROJECT_ROOT" 2>/dev/null || true
        git -C "$PROJECT_ROOT" archive HEAD | tar -x -C "$ROOTFS_DIR/opt/anklume/"
    else
        # Fallback: copy essential dirs
        for d in scripts roles roles_custom Makefile site.yml snapshot.yml \
                 ansible.cfg inventory group_vars host_vars pyproject.toml \
                 infra.yml requirements.yml; do
            [ -e "$PROJECT_ROOT/$d" ] && cp -r "$PROJECT_ROOT/$d" "$ROOTFS_DIR/opt/anklume/" 2>/dev/null || true
        done
    fi
    info "  anklume framework files copied"

    # Create /etc/anklume marker
    mkdir -p "$ROOTFS_DIR/etc/anklume"
    echo "0" > "$ROOTFS_DIR/etc/anklume/absolute_level"
    echo "0" > "$ROOTFS_DIR/etc/anklume/relative_level"
    echo "false" > "$ROOTFS_DIR/etc/anklume/vm_nested"

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

    # Enable anklume services in chroot
    chroot "$ROOTFS_DIR" systemctl enable anklume-first-boot.service >/dev/null 2>&1 || true
    chroot "$ROOTFS_DIR" systemctl enable anklume-data-mount.service >/dev/null 2>&1 || true
    info "  anklume services enabled"

    # Generate initramfs in chroot
    chroot "$ROOTFS_DIR" update-initramfs -c -k all >/dev/null 2>&1 || true
    info "  Initramfs generated"

    # Unmount pseudo-filesystems before creating squashfs
    umount "$ROOTFS_DIR/dev/pts" 2>/dev/null || true
    umount "$ROOTFS_DIR/dev" 2>/dev/null || true
    umount "$ROOTFS_DIR/sys" 2>/dev/null || true
    umount "$ROOTFS_DIR/proc" 2>/dev/null || true
    # Remove them from MOUNTED_PATHS to avoid double-unmount in cleanup
    MOUNTED_PATHS=()

    ok "Rootfs bootstrap complete"
}

# ── Bootstrap rootfs (Arch) ──
bootstrap_rootfs_arch() {
    info "Bootstrapping Arch rootfs..."

    ROOTFS_DIR="$WORK_DIR/rootfs"
    mkdir -p "$ROOTFS_DIR"

    # Prepare a vanilla Arch pacman.conf to avoid CachyOS mirror issues.
    # pacstrap -K copies host config; we override the mirrorlist first so
    # that only standard Arch repos are used in the rootfs.
    mkdir -p "$ROOTFS_DIR/etc/pacman.d"
    cat > "$ROOTFS_DIR/etc/pacman.d/mirrorlist" << 'MIRRORS'
Server = https://geo.mirror.pkgbuild.com/$repo/os/$arch
Server = https://mirror.rackspace.com/archlinux/$repo/os/$arch
Server = https://archlinux.mailtunnel.eu/$repo/os/$arch
MIRRORS

    # Create a minimal pacman.conf with only vanilla Arch repos
    cat > "$WORK_DIR/pacman-vanilla.conf" << 'PACCONF'
[options]
HoldPkg     = pacman glibc
Architecture = auto
SigLevel    = Required DatabaseOptional
LocalFileSigLevel = Optional

[core]
Include = /etc/pacman.d/mirrorlist

[extra]
Include = /etc/pacman.d/mirrorlist
PACCONF

    # Run pacstrap with vanilla config
    # Include all anklume runtime deps: Incus, Ansible, Python, Git, etc.
    pacstrap -C "$WORK_DIR/pacman-vanilla.conf" -K "$ROOTFS_DIR" \
        base linux linux-firmware mkinitcpio \
        openssh curl jq python python-pip python-yaml file \
        nftables cryptsetup btrfs-progs squashfs-tools \
        incus ansible git make ca-certificates \
        sudo nano iproute2 systemd-resolvconf \
        dmidecode lsof htop

    info "  Pacstrap complete"

    # Bind-mount pseudo-filesystems for chroot operations
    mount --bind /proc "$ROOTFS_DIR/proc"
    mount --bind /sys "$ROOTFS_DIR/sys"
    mount --bind /dev "$ROOTFS_DIR/dev"
    mount --bind /dev/pts "$ROOTFS_DIR/dev/pts"
    MOUNTED_PATHS+=("$ROOTFS_DIR/dev/pts" "$ROOTFS_DIR/dev" "$ROOTFS_DIR/sys" "$ROOTFS_DIR/proc")

    # Configure hostname
    echo "anklume" > "$ROOTFS_DIR/etc/hostname"
    info "  Hostname configured"

    # Minimal fstab for live overlay — root is already mounted by initramfs
    cat > "$ROOTFS_DIR/etc/fstab" << 'FSTAB'
# anklume Live OS — root is overlay (squashfs ro + tmpfs rw)
# No entries needed; systemd auto-mounts /proc /sys /dev /run
FSTAB
    info "  fstab configured"

    # Set root password for live system
    echo "root:anklume" | chroot "$ROOTFS_DIR" chpasswd 2>/dev/null || true
    info "  Root password set (anklume)"

    # Configure locale
    sed -i 's/#en_US.UTF-8/en_US.UTF-8/' "$ROOTFS_DIR/etc/locale.gen"
    chroot "$ROOTFS_DIR" locale-gen >/dev/null 2>&1 || true
    echo "LANG=en_US.UTF-8" > "$ROOTFS_DIR/etc/locale.conf"
    info "  Locale configured"

    # Configure timezone
    ln -sf /usr/share/zoneinfo/UTC "$ROOTFS_DIR/etc/localtime"
    info "  Timezone configured"

    # Copy entire anklume framework (git repo) into rootfs
    mkdir -p "$ROOTFS_DIR/opt/anklume"
    if command -v git &>/dev/null && [ -d "$PROJECT_ROOT/.git" ]; then
        git -C "$PROJECT_ROOT" archive HEAD | tar -x -C "$ROOTFS_DIR/opt/anklume/"
    else
        for d in scripts roles roles_custom Makefile site.yml snapshot.yml \
                 ansible.cfg inventory group_vars host_vars pyproject.toml \
                 infra.yml requirements.yml; do
            [ -e "$PROJECT_ROOT/$d" ] && cp -r "$PROJECT_ROOT/$d" "$ROOTFS_DIR/opt/anklume/" 2>/dev/null || true
        done
    fi
    info "  anklume framework files copied"

    # Create /etc/anklume marker
    mkdir -p "$ROOTFS_DIR/etc/anklume"
    echo "0" > "$ROOTFS_DIR/etc/anklume/absolute_level"
    echo "0" > "$ROOTFS_DIR/etc/anklume/relative_level"
    echo "false" > "$ROOTFS_DIR/etc/anklume/vm_nested"

    # Copy mkinitcpio hooks
    # ZFS not included by default on Arch (requires archzfs repo). Use BTRFS.
    if [ -d "$PROJECT_ROOT/host/boot/mkinitcpio" ]; then
        mkdir -p "$ROOTFS_DIR/etc/initcpio/hooks"
        mkdir -p "$ROOTFS_DIR/etc/initcpio/install"
        if [ -d "$PROJECT_ROOT/host/boot/mkinitcpio/hooks" ]; then
            cp "$PROJECT_ROOT/host/boot/mkinitcpio/hooks"/* "$ROOTFS_DIR/etc/initcpio/hooks/" 2>/dev/null || true
            chmod +x "$ROOTFS_DIR/etc/initcpio/hooks"/* 2>/dev/null || true
        fi
        if [ -d "$PROJECT_ROOT/host/boot/mkinitcpio/install" ]; then
            cp "$PROJECT_ROOT/host/boot/mkinitcpio/install"/* "$ROOTFS_DIR/etc/initcpio/install/" 2>/dev/null || true
            chmod +x "$ROOTFS_DIR/etc/initcpio/install"/* 2>/dev/null || true
        fi
        info "  mkinitcpio hooks installed"
    fi

    # Configure mkinitcpio — custom hooks BEFORE filesystems, no autodetect (strips modules)
    # MODULES: virtio drivers for VM boot, iso9660/squashfs for live ISO, dm-verity
    sed -i 's/^MODULES=.*/MODULES=(virtio_blk virtio_scsi virtio_pci virtio_net sr_mod cdrom iso9660 squashfs overlay loop dm-mod dm-verity)/' \
        "$ROOTFS_DIR/etc/mkinitcpio.conf"
    sed -i 's/^HOOKS=.*/HOOKS=(base udev modconf block keyboard consolefont anklume-verity anklume-toram filesystems fsck)/' \
        "$ROOTFS_DIR/etc/mkinitcpio.conf"
    info "  mkinitcpio configured"

    # Copy systemd services
    if [ -d "$PROJECT_ROOT/host/boot/systemd" ]; then
        mkdir -p "$ROOTFS_DIR/etc/systemd/system"
        cp "$PROJECT_ROOT/host/boot/systemd"/*.service "$ROOTFS_DIR/etc/systemd/system/" 2>/dev/null || true
        info "  Systemd services installed"
    fi

    # Install incus-agent service for VM testing
    cat > "$ROOTFS_DIR/etc/systemd/system/incus-agent.service" << 'AGENT'
[Unit]
Description=Incus VM Agent
Documentation=https://linuxcontainers.org/incus
ConditionVirtualization=vm
After=local-fs.target

[Service]
Type=notify
ExecStartPre=/bin/mkdir -p /run/incus_agent
ExecStartPre=/bin/sh -c "mount -t virtiofs config /run/incus_agent 2>/dev/null || mount -t 9p config /run/incus_agent -o access=0,trans=virtio 2>/dev/null || true"
ExecStartPre=/bin/sh -c "test -f /run/incus_agent/incus-agent && cp /run/incus_agent/incus-agent /usr/local/bin/ && chmod +x /usr/local/bin/incus-agent || true"
ExecStart=/usr/local/bin/incus-agent
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
AGENT
    info "  Incus agent service installed"

    # Create vconsole.conf — French AZERTY keyboard layout
    echo "KEYMAP=fr" > "$ROOTFS_DIR/etc/vconsole.conf"

    # Enable anklume services in chroot
    chroot "$ROOTFS_DIR" systemctl enable anklume-first-boot.service >/dev/null 2>&1 || true
    chroot "$ROOTFS_DIR" systemctl enable anklume-data-mount.service >/dev/null 2>&1 || true
    # incus-agent: don't enable — not useful in live ISO (no virtiofs config channel)
    # Mask tmp.mount — /tmp is writable via overlay, no separate tmpfs needed
    chroot "$ROOTFS_DIR" systemctl mask tmp.mount >/dev/null 2>&1 || true
    info "  anklume services enabled"

    # Detect installed kernel version in the rootfs
    local kver
    kver=$(ls "$ROOTFS_DIR/usr/lib/modules/" 2>/dev/null | head -1)
    info "  Detected kernel version: ${kver:-NONE}"

    # Ensure kernel is in /boot/ (pacman hooks may fail in chroot)
    if [ ! -f "$ROOTFS_DIR/boot/vmlinuz-linux" ] && [ -n "$kver" ]; then
        if [ -f "$ROOTFS_DIR/usr/lib/modules/$kver/vmlinuz" ]; then
            cp "$ROOTFS_DIR/usr/lib/modules/$kver/vmlinuz" "$ROOTFS_DIR/boot/vmlinuz-linux"
            info "  Kernel copied to /boot/vmlinuz-linux from modules"
        fi
    fi

    # Create preset file if missing (pacstrap hooks may have failed)
    if [ ! -f "$ROOTFS_DIR/etc/mkinitcpio.d/linux.preset" ] && [ -n "$kver" ]; then
        mkdir -p "$ROOTFS_DIR/etc/mkinitcpio.d"
        cat > "$ROOTFS_DIR/etc/mkinitcpio.d/linux.preset" << PRESET
ALL_config="/etc/mkinitcpio.conf"
ALL_kver="$kver"
PRESETS=('default')
default_image="/boot/initramfs-linux.img"
PRESET
        info "  Created linux.preset for kernel $kver"
    fi

    # Generate initramfs with explicit kernel version
    if [ -n "$kver" ]; then
        if ! chroot "$ROOTFS_DIR" mkinitcpio -k "$kver" -g /boot/initramfs-linux.img 2>&1; then
            warn "mkinitcpio with custom hooks failed, trying without"
            # Restore default hooks and retry
            chroot "$ROOTFS_DIR" mkinitcpio -k "$kver" -S anklume-verity,anklume-toram \
                -g /boot/initramfs-linux.img 2>&1 || warn "mkinitcpio fallback also failed"
        fi
    fi

    # Verify kernel and initramfs exist
    if [ -f "$ROOTFS_DIR/boot/vmlinuz-linux" ]; then
        info "  Kernel: /boot/vmlinuz-linux"
    else
        warn "  Kernel NOT found in /boot/"
    fi
    if [ -f "$ROOTFS_DIR/boot/initramfs-linux.img" ]; then
        info "  Initramfs: /boot/initramfs-linux.img ($(du -h "$ROOTFS_DIR/boot/initramfs-linux.img" | cut -f1))"
    else
        err "  Initramfs NOT generated — image will not boot"
    fi

    # Unmount pseudo-filesystems before creating squashfs
    umount "$ROOTFS_DIR/dev/pts" 2>/dev/null || true
    umount "$ROOTFS_DIR/dev" 2>/dev/null || true
    umount "$ROOTFS_DIR/sys" 2>/dev/null || true
    umount "$ROOTFS_DIR/proc" 2>/dev/null || true
    # Remove them from MOUNTED_PATHS to avoid double-unmount in cleanup
    MOUNTED_PATHS=()

    ok "Rootfs bootstrap complete"
}

# ── Dispatch bootstrap_rootfs ──
bootstrap_rootfs() {
    case "$BASE" in
        debian|stable)
            bootstrap_rootfs_debian
            ;;
        arch)
            bootstrap_rootfs_arch
            ;;
        *)
            err "Unsupported base: $BASE"
            exit 1
            ;;
    esac
}

# ── Create squashfs ──
create_squashfs() {
    info "Creating SquashFS image..."

    local squashfs_file="$WORK_DIR/rootfs.squashfs"

    # Create squashfs with zstd compression (fast, good ratio)
    # Exclude pseudo-filesystem mount points just in case
    mksquashfs "$ROOTFS_DIR" "$squashfs_file" \
        -comp zstd -Xcompression-level 15 -b 256K \
        -no-exports -no-xattrs \
        -e proc sys dev run tmp

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

# ── Generate checksums ──
generate_checksums() {
    info "Unmounting partitions and detaching loop device before checksum..."

    # Unmount all mounted partitions (reverse order) so the loop device is fully released
    for ((i=${#MOUNTED_PATHS[@]}-1; i>=0; i--)); do
        local mp="${MOUNTED_PATHS[$i]}"
        if mountpoint -q "$mp" 2>/dev/null; then
            umount -R "$mp" 2>/dev/null || true
        fi
    done
    MOUNTED_PATHS=()

    sync

    if [ -n "$LOOP_DEVICE" ] && losetup -a | grep -q "$LOOP_DEVICE"; then
        losetup -d "$LOOP_DEVICE"
        LOOP_DEVICE=""
    fi

    info "Generating checksums..."
    sha256sum "$OUTPUT" > "${OUTPUT}.sha256"
    ok "SHA256: $(cat "${OUTPUT}.sha256")"
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

    # Copy kernel and initramfs based on distro
    local vmlinuz
    local initrd

    case "$BASE" in
        debian|stable)
            vmlinuz=$(find "$ROOTFS_DIR/boot" -name "vmlinuz-*" -type f | head -1)
            initrd=$(find "$ROOTFS_DIR/boot" -name "initrd.img-*" -type f | head -1)
            ;;
        arch)
            vmlinuz="$ROOTFS_DIR/boot/vmlinuz-linux"
            initrd="$ROOTFS_DIR/boot/initramfs-linux.img"
            # Fallback: check /usr/lib/modules/*/vmlinuz if /boot is empty
            if [ ! -f "$vmlinuz" ]; then
                vmlinuz=$(find "$ROOTFS_DIR/usr/lib/modules" -name "vmlinuz" -type f 2>/dev/null | head -1)
            fi
            ;;
    esac

    if [ -f "$vmlinuz" ] && [ -f "$initrd" ]; then
        cp "$vmlinuz" "$efi_mount/vmlinuz"
        cp "$initrd" "$efi_mount/initrd.img"
        info "  Kernel and initramfs copied to ESP"
    elif [ -f "$vmlinuz" ]; then
        cp "$vmlinuz" "$efi_mount/vmlinuz"
        warn "Kernel copied but initramfs not found — boot may fail"
    else
        err "Could not find kernel or initramfs — image will not boot"
    fi

    # Create boot entries
    # Entry for slot A (current)
    cat > "$efi_mount/loader/entries/anklume-a.conf" << ENTRY_A
title           anklume (Slot A)
linux           /vmlinuz
initrd          /initrd.img
options         root=/dev/dm-0 ro anklume.slot=A anklume.verity_hash=$VERITY_HASH anklume.toram=1 systemd.unified_cgroup_hierarchy=0 console=tty0 console=ttyS0,115200n8
tries           3
tries-left      3
ENTRY_A

    # Entry for slot B (fallback)
    cat > "$efi_mount/loader/entries/anklume-b.conf" << ENTRY_B
title           anklume (Slot B)
linux           /vmlinuz
initrd          /initrd.img
options         root=/dev/dm-0 ro anklume.slot=B anklume.verity_hash=$VERITY_HASH anklume.toram=1 systemd.unified_cgroup_hierarchy=0 console=tty0 console=ttyS0,115200n8
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

# ── Assemble hybrid ISO ──
assemble_iso() {
    info "Assembling hybrid ISO..."

    local squashfs_file="$WORK_DIR/rootfs.squashfs"
    local verity_file="$WORK_DIR/rootfs.squashfs.verity"
    local staging="$WORK_DIR/iso-staging"

    # Create ISO staging directory
    mkdir -p "$staging/boot/grub"
    mkdir -p "$staging/EFI/BOOT"
    mkdir -p "$staging/live"

    # Copy squashfs and verity hash
    cp "$squashfs_file" "$staging/live/rootfs.squashfs"
    if [ -f "$verity_file" ]; then
        cp "$verity_file" "$staging/live/rootfs.verity"
    fi
    info "  Squashfs and verity files staged"

    # Copy kernel and initramfs
    local vmlinuz initrd
    case "$BASE" in
        debian|stable)
            vmlinuz=$(find "$ROOTFS_DIR/boot" -name "vmlinuz-*" -type f 2>/dev/null | head -1)
            initrd=$(find "$ROOTFS_DIR/boot" -name "initrd.img-*" -type f 2>/dev/null | head -1)
            ;;
        arch)
            vmlinuz="$ROOTFS_DIR/boot/vmlinuz-linux"
            initrd="$ROOTFS_DIR/boot/initramfs-linux.img"
            if [ ! -f "$vmlinuz" ]; then
                vmlinuz=$(find "$ROOTFS_DIR/usr/lib/modules" -name "vmlinuz" -type f 2>/dev/null | head -1)
            fi
            ;;
    esac

    if [ -f "$vmlinuz" ] && [ -f "$initrd" ]; then
        cp "$vmlinuz" "$staging/boot/vmlinuz"
        cp "$initrd" "$staging/boot/initrd.img"
        info "  Kernel and initramfs staged"
    else
        err "Could not find kernel ($vmlinuz) or initramfs ($initrd)"
        exit 1
    fi

    # Create GRUB config from template, substituting verity hash
    local grub_template="$PROJECT_ROOT/host/boot/grub/grub.cfg"
    if [ -f "$grub_template" ]; then
        sed "s/VERITY_HASH_PLACEHOLDER/$VERITY_HASH/g" "$grub_template" > "$staging/boot/grub/grub.cfg"
    else
        # Inline fallback if template missing
        cat > "$staging/boot/grub/grub.cfg" << GRUBCFG
insmod part_gpt
insmod part_msdos
insmod iso9660
insmod fat
insmod search_label
insmod linux
insmod gzio
insmod all_video

set timeout=5
set default=0

search --no-floppy --label ANKLUME-LIVE --set=root

menuentry "anklume Live OS (toram)" {
    linux /boot/vmlinuz ro anklume.boot_mode=iso anklume.slot=A anklume.toram=1 anklume.verity_hash=$VERITY_HASH console=tty0 console=ttyS0,115200n8
    initrd /boot/initrd.img
}
menuentry "anklume Live OS (direct)" {
    linux /boot/vmlinuz ro anklume.boot_mode=iso anklume.slot=A anklume.verity_hash=$VERITY_HASH console=tty0 console=ttyS0,115200n8
    initrd /boot/initrd.img
}
GRUBCFG
    fi
    info "  GRUB config created"

    # Determine GRUB platform paths
    local grub_prefix="/usr/lib/grub"
    if [ -d "$ROOTFS_DIR/usr/lib/grub" ]; then
        grub_prefix="$ROOTFS_DIR/usr/lib/grub"
    fi

    # Create GRUB UEFI standalone image
    local grub_efi_dir=""
    for d in "$grub_prefix/x86_64-efi" /usr/lib/grub/x86_64-efi; do
        if [ -d "$d" ]; then
            grub_efi_dir="$d"
            break
        fi
    done

    if [ -n "$grub_efi_dir" ]; then
        grub-mkstandalone \
            --format=x86_64-efi \
            --output="$staging/EFI/BOOT/BOOTX64.EFI" \
            --locales="" \
            --fonts="" \
            --install-modules="normal search search_fs_uuid search_fs_file search_label iso9660 part_gpt part_msdos fat ext2 linux gzio" \
            "boot/grub/grub.cfg=$staging/boot/grub/grub.cfg" \
            2>/dev/null || warn "grub-mkstandalone failed, trying grub-mkimage"
        info "  GRUB EFI standalone created"
    fi

    # Create EFI boot image (FAT) for El Torito
    local efi_img="$staging/EFI/BOOT/efiboot.img"
    local efi_size_kb=16384
    dd if=/dev/zero of="$efi_img" bs=1K count=$efi_size_kb 2>/dev/null
    mkfs.fat -F 16 "$efi_img" >/dev/null 2>&1
    mmd -i "$efi_img" ::EFI ::EFI/BOOT 2>/dev/null
    if [ -f "$staging/EFI/BOOT/BOOTX64.EFI" ]; then
        mcopy -i "$efi_img" "$staging/EFI/BOOT/BOOTX64.EFI" ::EFI/BOOT/BOOTX64.EFI
    fi
    info "  EFI boot image created"

    # Create GRUB BIOS image (for hybrid MBR boot)
    local grub_bios_dir=""
    for d in "$grub_prefix/i386-pc" /usr/lib/grub/i386-pc; do
        if [ -d "$d" ]; then
            grub_bios_dir="$d"
            break
        fi
    done

    local bios_img="$WORK_DIR/bios.img"
    if [ -n "$grub_bios_dir" ]; then
        grub-mkimage \
            -O i386-pc \
            -o "$bios_img" \
            -p /boot/grub \
            --prefix=/boot/grub \
            biosdisk iso9660 part_msdos \
            2>/dev/null || warn "grub-mkimage for BIOS failed"
        info "  GRUB BIOS image created"
    else
        warn "GRUB i386-pc modules not found — ISO will be UEFI-only"
    fi

    # Assemble ISO with xorriso
    local xorriso_args=(
        -as mkisofs
        -iso-level 3
        -full-iso9660-filenames
        -volid "$ANKLUME_ISO_LABEL"
        -joliet -joliet-long
        -rational-rock
    )

    # UEFI boot (El Torito)
    xorriso_args+=(
        -eltorito-alt-boot
        -e EFI/BOOT/efiboot.img
        -no-emul-boot
        -isohybrid-gpt-basdat
    )

    # BIOS boot (El Torito) if available
    if [ -n "$grub_bios_dir" ] && [ -f "$grub_bios_dir/cdboot.img" ] && [ -f "$grub_bios_dir/boot.img" ]; then
        cp "$grub_bios_dir/cdboot.img" "$staging/boot/grub/cdboot.img"
        cp "$grub_bios_dir/boot.img" "$staging/boot/grub/boot.img"
        # BIOS must be the first El Torito entry for hybrid MBR
        xorriso_args=(
            -as mkisofs
            -iso-level 3
            -full-iso9660-filenames
            -volid "$ANKLUME_ISO_LABEL"
            -joliet -joliet-long
            -rational-rock
            -eltorito-boot boot/grub/cdboot.img
            -no-emul-boot
            -boot-load-size 4
            -boot-info-table
            --grub2-boot-info
            --grub2-mbr "$grub_bios_dir/boot_hybrid.img"
            -eltorito-alt-boot
            -e EFI/BOOT/efiboot.img
            -no-emul-boot
            -append_partition 2 0xef "$efi_img"
        )
    fi

    xorriso_args+=(-output "$OUTPUT" "$staging")

    info "  Running xorriso..."
    # xorriso returns non-zero on MISHAP warnings even when ISO is valid
    xorriso "${xorriso_args[@]}" 2>&1 | tail -5 || true
    if [ ! -f "$OUTPUT" ]; then
        err "xorriso failed — no output file"
        exit 1
    fi

    ok "Hybrid ISO assembled: $OUTPUT"
}

# ── Print summary ──
print_summary() {
    local img_size
    img_size=$(stat -f%z "$OUTPUT" 2>/dev/null || stat -c%s "$OUTPUT")

    local img_size_mb=$((img_size / 1024 / 1024))

    echo ""
    echo "=== anklume Live OS Build Complete ==="
    echo "Image file:      $OUTPUT"
    echo "Format:          $FORMAT"
    echo "Image size:      ${img_size_mb}MB ($img_size bytes)"
    echo "Base distro:     $BASE"
    echo "Verity hash:     $VERITY_HASH"
    echo "Checksum:        ${OUTPUT}.sha256"
    echo ""
    if [ "$FORMAT" = "iso" ]; then
        echo "Boot modes:      BIOS + UEFI (hybrid ISO)"
        echo "Menu entries:    toram (default), direct"
        echo ""
        echo "Next steps:"
        echo "  1. Write to USB: sudo dd if=$OUTPUT of=/dev/sdX bs=4M status=progress"
        echo "  2. Or use Ventoy: copy $OUTPUT to Ventoy USB"
        echo "  3. Boot and select anklume from GRUB menu"
    else
        echo "Boot slots:      A (active), B (fallback)"
        echo "Boot timeout:    3 seconds"
        echo "ToRAM enabled:   yes (loads OS into memory)"
        echo ""
        echo "Next steps:"
        echo "  1. Write image to USB: sudo dd if=$OUTPUT of=/dev/sdX bs=4M status=progress"
        echo "  2. Boot from USB and select anklume from boot menu"
        echo "  3. System will load into RAM (toram) for performance"
    fi
    echo ""
}

# ── Main ──
main() {
    while [ $# -gt 0 ]; do
        case "$1" in
            --output)     OUTPUT="$2"; shift 2 ;;
            --format)     FORMAT="$2"; shift 2 ;;
            --base)       BASE="$2"; shift 2 ;;
            --arch)       ARCH="$2"; shift 2 ;;
            --size)       IMAGE_SIZE_GB="$2"; shift 2 ;;
            --mirror)     MIRROR="$2"; shift 2 ;;
            --no-verity)  NO_VERITY=true; shift ;;
            --help|-h)    usage ;;
            *)            err "Unknown option: $1"; usage ;;
        esac
    done

    # Validate format
    case "$FORMAT" in
        iso|raw) ;;
        *) err "Invalid format: $FORMAT (must be iso or raw)"; exit 1 ;;
    esac

    # Set default output name based on format
    if [ -z "$OUTPUT" ]; then
        OUTPUT="anklume-live.$FORMAT"
        if [ "$FORMAT" = "raw" ]; then
            OUTPUT="anklume-live.img"
        fi
    fi

    echo "=== anklume Live OS Image Builder ==="
    info "Format: $FORMAT"

    # Create work directory
    WORK_DIR=$(mktemp -d)
    info "Work directory: $WORK_DIR"

    check_root
    check_dependencies
    bootstrap_rootfs
    create_squashfs
    setup_verity

    if [ "$FORMAT" = "iso" ]; then
        assemble_iso
        generate_checksums
    else
        create_disk_image
        setup_loop_device
        format_partitions
        install_bootloader
        setup_persistent
        write_squashfs_to_partition
        generate_checksums
    fi

    print_summary
}

main "$@"
