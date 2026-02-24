"""Tests for scripts/golden.sh — golden image management."""

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

GOLDEN_SH = Path(__file__).resolve().parent.parent / "scripts" / "golden.sh"

# Fake Incus JSON output: two instances across two projects
FAKE_INCUS_LIST = json.dumps([
    {"name": "pro-dev", "project": "pro", "status": "Running"},
    {"name": "anklume-instance", "project": "anklume", "status": "Stopped"},
])

FAKE_PROJECT_LIST = json.dumps([
    {"name": "default"},
    {"name": "anklume"},
    {"name": "pro"},
])

# Instance with pristine snapshot
FAKE_SNAPSHOT_LIST_WITH_PRISTINE = json.dumps([
    {"name": "pristine", "created_at": "2026-01-15T10:00:00"},
])

FAKE_SNAPSHOT_LIST_EMPTY = json.dumps([])

# Instance list for a project (used by create and list)
FAKE_PRO_INSTANCES = json.dumps([
    {
        "name": "pro-dev",
        "status": "Running",
        "snapshots": [{"name": "pristine", "created_at": "2026-01-15T10:00:00"}],
    },
])

FAKE_ANKLUME_INSTANCES = json.dumps([
    {
        "name": "anklume-instance",
        "status": "Stopped",
        "snapshots": None,
    },
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

# project list
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format json"* ]]; then
    echo '{FAKE_PROJECT_LIST}'
    exit 0
fi
if [[ "$1" == "project" && "$2" == "list" ]]; then
    echo "default,YES"
    exit 0
fi

# list --all-projects (for find_project)
if [[ "$1" == "list" && "$*" == *"--all-projects"* ]]; then
    echo '{FAKE_INCUS_LIST}'
    exit 0
fi

# list --project anklume (check before pro since --project contains "pro")
if [[ "$1" == "list" && "$*" == *"--project"* && "$*" == *"anklume"* && "$*" == *"--format json"* ]]; then
    echo '{FAKE_ANKLUME_INSTANCES}'
    exit 0
fi

# list --project pro
if [[ "$1" == "list" && "$*" == *"--project"* && "$*" == *"pro"* && "$*" == *"--format json"* ]]; then
    echo '{FAKE_PRO_INSTANCES}'
    exit 0
fi

# list --project default (empty)
if [[ "$1" == "list" && "$*" == *"--format json"* ]]; then
    echo '[]'
    exit 0
fi

# snapshot list (with pristine)
if [[ "$1" == "snapshot" && "$2" == "list" && "$*" == *"pro-dev"* && "$*" == *"--format json"* ]]; then
    echo '{FAKE_SNAPSHOT_LIST_WITH_PRISTINE}'
    exit 0
fi

# snapshot list (empty)
if [[ "$1" == "snapshot" && "$2" == "list" && "$*" == *"--format json"* ]]; then
    echo '{FAKE_SNAPSHOT_LIST_EMPTY}'
    exit 0
fi

# snapshot create / delete / copy / publish / stop — succeed
if [[ "$1" == "snapshot" || "$1" == "stop" || "$1" == "copy" || "$1" == "publish" ]]; then
    exit 0
fi

echo "mock: unhandled command: $*" >&2
exit 1
""")
    mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env["PATH"] = f"{mock_bin}:{env['PATH']}"
    return env, log_file


def run_golden(args, env, input_text=None):
    """Run golden.sh with given args and environment."""
    return subprocess.run(
        ["bash", str(GOLDEN_SH)] + args,
        capture_output=True, text=True, env=env, input=input_text,
    )


def read_log(log_file):
    """Return list of incus commands from the log file."""
    if log_file.exists():
        return [line.strip() for line in log_file.read_text().splitlines() if line.strip()]
    return []


# ── shellcheck + executable ──────────────────────────────────────


class TestScriptQuality:
    @pytest.mark.skipif(not shutil.which("shellcheck"), reason="shellcheck not installed")
    def test_script_shellcheck_clean(self):
        """golden.sh passes shellcheck."""
        result = subprocess.run(
            ["shellcheck", str(GOLDEN_SH)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"shellcheck errors:\n{result.stdout}"

    def test_script_executable(self):
        """golden.sh has the executable bit set."""
        assert os.access(GOLDEN_SH, os.X_OK)


# ── help ──────────────────────────────────────────────────────────


class TestHelp:
    def test_help_flag(self):
        """--help shows usage and exits 0."""
        result = subprocess.run(
            ["bash", str(GOLDEN_SH), "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "Usage:" in result.stdout
        assert "create" in result.stdout
        assert "derive" in result.stdout
        assert "publish" in result.stdout

    def test_no_args_shows_usage(self):
        """No arguments shows usage and exits 0."""
        result = subprocess.run(
            ["bash", str(GOLDEN_SH)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "Usage:" in result.stdout


# ── create ────────────────────────────────────────────────────────


class TestCreate:
    def test_create_subcommand_requires_name(self, mock_env):
        """create without instance name fails."""
        env, _ = mock_env
        result = run_golden(["create"], env)
        assert result.returncode != 0
        assert "Usage:" in result.stderr or "ERROR:" in result.stderr

    def test_create_stops_and_snapshots(self, mock_env):
        """create stops a running instance and creates pristine snapshot."""
        env, log = mock_env
        result = run_golden(["create", "pro-dev"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("stop pro-dev --project pro" in c for c in cmds)
        # Should delete existing pristine then create new one
        assert any("snapshot create pro-dev pristine --project pro" in c for c in cmds)

    def test_create_with_explicit_project(self, mock_env):
        """create with --project skips auto-detection."""
        env, log = mock_env
        result = run_golden(["create", "pro-dev", "--project", "pro"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("snapshot create pro-dev pristine --project pro" in c for c in cmds)

    def test_create_already_stopped(self, mock_env):
        """create on a stopped instance skips the stop step."""
        env, log = mock_env
        result = run_golden(["create", "anklume-instance"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        # Should NOT have a stop command (already stopped)
        assert not any("stop anklume-instance" in c for c in cmds)
        assert any("snapshot create anklume-instance pristine --project anklume" in c for c in cmds)


# ── derive ────────────────────────────────────────────────────────


class TestDerive:
    def test_derive_subcommand_requires_args(self, mock_env):
        """derive without arguments fails."""
        env, _ = mock_env
        result = run_golden(["derive"], env)
        assert result.returncode != 0
        assert "Usage:" in result.stderr or "ERROR:" in result.stderr

    def test_derive_single_arg_fails(self, mock_env):
        """derive with only template name fails."""
        env, _ = mock_env
        result = run_golden(["derive", "pro-dev"], env)
        assert result.returncode != 0

    def test_derive_creates_copy(self, mock_env):
        """derive creates a copy from template/pristine."""
        env, log = mock_env
        result = run_golden(["derive", "pro-dev", "pro-dev-copy"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("copy pro-dev/pristine pro-dev-copy --project pro" in c for c in cmds)

    def test_derive_with_project(self, mock_env):
        """derive with --project passes it through."""
        env, log = mock_env
        result = run_golden(["derive", "pro-dev", "new-instance", "--project", "pro"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("copy pro-dev/pristine new-instance --project pro" in c for c in cmds)


# ── publish ───────────────────────────────────────────────────────


class TestPublish:
    def test_publish_subcommand_requires_args(self, mock_env):
        """publish without arguments fails."""
        env, _ = mock_env
        result = run_golden(["publish"], env)
        assert result.returncode != 0
        assert "Usage:" in result.stderr or "ERROR:" in result.stderr

    def test_publish_single_arg_fails(self, mock_env):
        """publish with only template name fails."""
        env, _ = mock_env
        result = run_golden(["publish", "pro-dev"], env)
        assert result.returncode != 0

    def test_publish_creates_image(self, mock_env):
        """publish creates an image with the given alias."""
        env, log = mock_env
        result = run_golden(["publish", "pro-dev", "golden-pro"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any(
            "publish pro-dev/pristine --project pro --alias golden-pro" in c
            for c in cmds
        )


# ── list ──────────────────────────────────────────────────────────


class TestList:
    def test_list_runs(self, mock_env):
        """list command runs successfully."""
        env, _ = mock_env
        result = run_golden(["list"], env)
        assert result.returncode == 0
        assert "Golden images" in result.stdout

    def test_list_with_project(self, mock_env):
        """list with --project filters to that project."""
        env, log = mock_env
        result = run_golden(["list", "--project", "pro"], env)
        assert result.returncode == 0


# ── unknown command ───────────────────────────────────────────────


class TestUnknown:
    def test_unknown_command(self):
        """Unknown subcommand gives clear error."""
        result = subprocess.run(
            ["bash", str(GOLDEN_SH), "badcmd"],
            capture_output=True, text=True,
        )
        assert result.returncode != 0
        assert "Unknown command" in result.stderr
