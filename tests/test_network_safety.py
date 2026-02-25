"""Tests for scripts/network-safety-check.sh — network state backup/restore.

Covers: script existence, shellcheck, missing subcommand, backup subcommand
with mocked commands, restore-info subcommand with a fake backup file.
"""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = PROJECT_ROOT / "scripts" / "network-safety-check.sh"


def _make_executable(path: Path, content: str) -> None:
    """Write an executable shell script to path."""
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


class TestNetworkSafety:
    """Tests for network-safety-check.sh behavior."""

    def test_script_exists(self):
        """network-safety-check.sh exists and is executable."""
        assert SCRIPT.exists()
        assert os.access(SCRIPT, os.X_OK)

    @pytest.mark.skipif(
        shutil.which("shellcheck") is None,
        reason="shellcheck not installed",
    )
    def test_shellcheck(self):
        """network-safety-check.sh passes shellcheck."""
        result = subprocess.run(
            ["shellcheck", "--severity=warning", str(SCRIPT)],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, (
            f"shellcheck errors:\n{result.stdout}\n{result.stderr}"
        )

    def test_missing_subcommand_exits_nonzero(self):
        """Running with no subcommand exits non-zero with usage message."""
        env = os.environ.copy()
        env["HOME"] = "/tmp/anklume-test-netsafety"
        result = subprocess.run(
            ["bash", str(SCRIPT)],
            capture_output=True, text=True, env=env, timeout=10,
        )
        assert result.returncode != 0
        assert "Usage" in result.stdout or "usage" in result.stdout.lower()

    def test_invalid_subcommand_exits_nonzero(self):
        """Running with an invalid subcommand exits non-zero."""
        env = os.environ.copy()
        env["HOME"] = "/tmp/anklume-test-netsafety"
        result = subprocess.run(
            ["bash", str(SCRIPT), "invalid-subcommand"],
            capture_output=True, text=True, env=env, timeout=10,
        )
        assert result.returncode != 0

    def test_backup_creates_file(self, tmp_path):
        """backup subcommand creates a network state backup file.

        Mocks ip and nft commands with wrapper scripts that produce
        deterministic output.
        """
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()

        # Mock 'ip' command
        _make_executable(
            mock_bin / "ip",
            '#!/usr/bin/env bash\n'
            'if [[ "$*" == *"route show"* ]]; then\n'
            '    echo "default via 192.168.1.1 dev eth0"\n'
            '    echo "10.100.0.0/24 dev net-pro"\n'
            'elif [[ "$*" == *"link show"* ]]; then\n'
            '    echo "1: lo: <LOOPBACK,UP> mtu 65536"\n'
            '    echo "2: eth0: <BROADCAST,MULTICAST,UP> mtu 1500"\n'
            'elif [[ "$*" == *"route get"* ]]; then\n'
            '    echo "1.1.1.1 via 192.168.1.1 dev eth0 src 192.168.1.100"\n'
            'else\n'
            '    echo "mock ip: $*"\n'
            'fi\n'
        )

        # Mock 'nft' command
        _make_executable(
            mock_bin / "nft",
            '#!/usr/bin/env bash\n'
            'echo "table inet anklume {"\n'
            'echo "  chain forward {"\n'
            'echo "    type filter hook forward priority -1;"\n'
            'echo "  }"\n'
            'echo "}"\n'
        )

        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        env["HOME"] = str(tmp_path)

        result = subprocess.run(
            ["bash", str(SCRIPT), "backup"],
            capture_output=True, text=True, env=env, timeout=10,
        )
        assert result.returncode == 0
        assert "backed up" in result.stdout.lower()

        # Verify backup file was created in the expected location
        backup_dir = tmp_path / ".anklume-network-backups"
        assert backup_dir.exists()
        backup_files = list(backup_dir.glob("network-*.txt"))
        assert len(backup_files) == 1

        # Verify backup content contains expected sections
        content = backup_files[0].read_text()
        assert "=== Routes ===" in content
        assert "=== nftables ===" in content
        assert "=== Interfaces ===" in content
        assert "=== Default gateway ===" in content

    def test_restore_info_shows_latest_backup(self, tmp_path):
        """restore-info subcommand displays the latest backup file."""
        backup_dir = tmp_path / ".anklume-network-backups"
        backup_dir.mkdir(parents=True)

        # Create a fake backup file
        backup_file = backup_dir / "network-20260225-120000.txt"
        backup_content = (
            "=== Routes ===\n"
            "default via 192.168.1.1 dev eth0\n"
            "\n"
            "=== nftables ===\n"
            "table inet anklume { }\n"
        )
        backup_file.write_text(backup_content)

        # Mock 'find' is not needed because the script uses the real
        # find against the backup directory. We just need HOME set.
        env = os.environ.copy()
        env["HOME"] = str(tmp_path)

        result = subprocess.run(
            ["bash", str(SCRIPT), "restore-info"],
            capture_output=True, text=True, env=env, timeout=10,
        )
        assert result.returncode == 0
        assert "Latest backup" in result.stdout
        assert "network-20260225-120000.txt" in result.stdout
        assert "=== Routes ===" in result.stdout

    def test_restore_info_no_backup_exits_nonzero(self, tmp_path):
        """restore-info with no backups exits non-zero."""
        env = os.environ.copy()
        env["HOME"] = str(tmp_path)

        # Ensure backup directory exists but is empty
        backup_dir = tmp_path / ".anklume-network-backups"
        backup_dir.mkdir(parents=True)

        result = subprocess.run(
            ["bash", str(SCRIPT), "restore-info"],
            capture_output=True, text=True, env=env, timeout=10,
        )
        assert result.returncode != 0
        assert "No backup found" in result.stderr

    def test_backup_multiple_creates_separate_files(self, tmp_path):
        """Multiple backup calls create separate timestamped files."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()

        # Minimal mocks for ip and nft
        _make_executable(
            mock_bin / "ip",
            '#!/usr/bin/env bash\necho "mock output"\n',
        )
        _make_executable(
            mock_bin / "nft",
            '#!/usr/bin/env bash\necho "mock nft"\n',
        )

        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        env["HOME"] = str(tmp_path)

        # Run backup twice (timestamps differ at sub-second precision
        # so we just verify at least 1 file exists after each call)
        subprocess.run(
            ["bash", str(SCRIPT), "backup"],
            capture_output=True, text=True, env=env, timeout=10,
        )
        backup_dir = tmp_path / ".anklume-network-backups"
        first_count = len(list(backup_dir.glob("network-*.txt")))
        assert first_count >= 1

        # Short sleep to ensure different timestamp
        import time
        time.sleep(1.1)

        subprocess.run(
            ["bash", str(SCRIPT), "backup"],
            capture_output=True, text=True, env=env, timeout=10,
        )
        second_count = len(list(backup_dir.glob("network-*.txt")))
        assert second_count >= 2
