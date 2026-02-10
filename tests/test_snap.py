"""Tests for scripts/snap.sh — snapshot management."""

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

SNAP_SH = Path(__file__).resolve().parent.parent / "scripts" / "snap.sh"

# Fake Incus JSON output: two instances across two projects
FAKE_INCUS_LIST = json.dumps([
    {"name": "admin-ansible", "project": "admin", "status": "Running"},
    {"name": "dev-workspace", "project": "work", "status": "Running"},
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
if [[ "$1" == "list" && "$*" == *"--all-projects"* ]]; then
    echo '{FAKE_INCUS_LIST}'
    exit 0
fi
if [[ "$1" == "snapshot" ]]; then
    exit 0
fi
echo "mock: unhandled command: $*" >&2
exit 1
""")
    mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env["PATH"] = f"{mock_bin}:{env['PATH']}"
    return env, log_file


def run_snap(args, env, input_text=None):
    """Run snap.sh with given args and environment."""
    result = subprocess.run(
        ["bash", str(SNAP_SH)] + args,
        capture_output=True, text=True, env=env, input=input_text,
    )
    return result


def read_log(log_file):
    """Return list of incus commands from the log file."""
    if log_file.exists():
        return [line.strip() for line in log_file.read_text().splitlines() if line.strip()]
    return []


# ── create ───────────────────────────────────────────────────


class TestCreate:
    def test_create_with_name(self, mock_env):
        env, log = mock_env
        result = run_snap(["create", "admin-ansible", "my-snap"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("snapshot create admin-ansible my-snap --project admin" in c for c in cmds)

    def test_create_auto_name(self, mock_env):
        env, log = mock_env
        result = run_snap(["create", "admin-ansible"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("snapshot create admin-ansible snap-" in c for c in cmds)

    def test_create_unknown_instance(self, mock_env):
        env, _ = mock_env
        result = run_snap(["create", "nonexistent", "s1"], env)
        assert result.returncode != 0
        assert "not found" in result.stderr.lower()

    def test_create_missing_args(self, mock_env):
        env, _ = mock_env
        result = run_snap(["create"], env)
        assert result.returncode != 0


# ── restore ──────────────────────────────────────────────────


class TestRestore:
    def test_restore(self, mock_env):
        env, log = mock_env
        result = run_snap(["restore", "dev-workspace", "my-snap"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("snapshot restore dev-workspace my-snap --project work" in c for c in cmds)

    def test_restore_missing_snap_name(self, mock_env):
        env, _ = mock_env
        result = run_snap(["restore", "admin-ansible"], env)
        assert result.returncode != 0

    def test_self_restore_requires_confirmation(self, mock_env):
        env, _ = mock_env
        env["HOSTNAME"] = "admin-ansible"
        result = run_snap(["restore", "self", "my-snap"], env, input_text="no\n")
        assert result.returncode != 0
        assert "WARNING" in result.stdout or "WARNING" in result.stderr

    def test_self_restore_with_force(self, mock_env):
        env, log = mock_env
        env["HOSTNAME"] = "admin-ansible"
        result = run_snap(["restore", "--force", "self", "my-snap"], env)
        assert result.returncode == 0


# ── list ─────────────────────────────────────────────────────


class TestList:
    def test_list_instance(self, mock_env):
        env, log = mock_env
        result = run_snap(["list", "admin-ansible"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("snapshot list admin-ansible" in c for c in cmds)

    def test_list_all(self, mock_env):
        env, log = mock_env
        result = run_snap(["list"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("admin-ansible" in c for c in cmds)
        assert any("dev-workspace" in c for c in cmds)


# ── delete ───────────────────────────────────────────────────


class TestDelete:
    def test_delete(self, mock_env):
        env, log = mock_env
        result = run_snap(["delete", "admin-ansible", "my-snap"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("snapshot delete admin-ansible my-snap --project admin" in c for c in cmds)


# ── self detection ───────────────────────────────────────────


class TestSelf:
    def test_self_resolves_hostname(self, mock_env):
        env, log = mock_env
        env["HOSTNAME"] = "dev-workspace"
        result = run_snap(["create", "self", "test-snap"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("snapshot create dev-workspace test-snap --project work" in c for c in cmds)


# ── usage ────────────────────────────────────────────────────


class TestUsage:
    def test_help(self, mock_env):
        env, _ = mock_env
        result = run_snap(["help"], env)
        assert result.returncode == 0
        assert "Usage" in result.stdout

    def test_unknown_command(self, mock_env):
        env, _ = mock_env
        result = run_snap(["bogus"], env)
        assert result.returncode != 0
