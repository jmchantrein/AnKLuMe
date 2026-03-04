#!/usr/bin/env bash
# test-iso-contents.sh — L2 tests: mount ISO squashfs and verify real contents
#
# Usage: test-iso-contents.sh <iso-path> [test-name|all]
#
# These tests mount the actual ISO's squashfs filesystem and check
# that binaries, modules, and configurations are correct.
# Requires: root (for mount), an ISO file.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=shell-lib.sh
source "$SCRIPT_DIR/shell-lib.sh"

ISO_PATH="${1:-}"
TEST_NAME="${2:-all}"
PASS_COUNT=0
FAIL_COUNT=0
MNT_ISO=""
MNT_SQUASH=""

# ── Setup / Teardown ─────────────────────────────────────────

setup_mounts() {
    if [ -z "$ISO_PATH" ] || [ ! -f "$ISO_PATH" ]; then
        err "ISO file not found: $ISO_PATH"
        exit 2
    fi

    MNT_ISO=$(mktemp -d /tmp/test-iso-XXXXXX)
    MNT_SQUASH=$(mktemp -d /tmp/test-squash-XXXXXX)

    mount -o loop,ro "$ISO_PATH" "$MNT_ISO" 2>/dev/null || {
        err "Failed to mount ISO"
        exit 2
    }

    if [ ! -f "$MNT_ISO/live/rootfs.squashfs" ]; then
        err "No squashfs found in ISO"
        umount "$MNT_ISO" 2>/dev/null || true
        rmdir "$MNT_ISO" "$MNT_SQUASH" 2>/dev/null || true
        exit 2
    fi

    mount -t squashfs -o ro,loop "$MNT_ISO/live/rootfs.squashfs" "$MNT_SQUASH" 2>/dev/null || {
        err "Failed to mount squashfs"
        umount "$MNT_ISO" 2>/dev/null || true
        rmdir "$MNT_ISO" "$MNT_SQUASH" 2>/dev/null || true
        exit 2
    }
}

teardown_mounts() {
    umount "$MNT_SQUASH" 2>/dev/null || true
    umount "$MNT_ISO" 2>/dev/null || true
    rmdir "$MNT_SQUASH" "$MNT_ISO" 2>/dev/null || true
}

trap teardown_mounts EXIT

pass() {
    echo "PASS: $*"
    ((PASS_COUNT++)) || true
}

fail() {
    echo "FAIL: $*"
    ((FAIL_COUNT++)) || true
}

# ── Individual tests ─────────────────────────────────────────

test_sddm_absent() {
    # SDDM binary must NOT exist in the squashfs
    if [ -f "$MNT_SQUASH/usr/bin/sddm" ]; then
        fail "SDDM binary present at /usr/bin/sddm"
        return
    fi
    # SDDM service must be masked (symlink to /dev/null)
    if [ -L "$MNT_SQUASH/etc/systemd/system/sddm.service" ]; then
        local target
        target=$(readlink "$MNT_SQUASH/etc/systemd/system/sddm.service")
        if [ "$target" = "/dev/null" ]; then
            pass "SDDM absent and service masked"
            return
        fi
    fi
    # No binary AND no mask — check if package is not installed at all
    if ! chroot "$MNT_SQUASH" dpkg -l sddm 2>/dev/null | grep -q '^ii'; then
        pass "SDDM not installed"
        return
    fi
    fail "SDDM state unclear"
}

test_zfs_module() {
    # ZFS kernel module must exist for at least one installed kernel
    local found=false
    for kdir in "$MNT_SQUASH"/usr/lib/modules/*/; do
        local kver
        kver=$(basename "$kdir")
        if find "$kdir" -name "zfs.ko*" 2>/dev/null | grep -q .; then
            found=true
            pass "ZFS module present for kernel $kver"
            break
        fi
    done
    if ! $found; then
        fail "ZFS module not found in any kernel"
        echo "  Available kernels:"
        ls "$MNT_SQUASH/usr/lib/modules/" 2>/dev/null
    fi
}

test_zfs_tools() {
    if [ -x "$MNT_SQUASH/usr/sbin/zpool" ] && [ -x "$MNT_SQUASH/usr/sbin/zfs" ]; then
        pass "ZFS userspace tools present (zpool, zfs)"
    else
        fail "ZFS userspace tools missing"
    fi
}

test_btrfs_tools() {
    if [ -x "$MNT_SQUASH/usr/sbin/mkfs.btrfs" ]; then
        pass "BTRFS tools present (mkfs.btrfs)"
    else
        fail "BTRFS tools missing"
    fi
}

test_incus_binary() {
    if [ -x "$MNT_SQUASH/usr/bin/incus" ]; then
        pass "Incus binary present"
    else
        fail "Incus binary missing"
    fi
}

test_incus_service_enabled() {
    # Use -L (symlink check) not -e (follows symlink to host, fails)
    if [ -L "$MNT_SQUASH/etc/systemd/system/multi-user.target.wants/incus-startup.service" ] || \
       [ -L "$MNT_SQUASH/etc/systemd/system/multi-user.target.wants/incus.service" ]; then
        pass "Incus service enabled"
    else
        fail "Incus service not enabled"
    fi
}

test_user_groups() {
    # The live user must be in incus-admin group
    if grep -q "^incus-admin:.*:.*anklume" "$MNT_SQUASH/etc/group" 2>/dev/null; then
        pass "User 'anklume' in incus-admin group"
    else
        fail "User 'anklume' NOT in incus-admin group"
        echo "  incus-admin line: $(grep incus-admin "$MNT_SQUASH/etc/group" 2>/dev/null)"
        echo "  User groups: $(grep anklume "$MNT_SQUASH/etc/group" 2>/dev/null | head -5)"
    fi
}

test_user_adm_group() {
    if grep -q "^adm:.*anklume" "$MNT_SQUASH/etc/group" 2>/dev/null; then
        pass "User 'anklume' in adm group (journalctl access)"
    else
        fail "User 'anklume' NOT in adm group"
    fi
}

test_apparmor_parser() {
    if [ -x "$MNT_SQUASH/usr/sbin/apparmor_parser" ]; then
        pass "apparmor_parser present"
    else
        fail "apparmor_parser missing (broken diversion restore)"
    fi
}

test_start_script() {
    if [ -x "$MNT_SQUASH/opt/anklume/scripts/start.sh" ]; then
        pass "start.sh present and executable"
    else
        fail "start.sh missing or not executable"
    fi
}

test_doctor_script() {
    if [ -f "$MNT_SQUASH/opt/anklume/scripts/doctor-checks.sh" ]; then
        pass "doctor-checks.sh present"
    else
        fail "doctor-checks.sh missing"
    fi
}

test_anklume_cli() {
    if [ -x "$MNT_SQUASH/usr/local/bin/anklume" ]; then
        pass "anklume CLI present"
    else
        fail "anklume CLI missing"
    fi
}

test_aa_teardown_service() {
    local svc="$MNT_SQUASH/etc/systemd/system/anklume-aa-teardown.service"
    if [ -f "$svc" ]; then
        # Must run before incus
        if grep -q "Before=incus.service" "$svc"; then
            pass "aa-teardown service present and runs before Incus"
        else
            fail "aa-teardown service missing Before=incus.service"
        fi
    else
        fail "anklume-aa-teardown.service missing"
    fi
}

test_start_service() {
    local svc="$MNT_SQUASH/etc/systemd/system/anklume-start.service"
    if [ ! -f "$svc" ]; then
        fail "anklume-start.service missing"
        return
    fi
    # Must use kernel cmdline condition (not sddm path)
    if grep -q "ConditionKernelCommandLine=boot=anklume" "$svc"; then
        pass "start service uses kernel cmdline condition"
    else
        fail "start service missing kernel cmdline condition"
    fi
    # Must NOT condition on /usr/bin/sddm
    if grep -q "ConditionPathExists=!/usr/bin/sddm" "$svc"; then
        fail "start service still conditions on /usr/bin/sddm"
    fi
}

test_no_display_manager_autostart() {
    local has_dm=false
    for dm in sddm gdm3 lightdm; do
        local link="$MNT_SQUASH/etc/systemd/system/display-manager.service"
        if [ -L "$link" ] && readlink "$link" | grep -q "$dm"; then
            has_dm=true
            fail "Display manager $dm is the default display-manager.service"
        fi
        # Check multi-user.target.wants
        if [ -e "$MNT_SQUASH/etc/systemd/system/multi-user.target.wants/${dm}.service" ]; then
            has_dm=true
            fail "Display manager $dm enabled in multi-user.target.wants"
        fi
    done
    if ! $has_dm; then
        pass "No display manager auto-starts"
    fi
}

test_boot_files() {
    local missing=false
    if [ ! -f "$MNT_ISO/boot/vmlinuz" ]; then
        fail "vmlinuz missing from ISO /boot/"
        missing=true
    fi
    if [ ! -f "$MNT_ISO/boot/initrd.img" ]; then
        fail "initrd.img missing from ISO /boot/"
        missing=true
    fi
    if ! $missing; then
        pass "Boot files present (vmlinuz, initrd.img)"
    fi
}

test_serial_console_enabled() {
    if [ -e "$MNT_SQUASH/etc/systemd/system/multi-user.target.wants/serial-getty@ttyS0.service" ] || \
       [ -L "$MNT_SQUASH/etc/systemd/system/getty.target.wants/serial-getty@ttyS0.service" ]; then
        pass "Serial console getty enabled (QEMU testing)"
    else
        fail "Serial console getty not enabled"
    fi
}

test_sudo_nopasswd() {
    if [ -f "$MNT_SQUASH/etc/sudoers.d/90-anklume" ]; then
        if grep -q "NOPASSWD" "$MNT_SQUASH/etc/sudoers.d/90-anklume"; then
            pass "Passwordless sudo configured for anklume user"
        else
            fail "sudo file exists but no NOPASSWD"
        fi
    else
        fail "sudoers.d/90-anklume missing"
    fi
}

# ── Runner ───────────────────────────────────────────────────

ALL_TESTS=(
    sddm-absent
    zfs-module
    zfs-tools
    btrfs-tools
    incus-binary
    incus-service-enabled
    user-groups
    user-adm-group
    apparmor-parser
    start-script
    doctor-script
    anklume-cli
    aa-teardown-service
    start-service
    no-display-manager
    boot-files
    serial-console
    sudo-nopasswd
)

run_test() {
    local name="$1"
    case "$name" in
        sddm-absent)           test_sddm_absent ;;
        zfs-module)             test_zfs_module ;;
        zfs-tools)              test_zfs_tools ;;
        btrfs-tools)            test_btrfs_tools ;;
        incus-binary)           test_incus_binary ;;
        incus-service-enabled)  test_incus_service_enabled ;;
        user-groups)            test_user_groups ;;
        user-adm-group)         test_user_adm_group ;;
        apparmor-parser)        test_apparmor_parser ;;
        start-script)           test_start_script ;;
        doctor-script)          test_doctor_script ;;
        anklume-cli)            test_anklume_cli ;;
        aa-teardown-service)    test_aa_teardown_service ;;
        start-service)          test_start_service ;;
        no-display-manager)     test_no_display_manager_autostart ;;
        boot-files)             test_boot_files ;;
        serial-console)         test_serial_console_enabled ;;
        sudo-nopasswd)          test_sudo_nopasswd ;;
        *)
            err "Unknown test: $name"
            return 1
            ;;
    esac
}

main() {
    if [ "$(id -u)" -ne 0 ]; then
        err "Must run as root (need to mount ISO and squashfs)"
        exit 2
    fi

    if [ -z "$ISO_PATH" ]; then
        echo "Usage: $0 <iso-path> [test-name|all]"
        echo ""
        echo "Tests: ${ALL_TESTS[*]}"
        exit 1
    fi

    setup_mounts

    echo "═══════════════════════════════════════════════════"
    echo "  L2 ISO Content Tests: $(basename "$ISO_PATH")"
    echo "═══════════════════════════════════════════════════"
    echo ""

    if [ "$TEST_NAME" = "all" ]; then
        for t in "${ALL_TESTS[@]}"; do
            run_test "$t"
        done
    else
        run_test "$TEST_NAME"
    fi

    echo ""
    echo "═══════════════════════════════════════════════════"
    echo "  Results: $PASS_COUNT passed, $FAIL_COUNT failed"
    echo "═══════════════════════════════════════════════════"

    if [ "$FAIL_COUNT" -gt 0 ]; then
        exit 1
    fi
    exit 0
}

main
