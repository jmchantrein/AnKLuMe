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
#   --desktop DE      Desktop environment: all, sway, labwc, kde, minimal (default: all)
#   --mirror URL      APT mirror URL
#   --no-verity       Skip dm-verity setup
#   --cache-rootfs DIR  Cache rootfs tarball for faster rebuilds
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
DESKTOP="all"
MIRROR=""
NO_VERITY=false
LIVE_USER="jmc"
CACHE_ROOTFS=""
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
    echo "  --desktop DE      Desktop environment (default: all)"
    echo "                    all=sway+labwc+kde, sway, labwc, kde, minimal=console only"
    echo "  --mirror URL      APT mirror URL"
    echo "  --no-verity       Skip dm-verity setup"
    echo "  --cache-rootfs DIR  Cache rootfs tarball (skip bootstrap on rebuild)"
    echo "  --help            Show this help"
    echo ""
    echo "Examples:"
    echo "  $(basename "$0") --output anklume.iso --base arch"
    echo "  $(basename "$0") --output anklume.iso --desktop sway"
    echo "  $(basename "$0") --cache-rootfs /home/user/iso-cache  # fast rebuild"
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

# ── Create live user with sudo (shared between Debian and Arch) ──
create_live_user() {
    local rootfs="$1"
    local user="$LIVE_USER"
    local home="/home/$user"

    # Create user with home directory and bash shell
    chroot "$rootfs" useradd -m -s /bin/bash -G wheel,sudo,video,audio,input "$user" 2>/dev/null \
        || chroot "$rootfs" useradd -m -s /bin/bash -G wheel,video,audio "$user" 2>/dev/null \
        || true
    # Set password (same as root: anklume)
    echo "$user:anklume" | chroot "$rootfs" chpasswd 2>/dev/null || {
        local pw_hash
        pw_hash=$(openssl passwd -6 "anklume")
        sed -i "s|^${user}:[^:]*:|${user}:${pw_hash}:|" "$rootfs/etc/shadow"
    }
    # Passwordless sudo
    mkdir -p "$rootfs/etc/sudoers.d"
    echo "$user ALL=(ALL) NOPASSWD: ALL" > "$rootfs/etc/sudoers.d/90-$user"
    chmod 440 "$rootfs/etc/sudoers.d/90-$user"

    # Add anklume to PATH via symlink (make -C /opt/anklume wrapper)
    cat > "$rootfs/usr/local/bin/anklume" << 'ANKLUME_BIN'
#!/bin/sh
exec make -C /opt/anklume "$@"
ANKLUME_BIN
    chmod +x "$rootfs/usr/local/bin/anklume"

    # Set anklume CLI mode to student (French help by default)
    mkdir -p "$rootfs/$home/.anklume"
    echo "student" > "$rootfs/$home/.anklume/mode"
    chroot "$rootfs" chown -R "$user:$user" "$home/.anklume" 2>/dev/null || true

    info "  User '$user' created with sudo (password: anklume, mode: student/fr)"
}

# ── Install desktop configs (shared between Debian and Arch) ──
install_desktop_configs() {
    local rootfs="$1"
    local desktop_dir="$PROJECT_ROOT/host/boot/desktop"
    local user_home="/home/$LIVE_USER"

    # Auto-login on tty1 as live user (not root)
    mkdir -p "$rootfs/etc/systemd/system/getty@tty1.service.d"
    cat > "$rootfs/etc/systemd/system/getty@tty1.service.d/autologin.conf" << AUTOLOGIN
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin $LIVE_USER --noclear %I \$TERM
AUTOLOGIN

    # bash_profile (DE dispatcher)
    cp "$desktop_dir/bash_profile" "$rootfs/$user_home/.bash_profile"

    # foot terminal config (shared)
    mkdir -p "$rootfs/$user_home/.config/foot"
    cp "$desktop_dir/foot.ini" "$rootfs/$user_home/.config/foot/foot.ini"

    # Splash script and quotes (English + French)
    cp "$desktop_dir/anklume-splash.sh" "$rootfs/opt/anklume/host/boot/desktop/anklume-splash.sh" 2>/dev/null || true
    cp "$desktop_dir/quotes.txt" "$rootfs/opt/anklume/host/boot/desktop/quotes.txt" 2>/dev/null || true
    cp "$desktop_dir/quotes.fr.txt" "$rootfs/opt/anklume/host/boot/desktop/quotes.fr.txt" 2>/dev/null || true

    # Keybindings reference (English + French)
    cp "$desktop_dir/KEYBINDINGS.txt" "$rootfs/opt/anklume/host/boot/desktop/KEYBINDINGS.txt" 2>/dev/null || true
    cp "$desktop_dir/KEYBINDINGS.fr.txt" "$rootfs/opt/anklume/host/boot/desktop/KEYBINDINGS.fr.txt" 2>/dev/null || true

    # KDE autostart: welcome guide on first boot
    if [ "$DESKTOP" = "all" ] || [ "$DESKTOP" = "kde" ]; then
        mkdir -p "$rootfs/$user_home/.config/autostart"
        cp "$desktop_dir/anklume-welcome.desktop" "$rootfs/$user_home/.config/autostart/anklume-welcome.desktop" 2>/dev/null || true
    fi

    # sway config
    if [ "$DESKTOP" = "all" ] || [ "$DESKTOP" = "sway" ]; then
        mkdir -p "$rootfs/$user_home/.config/sway"
        cp "$desktop_dir/sway-config" "$rootfs/$user_home/.config/sway/config"
        # Create empty domains conf for include directive
        touch "$rootfs/$user_home/.config/sway/anklume-domains.conf"
    fi

    # labwc config
    if [ "$DESKTOP" = "all" ] || [ "$DESKTOP" = "labwc" ]; then
        mkdir -p "$rootfs/$user_home/.config/labwc"
        cp "$desktop_dir/labwc-rc.xml" "$rootfs/$user_home/.config/labwc/rc.xml"
        cp "$desktop_dir/labwc-menu.xml" "$rootfs/$user_home/.config/labwc/menu.xml"
        cp "$desktop_dir/labwc-autostart" "$rootfs/$user_home/.config/labwc/autostart"
        chmod +x "$rootfs/$user_home/.config/labwc/autostart"
        cp "$desktop_dir/labwc-environment" "$rootfs/$user_home/.config/labwc/environment"
        # waybar config
        mkdir -p "$rootfs/$user_home/.config/waybar"
        cp "$desktop_dir/waybar-config.jsonc" "$rootfs/$user_home/.config/waybar/config"
        cp "$desktop_dir/waybar-style.css" "$rootfs/$user_home/.config/waybar/style.css"
    fi

    # KDE Plasma keyboard layout (Wayland ignores /etc/default/keyboard)
    if [ "$DESKTOP" = "all" ] || [ "$DESKTOP" = "kde" ]; then
        mkdir -p "$rootfs/$user_home/.config"
        cat > "$rootfs/$user_home/.config/kxkbrc" << 'KXKB'
[Layout]
DisplayNames=
LayoutList=fr
Use=true
VariantList=
KXKB
    fi

    # Fix ownership (files were created as root during build)
    chroot "$rootfs" chown -R "$LIVE_USER:$LIVE_USER" "$user_home" 2>/dev/null || true

    info "  Desktop configs installed (DESKTOP=$DESKTOP, user=$LIVE_USER)"
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
    debootstrap_opts="$debootstrap_opts --include=systemd,linux-image-$ARCH,initramfs-tools,openssh-server,curl,jq,python3,python3-pip,python3-yaml,ca-certificates,console-setup,kbd"

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

    # Ensure DNS resolution works inside chroot
    cp /etc/resolv.conf "$ROOTFS_DIR/etc/resolv.conf" 2>/dev/null || true

    # Chroot hardening: prevent services from starting + tolerate postinst failures
    # 1. policy-rc.d: blocks invoke-rc.d calls (standard Debian chroot practice)
    # 2. Fake apparmor_parser: apparmor's postinst calls it directly (not via invoke-rc.d)
    # 3. || true on apt-get: some postinst scripts (dictionaries-common exit 25) are
    #    unavoidable in chroot; dpkg --configure -a cleans up after
    # Ref: https://bugs.debian.org/921667 (apparmor in chroot)
    printf '#!/bin/sh\nexit 101\n' > "$ROOTFS_DIR/usr/sbin/policy-rc.d"
    chmod +x "$ROOTFS_DIR/usr/sbin/policy-rc.d"
    # Divert apparmor_parser so postinst gets a no-op (real binary installs alongside)
    chroot "$ROOTFS_DIR" dpkg-divert --local --rename --add /sbin/apparmor_parser 2>/dev/null || true
    printf '#!/bin/sh\nexit 0\n' > "$ROOTFS_DIR/sbin/apparmor_parser"
    chmod +x "$ROOTFS_DIR/sbin/apparmor_parser"

    # Install additional packages via chroot (all anklume runtime + dev deps)
    local packages="nftables cryptsetup btrfs-progs squashfs-tools"
    packages="$packages firmware-linux-free"
    packages="$packages ansible git make sudo nano tmux rsync"
    packages="$packages iproute2 dmidecode lsof htop file"
    # Incus: Debian Trixie ships incus in official repos
    packages="$packages incus"
    # Wayland desktop — conditional on $DESKTOP
    packages="$packages foot wl-clipboard xwayland"
    if [ "$DESKTOP" = "all" ] || [ "$DESKTOP" = "sway" ]; then
        packages="$packages sway fuzzel i3status"
    fi
    if [ "$DESKTOP" = "all" ] || [ "$DESKTOP" = "labwc" ]; then
        packages="$packages labwc waybar fuzzel"
    fi
    if [ "$DESKTOP" = "all" ] || [ "$DESKTOP" = "kde" ]; then
        packages="$packages plasma-desktop kwin-wayland dolphin"
    fi
    # Dev/lint/test tools
    packages="$packages ansible-lint yamllint shellcheck"
    packages="$packages python3-pytest python3-hypothesis python3-pexpect"
    chroot "$ROOTFS_DIR" apt-get update -qq
    # shellcheck disable=SC2086
    chroot "$ROOTFS_DIR" env DEBIAN_FRONTEND=noninteractive \
        apt-get install -y -qq $packages 2>&1 | tail -5 || true
    # Fix half-configured packages from postinst failures in chroot
    # --force-all: mark packages as configured even if postinst fails (apparmor needs
    # securityfs, dictionaries-common exit 25 — both work fine at actual boot time)
    local chroot_path="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    chroot "$ROOTFS_DIR" env DEBIAN_FRONTEND=noninteractive PATH="$chroot_path" \
        dpkg --configure -a --force-all 2>&1 | tail -5 || true
    info "  System packages installed (apt: incus, ansible, desktop=$DESKTOP, lint/test tools)"

    # Install Python packages not available in Debian system repos
    # --ignore-installed avoids conflict with Debian's system click package
    chroot "$ROOTFS_DIR" pip3 install --break-system-packages --ignore-installed \
        "typer[all]>=0.12" "fastapi>=0.115" "uvicorn>=0.32" \
        ruff behave 2>&1 | tail -5
    info "  Python pip packages installed (pip: typer, fastapi, uvicorn, ruff, behave)"

    # Install initramfs-tools hooks and boot scripts BEFORE NVIDIA/backports
    # (backports kernel install triggers update-initramfs; hooks must be in place)
    if [ -d "$PROJECT_ROOT/host/boot/initramfs-tools" ]; then
        mkdir -p "$ROOTFS_DIR/etc/initramfs-tools/hooks"
        if [ -d "$PROJECT_ROOT/host/boot/initramfs-tools/hooks" ]; then
            cp "$PROJECT_ROOT/host/boot/initramfs-tools/hooks"/* "$ROOTFS_DIR/etc/initramfs-tools/hooks/" 2>/dev/null || true
            chmod +x "$ROOTFS_DIR/etc/initramfs-tools/hooks"/* 2>/dev/null || true
        fi
        mkdir -p "$ROOTFS_DIR/etc/initramfs-tools/scripts"
        if [ -d "$PROJECT_ROOT/host/boot/initramfs-tools/scripts" ]; then
            cp "$PROJECT_ROOT/host/boot/initramfs-tools/scripts"/* "$ROOTFS_DIR/etc/initramfs-tools/scripts/" 2>/dev/null || true
            chmod +x "$ROOTFS_DIR/etc/initramfs-tools/scripts"/* 2>/dev/null || true
        fi
        info "  initramfs-tools hooks and boot scripts installed (early)"
    fi

    # Add required kernel modules for live ISO boot
    cat >> "$ROOTFS_DIR/etc/initramfs-tools/modules" << 'MODULES'
# anklume live ISO boot modules
loop
squashfs
overlay
iso9660
cdrom
sr_mod
# ATA/AHCI controllers (needed for CDROM access in QEMU and real hardware)
ata_piix
ahci
ata_generic
# Virtio modules for VM boot
virtio_blk
virtio_scsi
virtio_pci
virtio_net
MODULES
    info "  initramfs-tools modules configured (early)"

    # Install NVIDIA drivers from backports (non-free)
    # Add non-free components to existing sources (for nvidia-driver)
    sed -i 's/^deb \(.*\) trixie main$/deb \1 trixie main contrib non-free non-free-firmware/' \
        "$ROOTFS_DIR/etc/apt/sources.list" 2>/dev/null || true
    cat > "$ROOTFS_DIR/etc/apt/sources.list.d/backports.list" << NVSRC
deb http://deb.debian.org/debian trixie-backports main contrib non-free non-free-firmware
NVSRC
    chroot "$ROOTFS_DIR" apt-get update -qq
    # DKMS auto-build fails in chroot because uname -r returns the HOST kernel
    # (bind-mounted /proc). Strategy:
    # 1. Install dkms + headers first (no NVIDIA trigger)
    # 2. Install nvidia-driver (let DKMS trigger fail)
    # 3. Fix broken packages, then manually build for Debian kernel
    local deb_kernel chroot_path
    chroot_path="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    # Step 1: Install DKMS, backports kernel + headers (newer = better hw support + NVIDIA compat)
    chroot "$ROOTFS_DIR" env DEBIAN_FRONTEND=noninteractive PATH="$chroot_path" \
        apt-get install -y -qq -t trixie-backports \
        dkms linux-image-amd64 linux-headers-amd64 2>&1 | tail -5 || true
    chroot "$ROOTFS_DIR" env DEBIAN_FRONTEND=noninteractive PATH="$chroot_path" \
        dpkg --configure -a --force-all 2>&1 | tail -3 || true
    # Detect the kernel that has matching headers (build symlink present)
    deb_kernel=""
    for kdir in "$ROOTFS_DIR"/lib/modules/*/; do
        kver=$(basename "$kdir")
        if [ -e "$kdir/build" ]; then
            deb_kernel="$kver"
            break
        fi
    done
    if [ -z "$deb_kernel" ]; then
        deb_kernel=$(find "$ROOTFS_DIR/lib/modules/" -maxdepth 1 -name "*deb*" -printf '%f\n' | tail -1)
    fi
    info "  Target kernel for NVIDIA: $deb_kernel"
    # Step 2: Install nvidia-driver from backports (matches backports kernel)
    # DKMS trigger will fail (builds for host kernel via uname -r) — OK, we rebuild manually
    chroot "$ROOTFS_DIR" env DEBIAN_FRONTEND=noninteractive PATH="$chroot_path" \
        apt-get install -y -qq -t trixie-backports \
        nvidia-driver 2>&1 | tail -10 || true
    # Step 3: Fix any broken packages
    chroot "$ROOTFS_DIR" env DEBIAN_FRONTEND=noninteractive PATH="$chroot_path" \
        dpkg --configure -a 2>&1 | tail -5 || true
    # Step 4: Manually build NVIDIA DKMS module for the Debian kernel
    if [ -n "$deb_kernel" ]; then
        # Read module name and version from dkms.conf
        local dkms_conf nv_name nv_ver
        dkms_conf=$(find "$ROOTFS_DIR/usr/src/" -maxdepth 2 -name "dkms.conf" \
            -path "*/nvidia*" | head -1)
        if [ -n "$dkms_conf" ]; then
            nv_name=$(grep '^PACKAGE_NAME=' "$dkms_conf" | cut -d= -f2 | tr -d '"')
            nv_ver=$(grep '^PACKAGE_VERSION=' "$dkms_conf" | cut -d= -f2 | tr -d '"')
            info "  Building NVIDIA $nv_name/$nv_ver DKMS for kernel $deb_kernel..."
            # Remove any failed auto-build first, then rebuild for the right kernel
            chroot "$ROOTFS_DIR" env PATH="$chroot_path" \
                dkms remove -m "$nv_name" -v "$nv_ver" --all 2>&1 | tail -3 || true
            if ! chroot "$ROOTFS_DIR" env PATH="$chroot_path" \
                dkms install -m "$nv_name" -v "$nv_ver" \
                -k "$deb_kernel" --force 2>&1 | tail -10; then
                warn "  NVIDIA DKMS build failed — modules not prebuilt (DKMS will rebuild at boot)"
            fi
        else
            warn "  No NVIDIA DKMS source found — modules will not be built"
        fi
    fi
    info "  NVIDIA drivers installed from backports"

    # Configure system
    echo "anklume" > "$ROOTFS_DIR/etc/hostname"

    # Minimal fstab for live overlay — root is already mounted by initramfs
    cat > "$ROOTFS_DIR/etc/fstab" << 'FSTAB'
# anklume Live OS — root is overlay (squashfs ro + tmpfs rw)
# No entries needed; systemd auto-mounts /proc /sys /dev /run
FSTAB
    info "  Hostname and fstab configured"

    # Set root password for live system — use openssl to generate hash directly
    # (chpasswd in chroot can fail silently due to PAM config)
    local pw_hash
    pw_hash=$(openssl passwd -6 "anklume")
    sed -i "s|^root:[^:]*:|root:${pw_hash}:|" "$ROOTFS_DIR/etc/shadow"
    # Also unlock the account (remove ! prefix if present)
    sed -i 's|^root:!|root:|' "$ROOTFS_DIR/etc/shadow"
    info "  Root password set (anklume) via shadow"

    # Allow root login on serial console (remove securetty restrictions)
    rm -f "$ROOTFS_DIR/etc/securetty"
    # Disable pam_securetty for login (allows root on any terminal)
    if [ -f "$ROOTFS_DIR/etc/pam.d/login" ]; then
        sed -i 's/^auth.*pam_securetty.so/#&/' "$ROOTFS_DIR/etc/pam.d/login"
    fi
    # Enable serial console getty for QEMU testing
    chroot "$ROOTFS_DIR" systemctl enable serial-getty@ttyS0.service >/dev/null 2>&1 || true
    info "  Serial console and root login configured"

    # Configure locale and timezone
    chroot "$ROOTFS_DIR" locale-gen en_US.UTF-8 >/dev/null 2>&1 || true
    chroot "$ROOTFS_DIR" locale-gen fr_FR.UTF-8 >/dev/null 2>&1 || true
    # Default to French locale (AZERTY keyboard configured in vconsole.conf)
    mkdir -p "$ROOTFS_DIR/etc/default"
    echo "LANG=fr_FR.UTF-8" > "$ROOTFS_DIR/etc/default/locale"
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

    # Pre-install Ansible Galaxy collections (avoids needing make init on first boot)
    if [ -f "$ROOTFS_DIR/opt/anklume/requirements.yml" ]; then
        chroot "$ROOTFS_DIR" env LC_ALL=C.UTF-8 ansible-galaxy collection install \
            -r /opt/anklume/requirements.yml 2>&1 | tail -3
        info "  Ansible Galaxy collections pre-installed"
    fi

    # Create /etc/anklume marker
    mkdir -p "$ROOTFS_DIR/etc/anklume"
    echo "0" > "$ROOTFS_DIR/etc/anklume/absolute_level"
    echo "0" > "$ROOTFS_DIR/etc/anklume/relative_level"
    echo "false" > "$ROOTFS_DIR/etc/anklume/vm_nested"

    # (hooks and modules already installed before NVIDIA section above)

    # Create vconsole.conf — French AZERTY keyboard layout
    echo "KEYMAP=fr" > "$ROOTFS_DIR/etc/vconsole.conf"
    # Also configure console-setup for Debian (vconsole.conf is Arch-style)
    mkdir -p "$ROOTFS_DIR/etc/default"
    cat > "$ROOTFS_DIR/etc/default/keyboard" << 'KBD'
XKBMODEL="pc105"
XKBLAYOUT="fr"
XKBVARIANT=""
XKBOPTIONS=""
BACKSPACE="guess"
KBD
    info "  Keyboard configured (fr)"

    # Copy systemd services
    if [ -d "$PROJECT_ROOT/host/boot/systemd" ]; then
        mkdir -p "$ROOTFS_DIR/etc/systemd/system"
        cp "$PROJECT_ROOT/host/boot/systemd"/*.service "$ROOTFS_DIR/etc/systemd/system/" 2>/dev/null || true
        info "  Systemd services installed"
    fi

    # Enable anklume services in chroot
    chroot "$ROOTFS_DIR" systemctl enable anklume-first-boot.service >/dev/null 2>&1 || true
    chroot "$ROOTFS_DIR" systemctl enable anklume-data-mount.service >/dev/null 2>&1 || true
    # Mask tmp.mount — /tmp is writable via overlay, no separate tmpfs needed
    # Use manual symlink (systemctl mask may not work without running systemd)
    ln -sf /dev/null "$ROOTFS_DIR/etc/systemd/system/tmp.mount" 2>/dev/null || true
    # Disable incus-agent — not useful in live ISO (no virtiofs config channel)
    ln -sf /dev/null "$ROOTFS_DIR/etc/systemd/system/incus-agent.service" 2>/dev/null || true
    info "  anklume services enabled"

    # Create live user and desktop configs
    create_live_user "$ROOTFS_DIR"
    mkdir -p "$ROOTFS_DIR/opt/anklume/host/boot/desktop"
    install_desktop_configs "$ROOTFS_DIR"

    # Regenerate initramfs for ALL installed kernels with our hooks and modules
    # Must run after NVIDIA/backports install to include all kernels
    info "  Regenerating initramfs for all installed kernels..."
    local kver
    for kdir in "$ROOTFS_DIR"/usr/lib/modules/*/; do
        kver=$(basename "$kdir")
        [ -d "$kdir/kernel" ] || continue
        info "    Regenerating initramfs for kernel $kver"
        env -u TMPDIR chroot "$ROOTFS_DIR" env PATH="/usr/sbin:/usr/bin:/sbin:/bin" \
            update-initramfs -u -k "$kver" 2>&1 | tail -5 || warn "update-initramfs failed for $kver"
    done
    info "  Initramfs regenerated with anklume hooks"

    # Workaround: Debian Trixie's initramfs-tools uses dracut-install for
    # module copying, which can silently fail in chroot environments.
    # Verify modules are present; if not, manually inject them.
    local newest_kver initrd_path
    newest_kver=$(find "$ROOTFS_DIR/usr/lib/modules/" -maxdepth 1 -mindepth 1 -printf '%f\n' | sort -V | tail -1)
    initrd_path=$(find "$ROOTFS_DIR/boot" -name "initrd.img-$newest_kver" -type f 2>/dev/null | head -1)
    if [ -n "$initrd_path" ] && [ -n "$newest_kver" ]; then
        # Check if initramfs has any .ko files
        local has_modules
        has_modules=$(python3 -c "
import sys
with open('$initrd_path', 'rb') as f:
    data = f.read()
# Find CPIO TRAILER (end of microcode archive)
trailer = b'TRAILER!!!'
idx = data.find(trailer)
if idx < 0:
    sys.exit(1)
end = ((idx + len(trailer) + 511) // 512) * 512
# Check rest of file for .ko signature in filenames
rest = data[end:]
if b'.ko' in rest:
    print('yes')
else:
    print('no')
" 2>/dev/null)
        if [ "$has_modules" = "no" ]; then
            warn "  Initramfs has no kernel modules — injecting manually"
            local inject_dir="$WORK_DIR/initrd-inject"
            # Module names must match actual .ko filenames (e.g. isofs not iso9660)
            local inject_modules="loop squashfs overlay isofs cdrom sr_mod"
            inject_modules="$inject_modules ata_piix ahci ata_generic libata libahci"
            inject_modules="$inject_modules scsi_mod scsi_common sd_mod sg"
            inject_modules="$inject_modules virtio_blk virtio_scsi virtio_pci virtio_net virtio virtio_ring"
            inject_modules="$inject_modules net_failover failover"
            mkdir -p "$inject_dir/lib/modules/$newest_kver"
            # Copy each module and its dependencies
            local mod_file
            for mod in $inject_modules; do
                mod_file=$(find "$ROOTFS_DIR/usr/lib/modules/$newest_kver/kernel" \
                    -name "${mod}.ko*" 2>/dev/null | head -1)
                if [ -n "$mod_file" ]; then
                    local rel_path="${mod_file#"$ROOTFS_DIR/usr/lib/modules/$newest_kver/"}"
                    mkdir -p "$inject_dir/lib/modules/$newest_kver/$(dirname "$rel_path")"
                    cp "$mod_file" "$inject_dir/lib/modules/$newest_kver/$rel_path"
                fi
            done
            # Generate modules.dep for injected modules
            depmod -b "$inject_dir" "$newest_kver" 2>/dev/null || true
            # Append the modules to the initramfs (cpio concatenation)
            # Find the main archive boundary (after microcode cpio)
            python3 << INJECT_PYEOF
import subprocess, sys, struct

initrd = '$initrd_path'
inject_dir = '$inject_dir'

with open(initrd, 'rb') as f:
    data = f.read()

# Find CPIO TRAILER (end of microcode archive)
trailer = b'TRAILER!!!'
idx = data.find(trailer)
if idx < 0:
    print("ERROR: No CPIO trailer found")
    sys.exit(1)
end = ((idx + len(trailer) + 511) // 512) * 512

# Extract the main archive (compressed)
main_archive = data[end:]

# Decompress the main archive
import gzip, io, tempfile, os

# Try gzip first
try:
    main_cpio = gzip.decompress(main_archive)
except:
    print("ERROR: Cannot decompress main archive")
    sys.exit(1)

# Write decompressed cpio to temp file
with tempfile.NamedTemporaryFile(suffix='.cpio', delete=False) as tmp:
    tmp.write(main_cpio)
    tmp_cpio = tmp.name

# Append new files to the cpio
result = subprocess.run(
    ['bash', '-c', f'cd {inject_dir} && find lib -type f -o -type d | sort | cpio -o -H newc --append -F {tmp_cpio}'],
    capture_output=True, text=True
)
if result.returncode != 0:
    # Try without --append (create new cpio and concatenate)
    with tempfile.NamedTemporaryFile(suffix='.cpio', delete=False) as tmp2:
        tmp2_path = tmp2.name
    result = subprocess.run(
        ['bash', '-c', f'cd {inject_dir} && find lib -type f -o -type d | sort | cpio -o -H newc > {tmp2_path}'],
        capture_output=True, text=True
    )
    # Concatenate: original + new
    with open(tmp_cpio, 'ab') as out:
        with open(tmp2_path, 'rb') as inp:
            out.write(inp.read())
    os.unlink(tmp2_path)

# Re-compress with gzip
with open(tmp_cpio, 'rb') as f:
    cpio_data = f.read()
os.unlink(tmp_cpio)

compressed = gzip.compress(cpio_data, compresslevel=6)

# Write back: microcode + compressed main
with open(initrd, 'wb') as f:
    f.write(data[:end])
    f.write(compressed)

count = sum(1 for _ in os.scandir(f'{inject_dir}/lib/modules/{os.listdir(inject_dir + "/lib/modules")[0]}/kernel') if True)
print(f"Injected modules into initramfs ({len(compressed)} bytes compressed)")
INJECT_PYEOF
            rm -rf "$inject_dir"
        else
            info "  Initramfs has kernel modules (OK)"
        fi
    fi

    # Remove chroot-only files and restore diverted binaries before creating squashfs
    rm -f "$ROOTFS_DIR/usr/sbin/policy-rc.d"
    rm -f "$ROOTFS_DIR/sbin/apparmor_parser"
    chroot "$ROOTFS_DIR" dpkg-divert --local --rename --remove /sbin/apparmor_parser 2>/dev/null || true

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
    # NOTE: CachyOS pacstrap can't resolve some vanilla Arch packages (nvidia,
    # python-uvicorn, etc.) — those are installed via chroot pacman below.
    # Build conditional package list for desktop
    local desktop_pkgs="foot wl-clipboard xorg-xwayland"
    if [ "$DESKTOP" = "all" ] || [ "$DESKTOP" = "sway" ]; then
        desktop_pkgs="$desktop_pkgs sway fuzzel i3status"
    fi
    if [ "$DESKTOP" = "all" ] || [ "$DESKTOP" = "labwc" ]; then
        desktop_pkgs="$desktop_pkgs labwc waybar fuzzel"
    fi
    # KDE is installed via chroot pacman below (large dep tree)

    # shellcheck disable=SC2086
    pacstrap -C "$WORK_DIR/pacman-vanilla.conf" -K "$ROOTFS_DIR" \
        base linux linux-firmware linux-headers mkinitcpio \
        openssh curl jq python python-pip python-yaml file \
        nftables cryptsetup btrfs-progs squashfs-tools \
        incus ansible git make ca-certificates \
        sudo nano iproute2 systemd-resolvconf \
        dmidecode lsof htop tmux rsync \
        $desktop_pkgs

    info "  Pacstrap complete (base packages, desktop=$DESKTOP)"

    # Re-write mirrorlist (pacstrap's pacman-mirrorlist package overwrites ours)
    cat > "$ROOTFS_DIR/etc/pacman.d/mirrorlist" << 'MIRRORS'
Server = https://geo.mirror.pkgbuild.com/$repo/os/$arch
Server = https://mirror.rackspace.com/archlinux/$repo/os/$arch
Server = https://archlinux.mailtunnel.eu/$repo/os/$arch
MIRRORS
    info "  Mirrorlist restored with working mirrors"

    # Bind-mount pseudo-filesystems for chroot operations
    mount --bind /proc "$ROOTFS_DIR/proc"
    mount --bind /sys "$ROOTFS_DIR/sys"
    mount --bind /dev "$ROOTFS_DIR/dev"
    mount --bind /dev/pts "$ROOTFS_DIR/dev/pts"
    MOUNTED_PATHS+=("$ROOTFS_DIR/dev/pts" "$ROOTFS_DIR/dev" "$ROOTFS_DIR/sys" "$ROOTFS_DIR/proc")

    # Ensure DNS resolution works inside chroot
    cp /etc/resolv.conf "$ROOTFS_DIR/etc/resolv.conf" 2>/dev/null || true

    # Ensure vanilla Arch pacman.conf in rootfs (CachyOS pacstrap may copy host config)
    cat > "$ROOTFS_DIR/etc/pacman.conf" << 'PACCONF'
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

    # Install packages that CachyOS pacstrap can't resolve from vanilla repos
    # Using chroot pacman (vanilla Arch inside rootfs) to install them
    local extra_pkgs="nvidia-open-dkms nvidia-utils python-typer python-rich python-fastapi python-pytest python-hypothesis python-pexpect ansible-lint yamllint shellcheck ruff"
    if [ "$DESKTOP" = "all" ] || [ "$DESKTOP" = "kde" ]; then
        extra_pkgs="$extra_pkgs plasma-desktop dolphin"
    fi
    # shellcheck disable=SC2086
    chroot "$ROOTFS_DIR" pacman -Sy --noconfirm \
        $extra_pkgs 2>&1 | tail -10
    info "  Extra packages installed via chroot pacman (nvidia-dkms, dev tools, desktop=$DESKTOP)"

    # Install Python packages not in Arch repos
    chroot "$ROOTFS_DIR" pip install --break-system-packages \
        behave uvicorn 2>&1 | tail -3
    info "  Python pip packages installed (behave, uvicorn)"

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

    # Configure locale (default to French — AZERTY keyboard in vconsole.conf)
    sed -i 's/#en_US.UTF-8/en_US.UTF-8/' "$ROOTFS_DIR/etc/locale.gen"
    sed -i 's/#fr_FR.UTF-8/fr_FR.UTF-8/' "$ROOTFS_DIR/etc/locale.gen"
    chroot "$ROOTFS_DIR" locale-gen >/dev/null 2>&1 || true
    echo "LANG=fr_FR.UTF-8" > "$ROOTFS_DIR/etc/locale.conf"
    info "  Locale configured (fr_FR.UTF-8)"

    # Configure timezone
    ln -sf /usr/share/zoneinfo/UTC "$ROOTFS_DIR/etc/localtime"
    info "  Timezone configured"

    # Copy entire anklume framework (git repo) into rootfs
    mkdir -p "$ROOTFS_DIR/opt/anklume"
    if command -v git &>/dev/null && [ -d "$PROJECT_ROOT/.git" ]; then
        # Allow git archive from a repo owned by a different user (running as root)
        git config --global --add safe.directory "$PROJECT_ROOT" 2>/dev/null || true
        git -C "$PROJECT_ROOT" archive HEAD | tar -x -C "$ROOTFS_DIR/opt/anklume/"
    else
        for d in scripts roles roles_custom Makefile site.yml snapshot.yml \
                 ansible.cfg inventory group_vars host_vars pyproject.toml \
                 infra.yml requirements.yml; do
            [ -e "$PROJECT_ROOT/$d" ] && cp -r "$PROJECT_ROOT/$d" "$ROOTFS_DIR/opt/anklume/" 2>/dev/null || true
        done
    fi
    info "  anklume framework files copied"

    # Pre-install Ansible Galaxy collections (avoids needing make init on first boot)
    if [ -f "$ROOTFS_DIR/opt/anklume/requirements.yml" ]; then
        chroot "$ROOTFS_DIR" env LC_ALL=C.UTF-8 ansible-galaxy collection install \
            -r /opt/anklume/requirements.yml 2>&1 | tail -3
        info "  Ansible Galaxy collections pre-installed"
    fi

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

    # Create live user and desktop configs
    create_live_user "$ROOTFS_DIR"
    mkdir -p "$ROOTFS_DIR/opt/anklume/host/boot/desktop"
    install_desktop_configs "$ROOTFS_DIR"

    # Detect installed kernel version in the rootfs
    local kver
    kver=$(find "$ROOTFS_DIR/usr/lib/modules/" -maxdepth 1 -mindepth 1 -printf '%f\n' 2>/dev/null | head -1)
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
    # Unset TMPDIR: host's TMPDIR (e.g. /home/user/tmp) doesn't exist in chroot
    if [ -n "$kver" ]; then
        if ! env -u TMPDIR chroot "$ROOTFS_DIR" mkinitcpio -k "$kver" -g /boot/initramfs-linux.img 2>&1; then
            warn "mkinitcpio with custom hooks failed, trying without"
            # Restore default hooks and retry
            env -u TMPDIR chroot "$ROOTFS_DIR" mkinitcpio -k "$kver" -S anklume-verity,anklume-toram \
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
    local cache_file=""
    if [ -n "$CACHE_ROOTFS" ]; then
        mkdir -p "$CACHE_ROOTFS"
        cache_file="$CACHE_ROOTFS/rootfs-${BASE}-${DESKTOP}.tar"
    fi

    # Restore from cache if available
    if [ -n "$cache_file" ] && [ -f "$cache_file" ]; then
        info "Restoring rootfs from cache: $cache_file"
        ROOTFS_DIR="$WORK_DIR/rootfs"
        mkdir -p "$ROOTFS_DIR"
        tar -xf "$cache_file" -C "$ROOTFS_DIR"
        ok "Rootfs restored from cache ($(du -sh "$cache_file" | cut -f1))"
        return
    fi

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

    # Save to cache for next build
    if [ -n "$cache_file" ]; then
        info "Saving rootfs cache: $cache_file"
        tar -cf "$cache_file" -C "$ROOTFS_DIR" .
        ok "Rootfs cached ($(du -sh "$cache_file" | cut -f1))"
    fi
}

# ── Create squashfs ──
create_squashfs() {
    info "Creating SquashFS image..."

    local squashfs_file="$WORK_DIR/rootfs.squashfs"

    # Clean directories that should be empty in the squashfs
    # /tmp: keep the directory (mode 1777) but remove contents
    rm -rf "${ROOTFS_DIR:?}/tmp/"* 2>/dev/null || true
    chmod 1777 "$ROOTFS_DIR/tmp" 2>/dev/null || true

    # Create squashfs with zstd compression (fast, good ratio)
    # Exclude kernel virtual fs mount points (populated at runtime)
    # Keep /tmp and /run as empty dirs in the squashfs
    mksquashfs "$ROOTFS_DIR" "$squashfs_file" \
        -comp zstd -Xcompression-level 15 -b 256K \
        -no-exports -no-xattrs \
        -e proc sys dev

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
            vmlinuz=$(find "$ROOTFS_DIR/boot" -name "vmlinuz-*" -type f | sort -V | tail -1)
            initrd=$(find "$ROOTFS_DIR/boot" -name "initrd.img-*" -type f | sort -V | tail -1)
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
            # Use the newest kernel (sort by version, take last)
            vmlinuz=$(find "$ROOTFS_DIR/boot" -name "vmlinuz-*" -type f 2>/dev/null | sort -V | tail -1)
            initrd=$(find "$ROOTFS_DIR/boot" -name "initrd.img-*" -type f 2>/dev/null | sort -V | tail -1)
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
        info "  Kernel and initramfs staged ($(basename "$vmlinuz"))"
    else
        err "Could not find kernel ($vmlinuz) or initramfs ($initrd)"
        exit 1
    fi

    # Create GRUB config from template, substituting placeholders
    local grub_template="$PROJECT_ROOT/host/boot/grub/grub.cfg"
    # Capitalize distro name for GRUB menu (debian → Debian, arch → Arch)
    local base_label
    base_label="$(echo "${BASE:0:1}" | tr '[:lower:]' '[:upper:]')${BASE:1}"
    if [ -f "$grub_template" ]; then
        sed -e "s/VERITY_HASH_PLACEHOLDER/$VERITY_HASH/g" \
            -e "s/BASE_PLACEHOLDER/$base_label/g" \
            "$grub_template" > "$staging/boot/grub/grub.cfg"
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
insmod keylayouts
insmod at_keyboard

set timeout=5
set default=0

search --no-floppy --label ANKLUME-LIVE --set=root

terminal_input at_keyboard console
keymap /boot/grub/fr.gkb

menuentry "anklume Live OS — $base_label (KDE Plasma + GPU)" {
    linux /boot/vmlinuz ro boot=anklume anklume.boot_mode=iso anklume.slot=A anklume.toram=1 anklume.desktop=kde anklume.verity_hash=$VERITY_HASH console=tty0 console=ttyS0,115200n8
    initrd /boot/initrd.img
}
menuentry "anklume Live OS — $base_label (KDE Plasma)" {
    linux /boot/vmlinuz ro boot=anklume anklume.boot_mode=iso anklume.slot=A anklume.toram=1 anklume.desktop=kde anklume.verity_hash=$VERITY_HASH modprobe.blacklist=nvidia,nvidia_drm,nvidia_modeset,nvidia_uvm console=tty0 console=ttyS0,115200n8
    initrd /boot/initrd.img
}
menuentry "anklume Live OS — $base_label (Console + GPU)" {
    linux /boot/vmlinuz ro boot=anklume anklume.boot_mode=iso anklume.slot=A anklume.toram=1 anklume.verity_hash=$VERITY_HASH console=tty0 console=ttyS0,115200n8
    initrd /boot/initrd.img
}
menuentry "anklume Live OS — $base_label (Console)" {
    linux /boot/vmlinuz ro boot=anklume anklume.boot_mode=iso anklume.slot=A anklume.toram=1 anklume.verity_hash=$VERITY_HASH modprobe.blacklist=nvidia,nvidia_drm,nvidia_modeset,nvidia_uvm console=tty0 console=ttyS0,115200n8
    initrd /boot/initrd.img
}
submenu "More Desktops (sway, labwc)" {
    menuentry "anklume Live OS — $base_label (sway Desktop + GPU)" {
        linux /boot/vmlinuz ro boot=anklume anklume.boot_mode=iso anklume.slot=A anklume.toram=1 anklume.desktop=sway anklume.verity_hash=$VERITY_HASH console=tty0 console=ttyS0,115200n8
        initrd /boot/initrd.img
    }
    menuentry "anklume Live OS — $base_label (sway Desktop)" {
        linux /boot/vmlinuz ro boot=anklume anklume.boot_mode=iso anklume.slot=A anklume.toram=1 anklume.desktop=sway anklume.verity_hash=$VERITY_HASH modprobe.blacklist=nvidia,nvidia_drm,nvidia_modeset,nvidia_uvm console=tty0 console=ttyS0,115200n8
        initrd /boot/initrd.img
    }
    menuentry "anklume Live OS — $base_label (labwc Desktop + GPU)" {
        linux /boot/vmlinuz ro boot=anklume anklume.boot_mode=iso anklume.slot=A anklume.toram=1 anklume.desktop=labwc anklume.verity_hash=$VERITY_HASH console=tty0 console=ttyS0,115200n8
        initrd /boot/initrd.img
    }
    menuentry "anklume Live OS — $base_label (labwc Desktop)" {
        linux /boot/vmlinuz ro boot=anklume anklume.boot_mode=iso anklume.slot=A anklume.toram=1 anklume.desktop=labwc anklume.verity_hash=$VERITY_HASH modprobe.blacklist=nvidia,nvidia_drm,nvidia_modeset,nvidia_uvm console=tty0 console=ttyS0,115200n8
        initrd /boot/initrd.img
    }
}
submenu "Advanced (direct boot from media)" {
    menuentry "anklume Live OS — $base_label (KDE Plasma + GPU)" {
        linux /boot/vmlinuz ro boot=anklume anklume.boot_mode=iso anklume.slot=A anklume.desktop=kde anklume.verity_hash=$VERITY_HASH console=tty0 console=ttyS0,115200n8
        initrd /boot/initrd.img
    }
    menuentry "anklume Live OS — $base_label (KDE Plasma)" {
        linux /boot/vmlinuz ro boot=anklume anklume.boot_mode=iso anklume.slot=A anklume.desktop=kde anklume.verity_hash=$VERITY_HASH modprobe.blacklist=nvidia,nvidia_drm,nvidia_modeset,nvidia_uvm console=tty0 console=ttyS0,115200n8
        initrd /boot/initrd.img
    }
    menuentry "anklume Live OS — $base_label (sway Desktop + GPU)" {
        linux /boot/vmlinuz ro boot=anklume anklume.boot_mode=iso anklume.slot=A anklume.desktop=sway anklume.verity_hash=$VERITY_HASH console=tty0 console=ttyS0,115200n8
        initrd /boot/initrd.img
    }
    menuentry "anklume Live OS — $base_label (sway Desktop)" {
        linux /boot/vmlinuz ro boot=anklume anklume.boot_mode=iso anklume.slot=A anklume.desktop=sway anklume.verity_hash=$VERITY_HASH modprobe.blacklist=nvidia,nvidia_drm,nvidia_modeset,nvidia_uvm console=tty0 console=ttyS0,115200n8
        initrd /boot/initrd.img
    }
    menuentry "anklume Live OS — $base_label (labwc Desktop + GPU)" {
        linux /boot/vmlinuz ro boot=anklume anklume.boot_mode=iso anklume.slot=A anklume.desktop=labwc anklume.verity_hash=$VERITY_HASH console=tty0 console=ttyS0,115200n8
        initrd /boot/initrd.img
    }
    menuentry "anklume Live OS — $base_label (labwc Desktop)" {
        linux /boot/vmlinuz ro boot=anklume anklume.boot_mode=iso anklume.slot=A anklume.desktop=labwc anklume.verity_hash=$VERITY_HASH modprobe.blacklist=nvidia,nvidia_drm,nvidia_modeset,nvidia_uvm console=tty0 console=ttyS0,115200n8
        initrd /boot/initrd.img
    }
    menuentry "anklume Live OS — $base_label (Console + GPU)" {
        linux /boot/vmlinuz ro boot=anklume anklume.boot_mode=iso anklume.slot=A anklume.verity_hash=$VERITY_HASH console=tty0 console=ttyS0,115200n8
        initrd /boot/initrd.img
    }
    menuentry "anklume Live OS — $base_label (Console)" {
        linux /boot/vmlinuz ro boot=anklume anklume.boot_mode=iso anklume.slot=A anklume.verity_hash=$VERITY_HASH modprobe.blacklist=nvidia,nvidia_drm,nvidia_modeset,nvidia_uvm console=tty0 console=ttyS0,115200n8
        initrd /boot/initrd.img
    }
}
GRUBCFG
    fi
    info "  GRUB config created"

    # Generate AZERTY keyboard layout for GRUB
    if command -v grub-kbdcomp >/dev/null 2>&1 && command -v ckbcomp >/dev/null 2>&1; then
        grub-kbdcomp -o "$staging/boot/grub/fr.gkb" fr 2>/dev/null || true
        if [ -s "$staging/boot/grub/fr.gkb" ]; then
            info "  GRUB AZERTY keyboard layout generated"
        else
            warn "grub-kbdcomp produced empty output — GRUB will use QWERTY"
            # Remove keyboard lines from grub.cfg to avoid boot error
            sed -i '/terminal_input\|keymap\|keylayouts\|at_keyboard/d' "$staging/boot/grub/grub.cfg"
        fi
    else
        warn "grub-kbdcomp or ckbcomp not found — GRUB will use QWERTY"
        sed -i '/terminal_input\|keymap\|keylayouts\|at_keyboard/d' "$staging/boot/grub/grub.cfg"
    fi

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
        local standalone_args=(
            --format=x86_64-efi
            --output="$staging/EFI/BOOT/BOOTX64.EFI"
            --locales=""
            --fonts=""
            --install-modules="normal search search_fs_uuid search_fs_file search_label iso9660 part_gpt part_msdos fat ext2 linux gzio keylayouts at_keyboard"
            "boot/grub/grub.cfg=$staging/boot/grub/grub.cfg"
        )
        # Embed keyboard layout if generated
        if [ -s "$staging/boot/grub/fr.gkb" ]; then
            standalone_args+=("boot/grub/fr.gkb=$staging/boot/grub/fr.gkb")
        fi
        grub-mkstandalone "${standalone_args[@]}" \
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
    echo "Desktop:         $DESKTOP"
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
            --desktop)    DESKTOP="$2"; shift 2 ;;
            --mirror)     MIRROR="$2"; shift 2 ;;
            --no-verity)  NO_VERITY=true; shift ;;
            --cache-rootfs) CACHE_ROOTFS="$2"; shift 2 ;;
            --help|-h)    usage ;;
            *)            err "Unknown option: $1"; usage ;;
        esac
    done

    # Validate format
    case "$FORMAT" in
        iso|raw) ;;
        *) err "Invalid format: $FORMAT (must be iso or raw)"; exit 1 ;;
    esac

    # Validate desktop
    case "$DESKTOP" in
        all|sway|labwc|kde|minimal) ;;
        *) err "Invalid desktop: $DESKTOP (must be all, sway, labwc, kde, or minimal)"; exit 1 ;;
    esac

    # Set default output name based on format
    if [ -z "$OUTPUT" ]; then
        OUTPUT="anklume-live.$FORMAT"
        if [ "$FORMAT" = "raw" ]; then
            OUTPUT="anklume-live.img"
        fi
    fi

    echo "=== anklume Live OS Image Builder ==="
    info "Format: $FORMAT, Desktop: $DESKTOP"

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
