"""Tests for scripts/transfer.sh — file transfer and backup."""

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from conftest import read_log

TRANSFER_SH = Path(__file__).resolve().parent.parent / "scripts" / "transfer.sh"

# Fake Incus JSON output: two instances across two projects
FAKE_INCUS_LIST = json.dumps([
    {"name": "anklume-instance", "project": "anklume", "status": "Running"},
    {"name": "pro-dev", "project": "pro", "status": "Running"},
    {"name": "perso-desktop", "project": "perso", "status": "Running"},
])


@pytest.fixture()
def mock_env(tmp_path):
    """Create a mock incus binary that logs calls and returns fake data."""
    mock_bin = tmp_path / "bin"
    mock_bin.mkdir()
    log_file = tmp_path / "incus.log"

    mock_incus = mock_bin / "incus"
    mock_incus.write_text(f"""#!/usr/bin/env bash
echo "$@" >> "{log_file}"
if [[ "$1" == "project" && "$2" == "list" ]]; then
    echo "default,YES,YES,YES,YES,YES,YES,Default,0"
    exit 0
fi
if [[ "$1" == "list" && "$*" == *"--all-projects"* ]]; then
    echo '{FAKE_INCUS_LIST}'
    exit 0
fi
if [[ "$1" == "file" && "$2" == "pull" ]]; then
    echo "mock-file-content"
    exit 0
fi
if [[ "$1" == "file" && "$2" == "push" ]]; then
    cat > /dev/null
    exit 0
fi
if [[ "$1" == "export" ]]; then
    # Create a fake backup file
    touch "$3"
    exit 0
fi
if [[ "$1" == "import" ]]; then
    exit 0
fi
echo "mock: unhandled command: $*" >&2
exit 1
""")
    mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env["PATH"] = f"{mock_bin}:{env['PATH']}"
    return env, log_file, tmp_path


def run_transfer(args, env, cwd=None):
    """Run transfer.sh with given args and environment."""
    result = subprocess.run(
        ["bash", str(TRANSFER_SH)] + args,
        capture_output=True, text=True, env=env, cwd=cwd,
    )
    return result


# ── shellcheck + executable ──────────────────────────────────


class TestScriptQuality:
    @pytest.mark.skipif(not shutil.which("shellcheck"), reason="shellcheck not installed")
    def test_script_shellcheck_clean(self):
        """transfer.sh passes shellcheck."""
        result = subprocess.run(
            ["shellcheck", str(TRANSFER_SH)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"shellcheck errors:\n{result.stdout}"

    def test_script_executable(self):
        """transfer.sh has the executable bit set."""
        assert os.access(TRANSFER_SH, os.X_OK)


# ── help ─────────────────────────────────────────────────────


class TestHelp:
    def test_help_flag(self):
        """--help shows usage without error."""
        result = subprocess.run(
            ["bash", str(TRANSFER_SH), "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "Usage:" in result.stdout
        assert "copy" in result.stdout
        assert "backup" in result.stdout
        assert "restore" in result.stdout

    def test_no_args_shows_usage(self):
        """No arguments shows usage."""
        result = subprocess.run(
            ["bash", str(TRANSFER_SH)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "Usage:" in result.stdout


# ── copy ─────────────────────────────────────────────────────


class TestCopy:
    def test_copy_requires_src_dst(self, mock_env):
        """copy without both args fails."""
        env, _, _ = mock_env
        result = run_transfer(["copy"], env)
        assert result.returncode != 0
        assert "Usage" in result.stderr or "ERROR" in result.stderr

    def test_copy_requires_colon_format(self, mock_env):
        """copy with invalid format fails."""
        env, _, _ = mock_env
        result = run_transfer(["copy", "pro-dev", "anklume-instance:/tmp/x"], env)
        assert result.returncode != 0
        assert "Invalid format" in result.stderr

    def test_copy_between_instances(self, mock_env):
        """copy pipes file pull to file push with correct projects."""
        env, log, _ = mock_env
        result = run_transfer(["copy", "pro-dev:/etc/hosts", "anklume-instance:/tmp/hosts"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("file pull" in c and "--project pro" in c for c in cmds)
        assert any("file push" in c and "--project anklume" in c for c in cmds)

    def test_copy_unknown_instance(self, mock_env):
        """copy with unknown instance fails."""
        env, _, _ = mock_env
        result = run_transfer(["copy", "nonexistent:/etc/x", "pro-dev:/tmp/x"], env)
        assert result.returncode != 0
        assert "not found" in result.stderr.lower()


# ── backup ────────────────────────────────────────────────────


class TestBackup:
    def test_backup_requires_instance(self, mock_env):
        """backup without instance fails."""
        env, _, _ = mock_env
        result = run_transfer(["backup"], env)
        assert result.returncode != 0
        assert "Usage" in result.stderr or "ERROR" in result.stderr

    def test_backup_creates_file(self, mock_env):
        """backup exports instance to backups/ directory."""
        env, log, tmp = mock_env
        result = run_transfer(["backup", "anklume-instance", "--output", str(tmp / "backups")], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("export anklume-instance" in c and "--project anklume" in c for c in cmds)

    def test_backup_unknown_instance(self, mock_env):
        """backup with unknown instance fails."""
        env, _, _ = mock_env
        result = run_transfer(["backup", "nonexistent"], env)
        assert result.returncode != 0
        assert "not found" in result.stderr.lower()


# ── restore ───────────────────────────────────────────────────


class TestRestore:
    def test_restore_requires_file(self, mock_env):
        """restore without file fails."""
        env, _, _ = mock_env
        result = run_transfer(["restore"], env)
        assert result.returncode != 0
        assert "Usage" in result.stderr or "ERROR" in result.stderr

    def test_restore_missing_file(self, mock_env):
        """restore with nonexistent file fails."""
        env, _, _ = mock_env
        result = run_transfer(["restore", "/nonexistent/backup.tar.gz"], env)
        assert result.returncode != 0
        assert "not found" in result.stderr.lower()

    def test_restore_from_file(self, mock_env):
        """restore imports from a backup file."""
        env, log, tmp = mock_env
        backup_file = tmp / "test-backup.tar.gz"
        backup_file.touch()
        result = run_transfer(["restore", str(backup_file)], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("import" in c for c in cmds)

    def test_restore_with_name(self, mock_env):
        """restore --name passes --alias to incus import."""
        env, log, tmp = mock_env
        backup_file = tmp / "test-backup.tar.gz"
        backup_file.touch()
        result = run_transfer(["restore", "--name", "new-instance", str(backup_file)], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("import" in c and "--alias new-instance" in c for c in cmds)

    def test_restore_with_project(self, mock_env):
        """restore --project passes --project to incus import."""
        env, log, tmp = mock_env
        backup_file = tmp / "test-backup.tar.gz"
        backup_file.touch()
        result = run_transfer(["restore", "--project", "homelab", str(backup_file)], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("import" in c and "--project homelab" in c for c in cmds)


# ── parse instance:path ──────────────────────────────────────


class TestParseInstancePath:
    def test_valid_format(self, mock_env):
        """Valid instance:/path format parses correctly (tested via copy)."""
        env, log, _ = mock_env
        result = run_transfer(["copy", "pro-dev:/etc/hosts", "perso-desktop:/tmp/hosts"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        # Verify both source and destination were parsed correctly
        assert any("file pull" in c and "pro-dev" in c for c in cmds)
        assert any("file push" in c and "perso-desktop" in c for c in cmds)

    def test_missing_path(self, mock_env):
        """instance: without path fails."""
        env, _, _ = mock_env
        result = run_transfer(["copy", "pro-dev:", "anklume-instance:/tmp/x"], env)
        assert result.returncode != 0
        assert "Invalid format" in result.stderr or "ERROR" in result.stderr

    def test_missing_instance(self, mock_env):
        """:/path without instance fails."""
        env, _, _ = mock_env
        result = run_transfer(["copy", ":/etc/hosts", "anklume-instance:/tmp/x"], env)
        assert result.returncode != 0
        assert "Invalid format" in result.stderr or "ERROR" in result.stderr


# ── unknown command ──────────────────────────────────────────


class TestUnknownCommand:
    def test_unknown_command(self):
        """Unknown subcommand gives error."""
        result = subprocess.run(
            ["bash", str(TRANSFER_SH), "invalid"],
            capture_output=True, text=True,
        )
        assert result.returncode != 0
        assert "Unknown command" in result.stderr
