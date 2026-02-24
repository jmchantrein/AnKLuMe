# Phase 31: Live OS with Encrypted Persistent Storage

## Introduction

anklume Live OS enables compartmentalized infrastructure to run from a USB boot media with encrypted persistent data on a separate disk. Boot into a live OS, run containers immediately, and maintain state across reboots.

**Key features:**
- Boot from USB (no installation required)
- Encrypted data disk (LUKS + ZFS/BTRFS)
- A/B slot updates (atomic, safe updates with automatic rollback)
- Three-layer encryption model for maximum security
- Persistent Incus storage across reboots

## Architecture Overview

### Boot Media Layout (GPT Partitioning)

```
┌─────────────────────────────────────┐
│ EFI System Partition (512 MB)       │ ANKLUME-EFI
├─────────────────────────────────────┤
│ OS Slot A (1536 MB, squashfs)       │ ANKLUME-OS-A
├─────────────────────────────────────┤
│ OS Slot B (1536 MB, squashfs)       │ ANKLUME-OS-B
├─────────────────────────────────────┤
│ Persistent Boot Config (100 MB)     │ ANKLUME-PERSIST
└─────────────────────────────────────┘
```

- **ANKLUME-EFI**: systemd-boot bootloader and kernel/initramfs
- **ANKLUME-OSA/OSB**: Two read-only OS squashfs images with dm-verity
- **ANKLUME-PERSIST**: Unencrypted persistent partition (stores boot state, ZFS pool metadata)

### Data Disk Layout (Separate NVMe/SSD)

```
┌─────────────────────────────────────┐
│ LUKS Encrypted Container            │ (passphrase protected)
├─────────────────────────────────────┤
│ ZFS/BTRFS Filesystem                │
├─────────────────────────────────────┤
│ • Data volumes                      │
│ • Incus storage pool                │
│ • Container rootfs and layers       │
└─────────────────────────────────────┘
```

## Three-Layer Encryption Model

### Layer 1: OS Integrity (dm-verity)

- Read-only squashfs OS partition with cryptographic integrity verification
- Detected tampering prevents boot
- Hash tree stored in ANKLUME-PERSIST
- Veritysetup validates on each boot

**What it protects:** OS kernel, systemd, essential binaries against tampering

**Overhead:** ~2% performance (hash verification), ~5MB metadata per OS slot

### Layer 2: Data at Rest (LUKS)

- Full-disk encryption of data disk using LUKS2
- Passphrase or keyfile protected (configurable during first-boot)
- Opens to `/dev/mapper/anklume-data-<pool-name>`
- ZFS/BTRFS mounted on top

**What it protects:** All user data, Incus container filesystems, persistent storage

**Overhead:** ~3-5% performance (encryption/decryption), passphrase required to mount

### Layer 3: Memory Encryption (Optional)

- Kernel parameter: `anklume.ram_crypt=1` (requires AMD SME or Intel TME)
- Encrypts all RAM contents while powered on
- Automatic key destruction on shutdown
- Prevents cold-boot attacks on running system

**What it protects:** Container processes, decrypted data in RAM

**Requirements:** CPU with SME (AMD) or TME (Intel), firmware support enabled

## Building an Image

### Create a Live OS Image

```bash
cd /path/to/anklume-repo

# Build default image (Debian 13, amd64, 3GB)
make build-image OUT=anklume-live.img

# Build with custom base OS
make build-image OUT=custom.img BASE=ubuntu ARCH=arm64

# Output: /path/to/custom.img (ready to write to USB)
```

### Flash to USB

```bash
# Identify USB device (e.g., /dev/sdX)
lsblk

# Write image (WARNING: destructive)
sudo dd if=anklume-live.img of=/dev/sdX bs=1M status=progress
sudo sync
```

### Build Process

1. **Debootstrap** OS into temporary rootfs (Debian packages, systemd, Incus)
2. **Configure** kernel, initramfs hooks, systemd services, systemd-boot
3. **Mksquashfs** rootfs into read-only compressed OS image (~600MB → ~200MB)
4. **Veritysetup** generate integrity hashes for dm-verity
5. **Sgdisk** create GPT partitions on USB device
6. **Write** EFI, kernel, initramfs, OS slots, persistent partition

**Image size:** ~1.2 GB on USB (includes boot loader, 2x OS slots, persist partition)

**Build time:** ~10-15 minutes (depends on internet speed, CPU)

## First Boot Wizard

First boot detects if the system has never been initialized:

### Automatic First-Boot Steps

1. **Disk Detection**
   - Lists available block devices
   - Prompts user to select data disk (e.g., `/dev/nvme0n1`)
   - Confirms is NOT the USB boot disk

2. **LUKS Setup**
   - Prompts for passphrase (or key file path)
   - Creates LUKS2 container on selected disk
   - Takes ~30 seconds

3. **Pool Creation**
   - Prompts for ZFS pool name or BTRFS mount point
   - Creates pool on decrypted device
   - Configures compression (zstd for ZFS)

4. **Incus Storage Pool**
   - Auto-configures Incus to use ZFS/BTRFS pool
   - Sets up container storage, image caching
   - Enables snapshots and cloning

5. **Persistence Flag**
   - Writes `/mnt/anklume-persist/pool.conf` (pool metadata)
   - Future boots skip first-boot and auto-mount data

### Manual First-Boot (if needed)

```bash
# If first-boot service fails, run manually:
sudo /opt/anklume/scripts/first-boot.sh --interactive

# Or with defaults:
sudo /opt/anklume/scripts/first-boot.sh \
  --disk /dev/nvme0n1 \
  --pool-name datapool \
  --passphrase-file ~/.anklume-passphrase
```

## A/B Update Mechanism

Live OS uses atomic A/B updates to ensure safe OS upgrades with automatic rollback.

### Update Process

```bash
# Download and apply update
make live-update URL=https://example.com/anklume-live-v1.2.img

# Behind the scenes:
# 1. Detects active slot (A or B)
# 2. Downloads new image to inactive slot
# 3. Verifies dm-verity hash
# 4. Resets boot counter to 0
# 5. Reboots into new slot
# 6. If successful, keep new slot
```

### Manual Update

```bash
# Check current status
make live-status
# Output: Active slot: A, Boot count: 0, Data pool: datapool

# Trigger manual update (requires USB write access)
sudo scripts/live-update.sh \
  --url https://cdn.example.com/anklume-v1.2.img \
  --verify-hash 6a3b2c...

# Reboot to apply
sudo reboot
```

## Rollback

Live OS automatically rolls back if boot fails 3 consecutive times.

### Boot Counter Mechanism

- **Boot count = 0**: Fresh start
- **Boot count increments** on each failed boot (systemd watchdog or manual)
- **Boot count reaches 3**: Kernel switches to previous A/B slot
- **Boot count resets** to 0 on successful boot

### Manual Rollback

```bash
# Check current state
sudo scripts/live-os-lib.sh status

# Force rollback to previous slot (requires persist mount)
sudo scripts/live-os-lib.sh set_active_slot B
sudo reboot
```

### Rollback Recovery

If system is unbootable after update:

1. Boot from live USB (or same USB, select older kernel version if available)
2. Mount persist partition: `mount /dev/disk/by-label/ANKLUME-PERSIST /mnt/persist`
3. Check AB state: `cat /mnt/persist/ab-state`
4. Force previous slot: `echo A > /mnt/persist/ab-state` (if current is B)
5. Reboot

## toram Mode

toram mode copies the entire OS into RAM, allowing USB ejection after boot.

### Enable toram

Add kernel parameter: `anklume.toram=1`

- Via bootloader (systemd-boot): Edit `/boot/loader/entries/default.conf`, add to options
- Via GRUB: Edit `/etc/default/grub`, add to `GRUB_CMDLINE_LINUX`
- Via kernel command line (live USB): Add at boot prompt

### Requirements

- RAM ≥ OS_SIZE_MB (typically 2-3 GB)
- 30-60 seconds longer boot time (initial copy)

### Benefits

- USB can be safely ejected after boot
- Faster reads (RAM vs USB 3.0)
- USB reusable for other systems

### Overhead

- RAM usage: ~1.5-2 GB (compressed OS decompresses to RAM)
- Boot time: +30-60 seconds (one-time copy)

## Security Considerations

### LUKS Passphrase Security

- Passphrase never stored on disk (except LUKS header, which is salted/iterated)
- User enters passphrase once per boot (or automated via key file)
- Weak passphrases (< 12 characters) vulnerable to dictionary attack

**Recommendation:** Use 16+ character passphrase or dedicated key file

### dm-verity Tampering Detection

- Any bit flip in OS partition detected
- Boot fails with error message
- Prevents privilege escalation via OS kernel modification

### Boot Loader Chain of Trust

- UEFI firmware verifies systemd-boot signature (if Secure Boot enabled)
- systemd-boot verifies kernel and initramfs
- Initramfs verifies OS squashfs via dm-verity

**Recommendation:** Enable Secure Boot and add `/boot/EFI/Boot/bootx64.efi` to whitelist

### Incus Isolation

- Namespace-based container isolation (not hypervisor-level)
- Requires nftables rules for network isolation (see `make nftables`)
- Trust domain separation ensures untrusted containers can't access admin filesystem

## Arch Linux Support

anklume Live OS can be built with Arch Linux as the base OS, providing a lightweight alternative to Debian.

### Build with Arch

```bash
# Build Arch-based Live OS image
make build-image OUT=anklume-arch.img BASE=arch

# Specify architecture
make build-image OUT=anklume-arch-arm64.img BASE=arch ARCH=arm64
```

### When to Choose Arch vs Debian

**Arch is recommended for machines with recent GPUs** (NVIDIA 40xx/50xx, AMD RDNA 3/4, Intel Arc).
Arch ships the latest Mesa, `linux-firmware`, and kernel drivers out of the box, so recent
hardware is supported immediately. Debian Stable freezes driver versions at release time,
which means GPUs released after the freeze often lack proper support (no Wayland acceleration,
missing firmware blobs, fallback to software rendering).

This also matters for **local AI inference**: recent GPUs with CUDA or ROCm support
can run large language models (7B–70B parameters) via Ollama or llama.cpp. Without
up-to-date drivers, GPU acceleration is unavailable and inference falls back to CPU.
Note that small models (1B–3B parameters) can run on **CPU only** with acceptable
performance on recent processors (Intel 12th gen+, AMD Zen 4+) thanks to AVX-512
and AMX instruction sets — but the inference libraries (llama.cpp, GGML) must be
compiled against recent toolchains to leverage these instructions, which Arch
provides naturally while Debian Stable may ship older versions.

For servers or headless machines where GPU support and local AI are irrelevant,
Debian Stable remains the safer choice thanks to its predictable update cycle
and longer security support.

### Key Differences vs Debian

| Aspect | Arch | Debian |
|--------|------|--------|
| **Bootstrap** | `pacstrap` | `debootstrap` |
| **Initramfs** | `mkinitcpio` | `initramfs-tools` |
| **Release cycle** | Rolling release | Stable snapshots |
| **Package sync** | Always latest | Fixed versions |
| **GPU drivers** | Latest (Mesa, firmware, kernel) | Frozen at release |

### Rolling Release Implications

- Arch updates frequently (new kernel versions, glibc updates)
- Live OS inherits base OS state at build time
- Recommended: Rebuild monthly to capture latest patches

### Recommended Filesystem

BTRFS is the recommended default for Arch-based images:

- BTRFS is stable in the mainline kernel, no external modules needed
- ZFS requires the `archzfs` repo and `zfs-dkms` package
- ZFS may break on kernel updates (rolling release vs DKMS compatibility)

### Host Prerequisites

To build Arch-based images on CachyOS/Arch hosts:

```bash
sudo pacman -S arch-install-scripts  # provides pacstrap
sudo pacman -S btrfs-progs           # for BTRFS pool creation
```

## Ventoy Compatibility

anklume Live OS images (both Arch and Debian) are fully compatible with [Ventoy](https://www.ventoy.net/), a USB boot manager that simplifies multiboot setups.

### Multiboot USB

Ventoy allows multiple ISO/IMG files on a single USB device:

```
USB Device (Ventoy):
├── anklume-live-debian.img
├── anklume-live-arch.img
└── other-distro.iso
```

- Boot menu appears on startup; select desired OS
- No need to rewrite USB for each image

### Data Disk Independence

The encrypted data disk is **completely independent** of boot media:

- Can boot Arch image one day, Debian the next, using the same data disk
- `mount-data.sh` and `umount-data.sh` are distro-agnostic
- LUKS passphrase remains valid across boot method changes
- ZFS/BTRFS pools automatically recognized on next boot

### Copy-to-RAM Default

By default, `anklume.toram=1` is active in bootloader configuration:

- OS copied to RAM during boot (~30-60 seconds)
- USB can be safely ejected after boot completes
- Requires 2-3 GB free RAM

## Checksums

anklume Live OS builds automatically generate SHA256 checksums.

### Automatic Generation

During build, a `.sha256` checksum file is created alongside the image:

```
Build output:
├── anklume-live.img          (image file)
└── anklume-live.img.sha256   (checksum file)
```

### Verify Image Integrity

```bash
# Verify against checksum file
sha256sum -c anklume-live.img.sha256
# Output: anklume-live.img: OK

# Or manually compute and compare
sha256sum anklume-live.img
```

## FAQ / Troubleshooting

### Q: Boot fails after update

**A:** Boot counter has reached 3, system rolled back. Check logs:
```bash
# Mount old USB boot media
mount /dev/sdX1 /tmp/boot-old

# Check boot counter
cat /mnt/persist/boot-count

# Check dmesg for errors
dmesg | tail -50
```

**Solution:** Reset boot counter and retry:
```bash
echo 0 | sudo tee /mnt/persist/boot-count
sudo reboot
```

### Q: LUKS unlock fails with "No key available"

**A:** Passphrase incorrect or key file missing. Options:

1. Reboot and try passphrase again
2. Use different key file: `sudo cryptsetup luksOpen /dev/nvme0n1 anklume-data --key-file ~/.backup-key`
3. Add recovery key from backup (if available)

### Q: Data mount fails: "zpool import failed"

**A:** ZFS pool not found on decrypted device. Check:

```bash
# Verify LUKS device is open
ls -la /dev/mapper/anklume-*

# List pools on device
sudo zpool import -d /dev/mapper/anklume-data

# If found, import manually
sudo zpool import -d /dev/mapper/anklume-data pool-name

# Verify mount
mount | grep anklume
```

### Q: toram mode ejects USB too early

**A:** Kernel is still reading from USB. Wait for message:
```
[INFO] Copying squashfs to RAM...
[OK] OS copied to RAM, USB can be safely removed
```

**Do not eject USB during copy phase.**

### Q: System boots into degraded mode (single-user)

**A:** One or more services failed. Check:

```bash
sudo systemctl status anklume-data-mount.service
sudo systemctl status anklume-first-boot.service
sudo journalctl -u anklume-data-mount -n 50
```

Common causes:
- Data disk not connected
- LUKS passphrase incorrect
- Pool config missing (`/mnt/anklume-persist/pool.conf`)

### Q: How do I backup the persistent config?

**A:** Backup `/mnt/anklume-persist/`:

```bash
sudo tar czf anklume-backup.tar.gz /mnt/anklume-persist/
sudo cp anklume-backup.tar.gz ~/backups/
```

Restore on new USB:
```bash
# After booting new USB, mount old persist
mount /dev/disk/by-label/ANKLUME-PERSIST /tmp/old-persist

# Restore config
sudo tar xzf anklume-backup.tar.gz -C /
```

### Q: Can I run without LUKS encryption?

**A:** Not recommended, but technically possible:

```bash
# During first-boot, select "none" for encryption
# Data disk will use unencrypted ZFS/BTRFS

# Security implications:
# - Cold-boot attacks possible
# - Data disk readable by anyone with physical access
# - Only use in trusted environments
```

## Getting Help

- Check logs: `sudo journalctl -b` (current boot)
- Verify services: `systemctl status | grep anklume`
- Test pool: `zpool status` or `btrfs filesystem show`
- Manual operations: Run scripts with `--help` flag

```bash
/opt/anklume/scripts/first-boot.sh --help
/opt/anklume/scripts/live-update.sh --help
/opt/anklume/scripts/mount-data.sh --help
```
