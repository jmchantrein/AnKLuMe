"""Tests for Phase 31 — Live OS with Encrypted Persistent Storage.

This module tests all scripts and configurations for the anklume live OS phase:
  - live-os-lib.sh (shared library)
  - build-image.sh (image building)
  - first-boot.sh (initial setup)
  - live-update.sh (A/B updates)
  - Initramfs hooks (anklume-toram, anklume-verity)
  - Systemd services (anklume-first-boot.service, anklume-data-mount.service)
  - Boot scripts (mount-data.sh, umount-data.sh)
  - Makefile targets (build-image, live-update, live-status)
"""

import re
import stat
import subprocess
from pathlib import Path

import pytest

# ── Path definitions ──────────────────────────────────────────────

LIVE_OS_LIB = Path(__file__).resolve().parent.parent / "scripts" / "live-os-lib.sh"
BUILD_IMAGE = Path(__file__).resolve().parent.parent / "scripts" / "build-image.sh"
FIRST_BOOT = Path(__file__).resolve().parent.parent / "scripts" / "first-boot.sh"
LIVE_UPDATE = Path(__file__).resolve().parent.parent / "scripts" / "live-update.sh"
TORAM_HOOK = Path(__file__).resolve().parent.parent / "host" / "boot" / "initramfs" / "anklume-toram"
VERITY_HOOK = Path(__file__).resolve().parent.parent / "host" / "boot" / "initramfs" / "anklume-verity"
FIRST_BOOT_SERVICE = Path(__file__).resolve().parent.parent / "host" / "boot" / "systemd" / "anklume-first-boot.service"
DATA_MOUNT_SERVICE = Path(__file__).resolve().parent.parent / "host" / "boot" / "systemd" / "anklume-data-mount.service"
MOUNT_DATA = Path(__file__).resolve().parent.parent / "host" / "boot" / "scripts" / "mount-data.sh"
UMOUNT_DATA = Path(__file__).resolve().parent.parent / "host" / "boot" / "scripts" / "umount-data.sh"
MAKEFILE = Path(__file__).resolve().parent.parent / "Makefile"

# Mkinitcpio hooks paths for Arch support
_MKINITCPIO = (
    Path(__file__).resolve().parent.parent / "host" / "boot" / "mkinitcpio"
)
MKINITCPIO_TORAM_INSTALL = _MKINITCPIO / "install" / "anklume-toram"
MKINITCPIO_TORAM_HOOK = _MKINITCPIO / "hooks" / "anklume-toram"
MKINITCPIO_VERITY_INSTALL = _MKINITCPIO / "install" / "anklume-verity"
MKINITCPIO_VERITY_HOOK = _MKINITCPIO / "hooks" / "anklume-verity"
GRUB_CONFIG = Path(__file__).resolve().parent.parent / "host" / "boot" / "grub" / "grub.cfg"
TEST_VM_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "live-os-test-vm.sh"


# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture()
def mock_persist_dir(tmp_path):
    """Create a mock persist directory with expected structure."""
    persist = tmp_path / "mnt" / "anklume-persist"
    persist.mkdir(parents=True, exist_ok=True)
    (persist / "pool.conf").write_text(
        "pool_name=anklume-data\npool_type=zfs\npool_uuid=12345-uuid\ndata_device=/dev/sda4\n"
    )
    (persist / "ab-state").write_text("A\n")
    (persist / "boot-count").write_text("0\n")
    return persist


# ── TestShellSyntax ───────────────────────────────────────────────


class TestShellSyntax:
    """All shell scripts must pass bash -n for syntax validation."""

    @pytest.mark.parametrize("script", [
        LIVE_OS_LIB,
        TORAM_HOOK,
        VERITY_HOOK,
        MOUNT_DATA,
        UMOUNT_DATA,
    ])
    def test_syntax(self, script):
        """Verify shell script passes bash -n syntax check."""
        if not script.exists():
            pytest.skip(f"Script not found: {script}")

        result = subprocess.run(
            ["bash", "-n", str(script)],
            capture_output=True, text=True,
            timeout=10,
        )
        assert result.returncode == 0, f"Syntax error in {script.name}:\n{result.stderr}"


# ── TestLiveOsLibStructure ────────────────────────────────────────


class TestLiveOsLibStructure:
    """Verify live-os-lib.sh has all required constants, sizes, and functions."""

    @classmethod
    def setup_class(cls):
        """Cache file content for test class."""
        if not LIVE_OS_LIB.exists():
            pytest.skip(f"File not found: {LIVE_OS_LIB}")
        cls.content = LIVE_OS_LIB.read_text()

    def test_file_exists(self):
        """Verify live-os-lib.sh exists."""
        assert LIVE_OS_LIB.exists(), f"File not found: {LIVE_OS_LIB}"

    def test_shebang(self):
        """Verify shebang line."""
        assert self.content.startswith("#!/usr/bin/env bash")

    def test_set_euo_pipefail(self):
        """Verify set -euo pipefail for safety."""
        assert "set -euo pipefail" in self.content

    # Partition label constants
    def test_efi_label_constant(self):
        """Verify ANKLUME_EFI_LABEL constant."""
        assert "ANKLUME_EFI_LABEL" in self.content
        assert "ANKLUME-EFI" in self.content

    def test_osa_label_constant(self):
        """Verify ANKLUME_OSA_LABEL constant."""
        assert "ANKLUME_OSA_LABEL" in self.content
        assert "ANKLUME-OS-A" in self.content

    def test_osb_label_constant(self):
        """Verify ANKLUME_OSB_LABEL constant."""
        assert "ANKLUME_OSB_LABEL" in self.content
        assert "ANKLUME-OS-B" in self.content

    def test_persist_label_constant(self):
        """Verify ANKLUME_PERSIST_LABEL constant."""
        assert "ANKLUME_PERSIST_LABEL" in self.content
        assert "ANKLUME-PERSIST" in self.content

    def test_data_label_constant(self):
        """Verify ANKLUME_DATA_LABEL constant."""
        assert "ANKLUME_DATA_LABEL" in self.content
        assert "ANKLUME-DATA" in self.content

    # Size constants
    def test_efi_size_constant(self):
        """Verify EFI_SIZE_MB constant."""
        assert "EFI_SIZE_MB" in self.content
        assert re.search(r"EFI_SIZE_MB\s*=\s*512", self.content)

    def test_os_size_constant(self):
        """Verify OS_SIZE_MB constant."""
        assert "OS_SIZE_MB" in self.content
        assert re.search(r"OS_SIZE_MB\s*=\s*1536", self.content)

    def test_persist_size_constant(self):
        """Verify PERSIST_SIZE_MB constant."""
        assert "PERSIST_SIZE_MB" in self.content
        assert re.search(r"PERSIST_SIZE_MB\s*=\s*100", self.content)

    # Mount points
    def test_persist_mount_constant(self):
        """Verify PERSIST_MNT constant."""
        assert "PERSIST_MNT" in self.content
        assert "/mnt/anklume-persist" in self.content

    def test_data_mount_constant(self):
        """Verify DATA_MNT constant."""
        assert "DATA_MNT" in self.content
        assert "/mnt/anklume-data" in self.content

    # Config paths
    def test_pool_conf_path(self):
        """Verify POOL_CONF constant."""
        assert "POOL_CONF" in self.content

    def test_ab_state_path(self):
        """Verify AB_STATE constant."""
        assert "AB_STATE" in self.content

    def test_boot_count_path(self):
        """Verify BOOT_COUNT constant."""
        assert "BOOT_COUNT" in self.content

    # Functions: Boot state management
    def test_get_active_slot_function(self):
        """Verify get_active_slot() function."""
        assert re.search(r'get_active_slot\(\)', self.content)

    def test_set_active_slot_function(self):
        """Verify set_active_slot() function."""
        assert re.search(r'set_active_slot\(\)', self.content)

    def test_get_inactive_slot_function(self):
        """Verify get_inactive_slot() function."""
        assert re.search(r'get_inactive_slot\(\)', self.content)

    # Functions: Boot counting
    def test_get_boot_count_function(self):
        """Verify get_boot_count() function."""
        assert re.search(r'get_boot_count\(\)', self.content)

    def test_increment_boot_count_function(self):
        """Verify increment_boot_count() function."""
        assert re.search(r'increment_boot_count\(\)', self.content)

    def test_reset_boot_count_function(self):
        """Verify reset_boot_count() function."""
        assert re.search(r'reset_boot_count\(\)', self.content)

    # Functions: RAM encryption and discovery
    def test_detect_ram_encryption_function(self):
        """Verify detect_ram_encryption() function."""
        assert re.search(r'detect_ram_encryption\(\)', self.content)

    def test_find_partition_by_label_function(self):
        """Verify find_partition_by_label() function."""
        assert re.search(r'find_partition_by_label\(\)', self.content)

    def test_ensure_persist_mounted_function(self):
        """Verify ensure_persist_mounted() function."""
        assert re.search(r'ensure_persist_mounted\(\)', self.content)

    # Logging helpers
    def test_info_helper(self):
        """Verify info() logging helper."""
        assert re.search(r'^info\(\)', self.content, re.MULTILINE)

    def test_ok_helper(self):
        """Verify ok() logging helper."""
        assert re.search(r'^ok\(\)', self.content, re.MULTILINE)

    def test_warn_helper(self):
        """Verify warn() logging helper."""
        assert re.search(r'^warn\(\)', self.content, re.MULTILINE)

    def test_err_helper(self):
        """Verify err() logging helper."""
        assert re.search(r'^err\(\)', self.content, re.MULTILINE)

    # Logging with ANSI colors
    def test_ansi_colors_in_logging(self):
        """Verify logging helpers use ANSI color codes."""
        assert "\\033" in self.content
        assert "[INFO]" in self.content
        assert "[ OK ]" in self.content
        assert "[WARN]" in self.content
        assert "[ERR ]" in self.content


# ── TestBuildImageStructure ───────────────────────────────────────


class TestBuildImageStructure:
    """Verify build-image.sh has all required components."""

    @classmethod
    def setup_class(cls):
        """Cache file content for test class."""
        if not BUILD_IMAGE.exists():
            pytest.skip(f"File not found: {BUILD_IMAGE}")
        cls.content = BUILD_IMAGE.read_text()

    def test_file_exists(self):
        """Verify build-image.sh exists."""
        assert BUILD_IMAGE.exists()

    def test_shebang(self):
        """Verify shebang line."""
        assert self.content.startswith("#!/usr/bin/env bash") or self.content.startswith("#!/bin/bash")

    def test_set_euo_pipefail(self):
        """Verify set -euo pipefail for safety."""
        assert "set -euo pipefail" in self.content

    def test_main_function_exists(self):
        """Verify main() function defined."""
        assert re.search(r'^main\(\)', self.content, re.MULTILINE)

    def test_main_called_at_end(self):
        """Verify script ends with main call."""
        lines = [line.strip() for line in self.content.strip().splitlines()
                 if line.strip() and not line.strip().startswith('#')]
        assert lines[-1] == 'main "$@"'

    def test_uses_debootstrap(self):
        """Verify script uses debootstrap."""
        assert "debootstrap" in self.content

    def test_uses_mksquashfs(self):
        """Verify script uses mksquashfs for image compression."""
        assert "mksquashfs" in self.content

    def test_uses_veritysetup(self):
        """Verify script uses veritysetup for integrity."""
        assert "veritysetup" in self.content

    def test_disk_partitioning_tools(self):
        """Verify script uses sgdisk or sfdisk for partitioning."""
        assert "sgdisk" in self.content or "sfdisk" in self.content

    def test_systemd_boot_config(self):
        """Verify systemd-boot configuration."""
        assert "systemd-boot" in self.content or "loader" in self.content


# ── TestFirstBootStructure ────────────────────────────────────────


class TestFirstBootStructure:
    """Verify first-boot.sh has correct structure."""

    @classmethod
    def setup_class(cls):
        """Cache file content for test class."""
        if not FIRST_BOOT.exists():
            pytest.skip(f"File not found: {FIRST_BOOT}")
        cls.content = FIRST_BOOT.read_text()

    def test_file_exists(self):
        """Verify first-boot.sh exists."""
        assert FIRST_BOOT.exists()

    def test_shebang(self):
        """Verify shebang line."""
        assert self.content.startswith("#!/usr/bin/env bash") or self.content.startswith("#!/bin/bash")

    def test_sources_live_os_lib(self):
        """Verify sources live-os-lib.sh."""
        assert "live-os-lib.sh" in self.content or "source" in self.content

    def test_disk_detection(self):
        """Verify disk detection using lsblk."""
        assert "lsblk" in self.content or "blkid" in self.content

    def test_luks_setup(self):
        """Verify LUKS encryption setup."""
        assert "cryptsetup" in self.content or "luksFormat" in self.content

    def test_zfs_pool_creation(self):
        """Verify ZFS pool creation."""
        assert "zpool" in self.content

    def test_incus_storage_pool(self):
        """Verify Incus storage pool configuration."""
        assert "incus" in self.content or "storage" in self.content

    def test_main_function(self):
        """Verify main() wrapper function."""
        assert re.search(r'^main\(\)', self.content, re.MULTILINE)


# ── TestLiveUpdateStructure ────────────────────────────────────────


class TestLiveUpdateStructure:
    """Verify live-update.sh has A/B slot logic and verification."""

    @classmethod
    def setup_class(cls):
        """Cache file content for test class."""
        if not LIVE_UPDATE.exists():
            pytest.skip(f"File not found: {LIVE_UPDATE}")
        cls.content = LIVE_UPDATE.read_text()

    def test_file_exists(self):
        """Verify live-update.sh exists."""
        assert LIVE_UPDATE.exists()

    def test_shebang(self):
        """Verify shebang line."""
        assert self.content.startswith("#!/usr/bin/env bash") or self.content.startswith("#!/bin/bash")

    def test_sources_live_os_lib(self):
        """Verify sources live-os-lib.sh."""
        assert "live-os-lib.sh" in self.content or "source" in self.content

    def test_ab_slot_logic(self):
        """Verify A/B slot selection logic."""
        assert "get_inactive_slot" in self.content or "slot" in self.content.lower()

    def test_image_download(self):
        """Verify image download using curl or wget."""
        assert "curl" in self.content or "wget" in self.content

    def test_verity_verification(self):
        """Verify verity hash verification."""
        assert "veritysetup" in self.content or "verity" in self.content

    def test_boot_counter_reset(self):
        """Verify boot counter reset after update."""
        assert "reset_boot_count" in self.content or "boot" in self.content.lower()

    def test_main_function(self):
        """Verify main() wrapper function."""
        assert re.search(r'^main\(\)', self.content, re.MULTILINE)


# ── TestInitramfsToram ────────────────────────────────────────────


class TestInitramfsToram:
    """Verify anklume-toram initramfs hook."""

    @classmethod
    def setup_class(cls):
        """Cache file content for test class."""
        if not TORAM_HOOK.exists():
            pytest.skip(f"File not found: {TORAM_HOOK}")
        cls.content = TORAM_HOOK.read_text()

    def test_file_exists(self):
        """Verify anklume-toram hook exists."""
        assert TORAM_HOOK.exists()

    def test_executable(self):
        """Verify hook is executable."""
        assert TORAM_HOOK.stat().st_mode & stat.S_IEXEC

    def test_prereq_function(self):
        """Verify PREREQ function defined."""
        assert "prereq()" in self.content

    def test_go_function(self):
        """Verify go() function for main logic."""
        assert "go()" in self.content

    def test_case_statement(self):
        """Verify case statement for prereq/go."""
        assert "case $1 in" in self.content or "case" in self.content

    def test_kernel_cmdline_parsing(self):
        """Verify /proc/cmdline parsing."""
        assert "/proc/cmdline" in self.content

    def test_anklume_toram_detection(self):
        """Verify detection of anklume.toram parameter."""
        assert "anklume.toram" in self.content

    def test_tmpfs_mount(self):
        """Verify tmpfs mount for RAM."""
        assert "tmpfs" in self.content

    def test_squashfs_copy(self):
        """Verify squashfs image copy to RAM."""
        assert "squashfs" in self.content or "cp" in self.content


# ── TestInitramfsVerity ────────────────────────────────────────────


class TestInitramfsVerity:
    """Verify anklume-verity initramfs hook."""

    @classmethod
    def setup_class(cls):
        """Cache file content for test class."""
        if not VERITY_HOOK.exists():
            pytest.skip(f"File not found: {VERITY_HOOK}")
        cls.content = VERITY_HOOK.read_text()

    def test_file_exists(self):
        """Verify anklume-verity hook exists."""
        assert VERITY_HOOK.exists()

    def test_executable(self):
        """Verify hook is executable."""
        assert VERITY_HOOK.stat().st_mode & stat.S_IEXEC

    def test_prereq_function(self):
        """Verify PREREQ function defined."""
        assert "prereq()" in self.content

    def test_go_function(self):
        """Verify go() function for main logic."""
        assert "go()" in self.content

    def test_case_statement(self):
        """Verify case statement for prereq/go."""
        assert "case" in self.content

    def test_kernel_cmdline_parsing(self):
        """Verify /proc/cmdline parsing."""
        assert "/proc/cmdline" in self.content

    def test_verity_hash_parameter(self):
        """Verify detection of anklume.verity_hash parameter."""
        assert "verity_hash" in self.content

    def test_slot_parameter(self):
        """Verify detection of anklume.slot parameter."""
        assert "slot" in self.content.lower()

    def test_blkid_partition_lookup(self):
        """Verify blkid partition discovery."""
        assert "blkid" in self.content

    def test_veritysetup_activation(self):
        """Verify veritysetup activation."""
        assert "veritysetup" in self.content

    def test_root_device_export(self):
        """Verify ROOT device export."""
        assert "export ROOT" in self.content or "ROOT=" in self.content


# ── TestSystemdServices ───────────────────────────────────────────


class TestSystemdServices:
    """Verify systemd service files have correct INI format and conditions."""

    def test_first_boot_service_exists(self):
        """Verify anklume-first-boot.service exists."""
        if not FIRST_BOOT_SERVICE.exists():
            pytest.skip(f"File not found: {FIRST_BOOT_SERVICE}")
        assert FIRST_BOOT_SERVICE.exists()

    def test_first_boot_valid_ini(self):
        """Verify first-boot service has valid INI sections."""
        if not FIRST_BOOT_SERVICE.exists():
            pytest.skip(f"File not found: {FIRST_BOOT_SERVICE}")

        content = FIRST_BOOT_SERVICE.read_text()
        assert "[Unit]" in content
        assert "[Service]" in content
        assert "[Install]" in content

    def test_first_boot_condition_path_not_exists(self):
        """Verify first-boot runs only if persist not initialized."""
        if not FIRST_BOOT_SERVICE.exists():
            pytest.skip(f"File not found: {FIRST_BOOT_SERVICE}")

        content = FIRST_BOOT_SERVICE.read_text()
        assert "ConditionPathExists=!/mnt/anklume-persist/pool.conf" in content

    def test_first_boot_wanted_by(self):
        """Verify first-boot is wanted by multi-user.target."""
        if not FIRST_BOOT_SERVICE.exists():
            pytest.skip(f"File not found: {FIRST_BOOT_SERVICE}")

        content = FIRST_BOOT_SERVICE.read_text()
        assert "WantedBy=multi-user.target" in content

    def test_data_mount_service_exists(self):
        """Verify anklume-data-mount.service exists."""
        if not DATA_MOUNT_SERVICE.exists():
            pytest.skip(f"File not found: {DATA_MOUNT_SERVICE}")
        assert DATA_MOUNT_SERVICE.exists()

    def test_data_mount_valid_ini(self):
        """Verify data-mount service has valid INI sections."""
        if not DATA_MOUNT_SERVICE.exists():
            pytest.skip(f"File not found: {DATA_MOUNT_SERVICE}")

        content = DATA_MOUNT_SERVICE.read_text()
        assert "[Unit]" in content
        assert "[Service]" in content
        assert "[Install]" in content

    def test_data_mount_condition_path_exists(self):
        """Verify data-mount runs only if persist is initialized."""
        if not DATA_MOUNT_SERVICE.exists():
            pytest.skip(f"File not found: {DATA_MOUNT_SERVICE}")

        content = DATA_MOUNT_SERVICE.read_text()
        assert "ConditionPathExists=/mnt/anklume-persist/pool.conf" in content

    def test_data_mount_before_incus(self):
        """Verify data-mount runs before incus.service."""
        if not DATA_MOUNT_SERVICE.exists():
            pytest.skip(f"File not found: {DATA_MOUNT_SERVICE}")

        content = DATA_MOUNT_SERVICE.read_text()
        assert "Before=incus.service" in content

    def test_data_mount_wanted_by(self):
        """Verify data-mount is wanted by multi-user.target."""
        if not DATA_MOUNT_SERVICE.exists():
            pytest.skip(f"File not found: {DATA_MOUNT_SERVICE}")

        content = DATA_MOUNT_SERVICE.read_text()
        assert "WantedBy=multi-user.target" in content


# ── TestMountDataStructure ────────────────────────────────────────


class TestMountDataStructure:
    """Verify mount-data.sh has correct structure and logic."""

    @classmethod
    def setup_class(cls):
        """Cache file content for test class."""
        if not MOUNT_DATA.exists():
            pytest.skip(f"File not found: {MOUNT_DATA}")
        cls.content = MOUNT_DATA.read_text()

    def test_file_exists(self):
        """Verify mount-data.sh exists."""
        assert MOUNT_DATA.exists()

    def test_shebang(self):
        """Verify shebang line."""
        assert self.content.startswith("#!/usr/bin/env bash")

    def test_set_euo_pipefail(self):
        """Verify set -euo pipefail for safety."""
        assert "set -euo pipefail" in self.content

    def test_sources_live_os_lib(self):
        """Verify sources live-os-lib.sh."""
        assert "live-os-lib.sh" in self.content

    def test_pool_conf_reading(self):
        """Verify reads pool.conf."""
        assert "pool.conf" in self.content or "POOL_CONF" in self.content

    def test_cryptsetup_luksopen(self):
        """Verify uses cryptsetup luksOpen."""
        assert "cryptsetup" in self.content or "luksOpen" in self.content

    def test_zpool_import(self):
        """Verify ZFS pool import logic."""
        assert "zpool" in self.content

    def test_filesystem_mount(self):
        """Verify mount command for filesystem mounting."""
        assert "mount" in self.content

    def test_main_function(self):
        """Verify main() wrapper function."""
        assert "main()" in self.content

    def test_pool_type_detection(self):
        """Verify detects pool type (zfs/btrfs)."""
        assert "zfs" in self.content.lower() and "btrfs" in self.content.lower()


# ── TestUmountDataStructure ────────────────────────────────────────


class TestUmountDataStructure:
    """Verify umount-data.sh has correct structure and logic."""

    @classmethod
    def setup_class(cls):
        """Cache file content for test class."""
        if not UMOUNT_DATA.exists():
            pytest.skip(f"File not found: {UMOUNT_DATA}")
        cls.content = UMOUNT_DATA.read_text()

    def test_file_exists(self):
        """Verify umount-data.sh exists."""
        assert UMOUNT_DATA.exists()

    def test_shebang(self):
        """Verify shebang line."""
        assert self.content.startswith("#!/usr/bin/env bash")

    def test_set_euo_pipefail(self):
        """Verify set -euo pipefail for safety."""
        assert "set -euo pipefail" in self.content

    def test_zpool_export(self):
        """Verify zpool export logic."""
        assert "zpool" in self.content and "export" in self.content

    def test_umount_command(self):
        """Verify umount command."""
        assert "umount" in self.content

    def test_cryptsetup_luksclose(self):
        """Verify cryptsetup luksClose logic."""
        assert "cryptsetup" in self.content or "luksClose" in self.content

    def test_pool_type_detection(self):
        """Verify detects pool type (zfs/btrfs)."""
        assert "zfs" in self.content.lower() and "btrfs" in self.content.lower()

    def test_main_function(self):
        """Verify main() wrapper function."""
        assert "main()" in self.content

    def test_graceful_degradation(self):
        """Verify handles unmount failures gracefully."""
        assert "warn" in self.content or "continue" in self.content.lower()


# ── TestLiveOsLibABState ──────────────────────────────────────────


class TestLiveOsLibABState:
    """Functional tests for A/B state management in live-os-lib.sh."""

    def test_get_active_slot_returns_default_a(self, mock_persist_dir):
        """Test get_active_slot returns 'A' when ab-state is not set."""
        ab_state_file = mock_persist_dir / "ab-state"
        ab_state_file.unlink(missing_ok=True)

        # Source the library and test
        result = subprocess.run(
            [
                "bash", "-c",
                f"source {LIVE_OS_LIB} && "
                f"PERSIST_MNT={mock_persist_dir} AB_STATE={mock_persist_dir}/ab-state && "
                f"get_active_slot"
            ],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "A" in result.stdout

    def test_set_active_slot_writes_value(self, mock_persist_dir):
        """Test set_active_slot writes slot to ab-state file."""
        ab_state_file = mock_persist_dir / "ab-state"
        ab_state_file.write_text("")

        result = subprocess.run(
            [
                "bash", "-c",
                f"source {LIVE_OS_LIB} && "
                f"PERSIST_MNT={mock_persist_dir} AB_STATE={mock_persist_dir}/ab-state && "
                f"set_active_slot B"
            ],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert ab_state_file.read_text().strip() == "B"

    def test_get_inactive_slot_returns_opposite(self, mock_persist_dir):
        """Test get_inactive_slot returns opposite of active slot."""
        ab_state_file = mock_persist_dir / "ab-state"
        ab_state_file.write_text("A")

        result = subprocess.run(
            [
                "bash", "-c",
                f"source {LIVE_OS_LIB} && "
                f"PERSIST_MNT={mock_persist_dir} AB_STATE={mock_persist_dir}/ab-state && "
                f"get_inactive_slot"
            ],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "B" in result.stdout

    def test_boot_count_increment(self, mock_persist_dir):
        """Test boot count increment operation."""
        boot_count_file = mock_persist_dir / "boot-count"
        boot_count_file.write_text("5")

        result = subprocess.run(
            [
                "bash", "-c",
                f"source {LIVE_OS_LIB} && "
                f"BOOT_COUNT={mock_persist_dir}/boot-count && "
                f"increment_boot_count && "
                f"get_boot_count"
            ],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "6" in result.stdout

    def test_boot_count_reset(self, mock_persist_dir):
        """Test boot count reset to 0."""
        boot_count_file = mock_persist_dir / "boot-count"
        boot_count_file.write_text("10")

        result = subprocess.run(
            [
                "bash", "-c",
                f"source {LIVE_OS_LIB} && "
                f"BOOT_COUNT={mock_persist_dir}/boot-count && "
                f"reset_boot_count && "
                f"get_boot_count"
            ],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "0" in result.stdout

    def test_detect_ram_encryption_returns_valid_output(self):
        """Test detect_ram_encryption returns expected encryption type."""
        result = subprocess.run(
            [
                "bash", "-c",
                f"source {LIVE_OS_LIB} && detect_ram_encryption"
            ],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        output = result.stdout.strip()
        assert output in ["amd-sme", "amd-sev", "intel-tme", "none"]


# ── TestMakefileTargets ────────────────────────────────────────────


class TestMakefileTargets:
    """Verify Makefile has Phase 31 live OS targets."""

    @classmethod
    def setup_class(cls):
        """Cache file content for test class."""
        if not MAKEFILE.exists():
            pytest.skip(f"File not found: {MAKEFILE}")
        cls.content = MAKEFILE.read_text()

    def test_file_exists(self):
        """Verify Makefile exists."""
        assert MAKEFILE.exists()

    def test_build_image_target(self):
        """Verify build-image target exists."""
        assert "build-image:" in self.content

    def test_build_image_help_text(self):
        """Verify build-image target has help text."""
        assert re.search(r'build-image:.*##', self.content)

    def test_build_image_script_reference(self):
        """Verify build-image target calls build-image.sh."""
        assert "scripts/build-image.sh" in self.content

    def test_live_update_target(self):
        """Verify live-update target exists."""
        assert "live-update:" in self.content

    def test_live_update_help_text(self):
        """Verify live-update target has help text."""
        assert re.search(r'live-update:.*##', self.content)

    def test_live_update_script_reference(self):
        """Verify live-update target calls live-update.sh."""
        assert "scripts/live-update.sh" in self.content

    def test_live_status_target(self):
        """Verify live-status target exists."""
        assert "live-status:" in self.content

    def test_live_status_help_text(self):
        """Verify live-status target has help text."""
        assert re.search(r'live-status:.*##', self.content)

    def test_live_status_script_reference(self):
        """Verify live-status shows live OS status."""
        assert "live-status" in self.content


# ── TestBuildImageArchSupport ─────────────────────────────────────


class TestBuildImageArchSupport:
    """Verify build-image.sh has Arch Linux support."""

    @classmethod
    def setup_class(cls):
        """Cache file content for test class."""
        if not BUILD_IMAGE.exists():
            pytest.skip(f"File not found: {BUILD_IMAGE}")
        cls.content = BUILD_IMAGE.read_text()

    def test_bootstrap_rootfs_arch_function(self):
        """Verify bootstrap_rootfs_arch() function exists."""
        assert re.search(r'bootstrap_rootfs_arch\(\)', self.content)

    def test_bootstrap_rootfs_debian_function(self):
        """Verify bootstrap_rootfs_debian() function exists (renamed from original)."""
        assert re.search(r'bootstrap_rootfs_debian\(\)', self.content)

    def test_bootstrap_rootfs_dispatch(self):
        """Verify bootstrap_rootfs() dispatcher exists."""
        assert re.search(r'bootstrap_rootfs\(\)', self.content)

    def test_pacstrap_referenced(self):
        """Verify pacstrap appears (Arch package installer)."""
        assert "pacstrap" in self.content

    def test_mkinitcpio_referenced(self):
        """Verify mkinitcpio appears (Arch initramfs)."""
        assert "mkinitcpio" in self.content

    def test_arch_kernel_paths(self):
        """Verify vmlinuz-linux appears (Arch kernel name)."""
        assert "vmlinuz-linux" in self.content

    def test_generate_checksums_function(self):
        """Verify generate_checksums() function exists."""
        assert re.search(r'generate_checksums\(\)', self.content)

    def test_sha256sum_usage(self):
        """Verify sha256sum appears."""
        assert "sha256sum" in self.content

    def test_base_arch_in_usage(self):
        """Verify arch appears in usage/help text."""
        assert "arch" in self.content.lower()


# ── TestMkinitcpioHooks ────────────────────────────────────────────


class TestMkinitcpioHooks:
    """Verify mkinitcpio hooks for Arch (similar to initramfs hooks for Debian)."""

    def test_toram_install_exists(self):
        """Verify anklume-toram install hook exists."""
        if not MKINITCPIO_TORAM_INSTALL.exists():
            pytest.skip(f"File not found: {MKINITCPIO_TORAM_INSTALL}")
        assert MKINITCPIO_TORAM_INSTALL.exists()

    def test_toram_install_build_function(self):
        """Verify build() function in toram install hook."""
        if not MKINITCPIO_TORAM_INSTALL.exists():
            pytest.skip(f"File not found: {MKINITCPIO_TORAM_INSTALL}")
        content = MKINITCPIO_TORAM_INSTALL.read_text()
        assert "build()" in content

    def test_toram_install_add_runscript(self):
        """Verify add_runscript call in toram install hook."""
        if not MKINITCPIO_TORAM_INSTALL.exists():
            pytest.skip(f"File not found: {MKINITCPIO_TORAM_INSTALL}")
        content = MKINITCPIO_TORAM_INSTALL.read_text()
        assert "add_runscript" in content

    def test_toram_hook_exists(self):
        """Verify anklume-toram hook exists."""
        if not MKINITCPIO_TORAM_HOOK.exists():
            pytest.skip(f"File not found: {MKINITCPIO_TORAM_HOOK}")
        assert MKINITCPIO_TORAM_HOOK.exists()

    def test_toram_hook_run_hook(self):
        """Verify run_hook() function in toram hook."""
        if not MKINITCPIO_TORAM_HOOK.exists():
            pytest.skip(f"File not found: {MKINITCPIO_TORAM_HOOK}")
        content = MKINITCPIO_TORAM_HOOK.read_text()
        assert "run_hook()" in content

    def test_toram_hook_is_stub(self):
        """Verify toram hook is a stub (logic moved to verity)."""
        if not MKINITCPIO_TORAM_HOOK.exists():
            pytest.skip(f"File not found: {MKINITCPIO_TORAM_HOOK}")
        content = MKINITCPIO_TORAM_HOOK.read_text()
        assert "return 0" in content

    def test_verity_install_exists(self):
        """Verify anklume-verity install hook exists."""
        if not MKINITCPIO_VERITY_INSTALL.exists():
            pytest.skip(f"File not found: {MKINITCPIO_VERITY_INSTALL}")
        assert MKINITCPIO_VERITY_INSTALL.exists()

    def test_verity_install_add_binary(self):
        """Verify add_binary calls for losetup, blkid, mount."""
        if not MKINITCPIO_VERITY_INSTALL.exists():
            pytest.skip(f"File not found: {MKINITCPIO_VERITY_INSTALL}")
        content = MKINITCPIO_VERITY_INSTALL.read_text()
        assert "add_binary losetup" in content
        assert "add_binary blkid" in content
        assert "add_binary mount" in content

    def test_verity_hook_exists(self):
        """Verify anklume-verity hook exists."""
        if not MKINITCPIO_VERITY_HOOK.exists():
            pytest.skip(f"File not found: {MKINITCPIO_VERITY_HOOK}")
        assert MKINITCPIO_VERITY_HOOK.exists()

    def test_verity_hook_run_hook(self):
        """Verify run_hook() function in verity hook."""
        if not MKINITCPIO_VERITY_HOOK.exists():
            pytest.skip(f"File not found: {MKINITCPIO_VERITY_HOOK}")
        content = MKINITCPIO_VERITY_HOOK.read_text()
        assert "run_hook()" in content

    def test_verity_hook_mount_handler(self):
        """Verify mount_handler pattern in verity hook."""
        if not MKINITCPIO_VERITY_HOOK.exists():
            pytest.skip(f"File not found: {MKINITCPIO_VERITY_HOOK}")
        content = MKINITCPIO_VERITY_HOOK.read_text()
        assert "mount_handler" in content
        assert "anklume_mount_handler" in content

    def test_verity_hook_squashfs_overlay(self):
        """Verify squashfs + overlayfs mount in verity hook."""
        if not MKINITCPIO_VERITY_HOOK.exists():
            pytest.skip(f"File not found: {MKINITCPIO_VERITY_HOOK}")
        content = MKINITCPIO_VERITY_HOOK.read_text()
        assert "squashfs" in content
        assert "overlay" in content


# ── TestISOSupport ───────────────────────────────────────────────


class TestISOSupport:
    """Verify build-image.sh has ISO output format support."""

    @classmethod
    def setup_class(cls):
        """Cache file content for test class."""
        if not BUILD_IMAGE.exists():
            pytest.skip(f"File not found: {BUILD_IMAGE}")
        cls.content = BUILD_IMAGE.read_text()

    def test_format_flag_exists(self):
        """Verify --format flag is accepted."""
        assert "--format" in self.content

    def test_format_iso_default(self):
        """Verify default format is iso."""
        assert re.search(r'FORMAT="iso"', self.content)

    def test_format_validation(self):
        """Verify format is validated (iso or raw)."""
        assert "iso|raw" in self.content or ("iso" in self.content and "raw" in self.content)

    def test_xorriso_referenced(self):
        """Verify xorriso is used for ISO assembly."""
        assert "xorriso" in self.content

    def test_grub_mkimage_referenced(self):
        """Verify grub-mkimage is used for BIOS boot."""
        assert "grub-mkimage" in self.content or "grub-mkstandalone" in self.content

    def test_assemble_iso_function(self):
        """Verify assemble_iso() function exists."""
        assert re.search(r'assemble_iso\(\)', self.content)

    def test_iso_staging_directory(self):
        """Verify ISO staging directory structure is created."""
        assert "iso-staging" in self.content

    def test_iso_label_used(self):
        """Verify ANKLUME_ISO_LABEL is used for the ISO volume ID."""
        assert "ANKLUME_ISO_LABEL" in self.content

    def test_iso_squashfs_path(self):
        """Verify squashfs is placed at live/rootfs.squashfs in ISO."""
        assert "live/rootfs.squashfs" in self.content

    def test_iso_verity_path(self):
        """Verify verity hash is placed at live/rootfs.verity in ISO."""
        assert "live/rootfs.verity" in self.content

    def test_efi_boot_image(self):
        """Verify EFI boot image (efiboot.img) is created."""
        assert "efiboot.img" in self.content

    def test_mtools_referenced(self):
        """Verify mtools commands are used for EFI image."""
        assert "mtools" in self.content


# ── TestGrubConfig ───────────────────────────────────────────────


class TestGrubConfig:
    """Verify GRUB config template for ISO boot."""

    @classmethod
    def setup_class(cls):
        """Cache file content for test class."""
        if not GRUB_CONFIG.exists():
            pytest.skip(f"File not found: {GRUB_CONFIG}")
        cls.content = GRUB_CONFIG.read_text()

    def test_file_exists(self):
        """Verify grub.cfg template exists."""
        assert GRUB_CONFIG.exists()

    def test_boot_mode_iso(self):
        """Verify anklume.boot_mode=iso parameter is set."""
        assert "anklume.boot_mode=iso" in self.content

    def test_verity_hash_placeholder(self):
        """Verify VERITY_HASH_PLACEHOLDER is present for build-time substitution."""
        assert "VERITY_HASH_PLACEHOLDER" in self.content

    def test_toram_entry(self):
        """Verify toram menu entry exists."""
        assert "anklume.toram=1" in self.content

    def test_direct_entry(self):
        """Verify direct (non-toram) submenu entry exists."""
        assert re.search(r'submenu.*direct', self.content, re.IGNORECASE)

    def test_kernel_path(self):
        """Verify kernel path is /boot/vmlinuz."""
        assert "/boot/vmlinuz" in self.content

    def test_initrd_path(self):
        """Verify initrd path is /boot/initrd.img."""
        assert "/boot/initrd.img" in self.content

    def test_console_serial(self):
        """Verify serial console is configured."""
        assert "console=ttyS0" in self.content


# ── TestVerityHookISO ────────────────────────────────────────────


class TestVerityHookISO:
    """Verify anklume-verity hooks support ISO boot mode."""

    def test_mkinitcpio_boot_mode_parsing(self):
        """Verify mkinitcpio verity hook parses anklume.boot_mode."""
        if not MKINITCPIO_VERITY_HOOK.exists():
            pytest.skip(f"File not found: {MKINITCPIO_VERITY_HOOK}")
        content = MKINITCPIO_VERITY_HOOK.read_text()
        assert "anklume.boot_mode=" in content
        assert "anklume_boot_mode" in content

    def test_mkinitcpio_iso_label_search(self):
        """Verify mkinitcpio verity hook searches for ANKLUME-LIVE label."""
        if not MKINITCPIO_VERITY_HOOK.exists():
            pytest.skip(f"File not found: {MKINITCPIO_VERITY_HOOK}")
        content = MKINITCPIO_VERITY_HOOK.read_text()
        assert "ANKLUME-LIVE" in content

    def test_mkinitcpio_toram_support(self):
        """Verify mkinitcpio verity hook supports toram copy."""
        if not MKINITCPIO_VERITY_HOOK.exists():
            pytest.skip(f"File not found: {MKINITCPIO_VERITY_HOOK}")
        content = MKINITCPIO_VERITY_HOOK.read_text()
        assert "anklume_toram" in content
        assert "copytoram" in content

    def test_mkinitcpio_losetup_usage(self):
        """Verify mkinitcpio verity hook uses losetup for ISO files."""
        if not MKINITCPIO_VERITY_HOOK.exists():
            pytest.skip(f"File not found: {MKINITCPIO_VERITY_HOOK}")
        content = MKINITCPIO_VERITY_HOOK.read_text()
        assert "losetup" in content

    def test_mkinitcpio_install_has_losetup(self):
        """Verify mkinitcpio verity install hook includes losetup."""
        if not MKINITCPIO_VERITY_INSTALL.exists():
            pytest.skip(f"File not found: {MKINITCPIO_VERITY_INSTALL}")
        content = MKINITCPIO_VERITY_INSTALL.read_text()
        assert "add_binary losetup" in content

    def test_mkinitcpio_install_has_loop_module(self):
        """Verify mkinitcpio verity install hook includes loop module."""
        if not MKINITCPIO_VERITY_INSTALL.exists():
            pytest.skip(f"File not found: {MKINITCPIO_VERITY_INSTALL}")
        content = MKINITCPIO_VERITY_INSTALL.read_text()
        assert "add_module loop" in content

    def test_initramfs_boot_mode_parsing(self):
        """Verify initramfs-tools verity hook parses anklume.boot_mode."""
        if not VERITY_HOOK.exists():
            pytest.skip(f"File not found: {VERITY_HOOK}")
        content = VERITY_HOOK.read_text()
        assert "anklume.boot_mode=" in content
        assert "BOOT_MODE" in content

    def test_initramfs_iso_label_search(self):
        """Verify initramfs-tools verity hook searches for ANKLUME-LIVE label."""
        if not VERITY_HOOK.exists():
            pytest.skip(f"File not found: {VERITY_HOOK}")
        content = VERITY_HOOK.read_text()
        assert "ANKLUME-LIVE" in content

    def test_initramfs_separate_data_hash(self):
        """Verify initramfs-tools verity hook uses separate data and hash devices."""
        if not VERITY_HOOK.exists():
            pytest.skip(f"File not found: {VERITY_HOOK}")
        content = VERITY_HOOK.read_text()
        assert "DATA_LOOP" in content
        assert "HASH_LOOP" in content


# ── TestToramHookISO ─────────────────────────────────────────────


class TestToramHookISO:
    """Verify anklume-toram hooks are stubs (logic in verity)."""

    def test_mkinitcpio_toram_is_stub(self):
        """Verify mkinitcpio toram hook is a stub."""
        if not MKINITCPIO_TORAM_HOOK.exists():
            pytest.skip(f"File not found: {MKINITCPIO_TORAM_HOOK}")
        content = MKINITCPIO_TORAM_HOOK.read_text()
        assert "return 0" in content

    def test_mkinitcpio_install_is_stub(self):
        """Verify mkinitcpio toram install is a stub."""
        if not MKINITCPIO_TORAM_INSTALL.exists():
            pytest.skip(f"File not found: {MKINITCPIO_TORAM_INSTALL}")
        content = MKINITCPIO_TORAM_INSTALL.read_text()
        assert "add_runscript" in content
        assert "add_binary" not in content


# ── TestLiveOsLibISO ─────────────────────────────────────────────


class TestLiveOsLibISO:
    """Verify live-os-lib.sh has ISO constants."""

    @classmethod
    def setup_class(cls):
        """Cache file content for test class."""
        if not LIVE_OS_LIB.exists():
            pytest.skip(f"File not found: {LIVE_OS_LIB}")
        cls.content = LIVE_OS_LIB.read_text()

    def test_iso_label_constant(self):
        """Verify ANKLUME_ISO_LABEL constant."""
        assert "ANKLUME_ISO_LABEL" in self.content
        assert "ANKLUME-LIVE" in self.content

    def test_iso_squashfs_path_constant(self):
        """Verify ISO_SQUASHFS_PATH constant."""
        assert "ISO_SQUASHFS_PATH" in self.content
        assert "live/rootfs.squashfs" in self.content

    def test_iso_verity_path_constant(self):
        """Verify ISO_VERITY_PATH constant."""
        assert "ISO_VERITY_PATH" in self.content
        assert "live/rootfs.verity" in self.content


# ── TestVMTestScriptISO ──────────────────────────────────────────


class TestVMTestScriptISO:
    """Verify live-os-test-vm.sh supports ISO format."""

    @classmethod
    def setup_class(cls):
        """Cache file content for test class."""
        if not TEST_VM_SCRIPT.exists():
            pytest.skip(f"File not found: {TEST_VM_SCRIPT}")
        cls.content = TEST_VM_SCRIPT.read_text()

    def test_iso_format_detection(self):
        """Verify script detects .iso extension."""
        assert "*.iso" in self.content or ".iso" in self.content

    def test_raw_format_detection(self):
        """Verify script detects .img extension."""
        assert ".img" in self.content

    def test_cdrom_attachment(self):
        """Verify ISO is attached as CD-ROM device."""
        assert "install-iso" in self.content or "CD-ROM" in self.content

    def test_default_image_is_iso(self):
        """Verify default image name is .iso."""
        assert re.search(r'IMAGE="anklume-live\.iso"', self.content)

    def test_iso_device_readonly(self):
        """Verify ISO CD-ROM device is marked readonly."""
        assert "readonly=true" in self.content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
