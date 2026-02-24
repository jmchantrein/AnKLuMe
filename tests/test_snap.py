"""Tests for scripts/snap.sh — snapshot management."""

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest
from conftest import read_log

SNAP_SH = Path(__file__).resolve().parent.parent / "scripts" / "snap.sh"

# Fake Incus JSON output: two instances across two projects
FAKE_INCUS_LIST = json.dumps([
    {"name": "anklume-instance", "project": "anklume", "status": "Running"},
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
if [[ "$1" == "project" && "$2" == "list" ]]; then
    echo "default,YES,YES,YES,YES,YES,YES,Default,0"
    exit 0
fi
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


# ── create ───────────────────────────────────────────────────


class TestCreate:
    def test_create_with_name(self, mock_env):
        env, log = mock_env
        result = run_snap(["create", "anklume-instance", "my-snap"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("snapshot create anklume-instance my-snap --project anklume" in c for c in cmds)

    def test_create_auto_name(self, mock_env):
        env, log = mock_env
        result = run_snap(["create", "anklume-instance"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("snapshot create anklume-instance snap-" in c for c in cmds)

    def test_create_unknown_instance(self, mock_env):
        env, _ = mock_env
        result = run_snap(["create", "nonexistent", "s1"], env)
        assert result.returncode != 0
        assert "not found" in result.stderr.lower()


# ── restore ──────────────────────────────────────────────────


class TestRestore:
    def test_restore(self, mock_env):
        env, log = mock_env
        result = run_snap(["restore", "dev-workspace", "my-snap"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("snapshot restore dev-workspace my-snap --project work" in c for c in cmds)

    def test_self_restore_requires_confirmation(self, mock_env):
        env, _ = mock_env
        env["HOSTNAME"] = "anklume-instance"
        result = run_snap(["restore", "self", "my-snap"], env, input_text="no\n")
        assert result.returncode != 0
        assert "WARNING" in result.stdout or "WARNING" in result.stderr

    def test_self_restore_confirm_yes(self, mock_env):
        """Typing 'yes' at the self-restore prompt proceeds with restore."""
        env, log = mock_env
        env["HOSTNAME"] = "anklume-instance"
        result = run_snap(["restore", "self", "my-snap"], env, input_text="yes\n")
        assert result.returncode == 0
        cmds = read_log(log)
        assert any(
            "snapshot restore anklume-instance my-snap --project anklume" in c
            for c in cmds
        )

    def test_self_restore_with_force(self, mock_env):
        env, log = mock_env
        env["HOSTNAME"] = "anklume-instance"
        result = run_snap(["restore", "--force", "self", "my-snap"], env)
        assert result.returncode == 0


# ── list ─────────────────────────────────────────────────────


class TestList:
    def test_list_instance(self, mock_env):
        env, log = mock_env
        result = run_snap(["list", "anklume-instance"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("snapshot list anklume-instance" in c for c in cmds)

    def test_list_all(self, mock_env):
        env, log = mock_env
        result = run_snap(["list"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("anklume-instance" in c for c in cmds)
        assert any("dev-workspace" in c for c in cmds)


# ── delete ───────────────────────────────────────────────────


class TestDelete:
    def test_delete(self, mock_env):
        env, log = mock_env
        result = run_snap(["delete", "anklume-instance", "my-snap"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("snapshot delete anklume-instance my-snap --project anklume" in c for c in cmds)


# ── self detection ───────────────────────────────────────────


class TestSelf:
    def test_self_resolves_hostname(self, mock_env):
        env, log = mock_env
        env["HOSTNAME"] = "dev-workspace"
        result = run_snap(["create", "self", "test-snap"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("snapshot create dev-workspace test-snap --project work" in c for c in cmds)

    def test_self_unknown_hostname(self, mock_env):
        """Self with unknown HOSTNAME gives an error."""
        env, _ = mock_env
        env["HOSTNAME"] = "nonexistent-machine"
        result = run_snap(["create", "self", "snap1"], env)
        assert result.returncode != 0
        assert "not found" in result.stderr.lower()


# ── project resolution ───────────────────────────────────────


class TestSnapProjectResolution:
    def test_instance_found_in_non_default_project(self, mock_env):
        """Instance dev-workspace found in 'work' project → correct --project flag."""
        env, log = mock_env
        result = run_snap(["create", "dev-workspace"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any(
            "snapshot create dev-workspace" in c and "--project work" in c
            for c in cmds
        )

    def test_instance_not_found_gives_error(self, mock_env):
        """Instance not in any project → clear error message."""
        env, _ = mock_env
        result = run_snap(["create", "nonexistent-instance"], env)
        assert result.returncode != 0
        assert "not found" in result.stderr


# ── force flag ───────────────────────────────────────────────


class TestForceFlag:
    def test_force_skips_warning(self, mock_env):
        """Force flag suppresses self-restore WARNING output."""
        env, log = mock_env
        env["HOSTNAME"] = "anklume-instance"
        result = run_snap(["restore", "--force", "self", "snap1"], env)
        assert result.returncode == 0
        assert "WARNING" not in result.stdout

    def test_force_resolves_self_correctly(self, mock_env):
        """Force + self resolves self to hostname."""
        env, log = mock_env
        env["HOSTNAME"] = "dev-workspace"
        result = run_snap(["restore", "--force", "self", "snap1"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any(
            "snapshot restore dev-workspace snap1 --project work" in c
            for c in cmds
        )


# ── incus not available ──────────────────────────────────────


class TestIncusNotAvailable:
    def test_incus_not_available(self, tmp_path):
        """Script fails gracefully when incus binary is not found."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        bash_path = "/usr/bin/bash"
        if not os.path.exists(bash_path):
            bash_path = "/bin/bash"
        (mock_bin / "bash").symlink_to(bash_path)
        env = os.environ.copy()
        env["PATH"] = str(mock_bin)
        result = run_snap(["create", "test", "snap1"], env)
        assert result.returncode != 0
