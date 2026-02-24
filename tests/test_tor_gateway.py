"""Tests for scripts/tor-gateway.sh — Tor transparent proxy setup."""

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from conftest import read_log

TOR_SH = Path(__file__).resolve().parent.parent / "scripts" / "tor-gateway.sh"

# Fake Incus JSON output: two instances across two projects
FAKE_INCUS_LIST = json.dumps([
    {"name": "tor-gw", "project": "tor-gateway", "status": "Running"},
    {"name": "anklume-instance", "project": "anklume", "status": "Running"},
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
if [[ "$1" == "project" && "$2" == "list" ]]; then
    echo "default,YES,YES,YES,YES,YES,YES,Default,0"
    exit 0
fi

# list --all-projects (for find_project)
if [[ "$1" == "list" && "$*" == *"--all-projects"* ]]; then
    echo '{FAKE_INCUS_LIST}'
    exit 0
fi

# exec (apt-get, systemctl, nft, journalctl, etc.)
if [[ "$1" == "exec" ]]; then
    # systemctl is-active tor — simulate running
    if [[ "$*" == *"is-active"* ]]; then
        echo "active"
        exit 0
    fi
    # journalctl — simulate bootstrapped
    if [[ "$*" == *"journalctl"* ]]; then
        echo "Bootstrapped 100% (done)"
        exit 0
    fi
    # nft list table — simulate success
    if [[ "$*" == *"nft"*"list table"* ]]; then
        echo "table inet tor-redirect {{}}"
        exit 0
    fi
    exit 0
fi

# file push (config files)
if [[ "$1" == "file" && "$2" == "push" ]]; then
    cat > /dev/null
    exit 0
fi

echo "mock: unhandled command: $*" >&2
exit 1
""")
    mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env["PATH"] = f"{mock_bin}:{env['PATH']}"
    return env, log_file


def run_tor(args, env):
    """Run tor-gateway.sh with given args and environment."""
    return subprocess.run(
        ["bash", str(TOR_SH)] + args,
        capture_output=True, text=True, env=env,
    )


# ── shellcheck + executable ──────────────────────────────────


class TestScriptQuality:
    @pytest.mark.skipif(not shutil.which("shellcheck"), reason="shellcheck not installed")
    def test_script_shellcheck_clean(self):
        """tor-gateway.sh passes shellcheck."""
        result = subprocess.run(
            ["shellcheck", str(TOR_SH)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"shellcheck errors:\n{result.stdout}"

    def test_script_executable(self):
        """tor-gateway.sh has the executable bit set."""
        assert os.access(TOR_SH, os.X_OK)


# ── help ─────────────────────────────────────────────────────


class TestHelp:
    def test_help_flag(self):
        """--help shows usage and exits 0."""
        result = subprocess.run(
            ["bash", str(TOR_SH), "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "Usage:" in result.stdout
        assert "setup" in result.stdout
        assert "status" in result.stdout
        assert "verify" in result.stdout

    def test_no_args_shows_usage(self):
        """No arguments shows usage and exits 0."""
        result = subprocess.run(
            ["bash", str(TOR_SH)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "Usage:" in result.stdout


# ── setup ────────────────────────────────────────────────────


class TestSetup:
    def test_setup_requires_instance(self, mock_env):
        """setup without instance name fails."""
        env, _ = mock_env
        result = run_tor(["setup"], env)
        assert result.returncode != 0
        assert "Usage:" in result.stderr or "ERROR:" in result.stderr

    def test_setup_installs_and_configures(self, mock_env):
        """setup installs tor and configures the service."""
        env, log = mock_env
        result = run_tor(["setup", "tor-gw"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        # Should exec apt-get install (via bash -c)
        assert any("exec" in c and "tor-gw" in c for c in cmds)
        # Should push torrc config via file push
        assert any("file push" in c and "torrc" in c for c in cmds)
        # Should push nftables config
        assert any("file push" in c and "tor-redirect" in c for c in cmds)
        # Should enable and restart tor
        assert any("systemctl" in c and "enable" in c and "tor" in c for c in cmds)
        assert any("systemctl" in c and "restart" in c and "tor" in c for c in cmds)

    def test_setup_with_explicit_project(self, mock_env):
        """setup with --project skips auto-detection."""
        env, log = mock_env
        result = run_tor(["setup", "tor-gw", "--project", "tor-gateway"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        # Project should appear in exec commands
        assert any("--project" in c and "tor-gateway" in c for c in cmds)
        # Should NOT have called list --all-projects (project was given)
        assert not any("--all-projects" in c for c in cmds)

    def test_setup_output_message(self, mock_env):
        """setup shows completion message."""
        env, _ = mock_env
        result = run_tor(["setup", "tor-gw"], env)
        assert result.returncode == 0
        assert "Done" in result.stdout
        assert "Tor transparent proxy" in result.stdout


# ── status ───────────────────────────────────────────────────


class TestStatus:
    def test_status_requires_instance(self, mock_env):
        """status without instance name fails."""
        env, _ = mock_env
        result = run_tor(["status"], env)
        assert result.returncode != 0
        assert "Usage:" in result.stderr or "ERROR:" in result.stderr

    def test_status_shows_info(self, mock_env):
        """status queries systemctl and nftables."""
        env, log = mock_env
        result = run_tor(["status", "tor-gw"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("systemctl" in c and "status" in c and "tor" in c for c in cmds)


# ── verify ───────────────────────────────────────────────────


class TestVerify:
    def test_verify_requires_instance(self, mock_env):
        """verify without instance name fails."""
        env, _ = mock_env
        result = run_tor(["verify"], env)
        assert result.returncode != 0
        assert "Usage:" in result.stderr or "ERROR:" in result.stderr

    def test_verify_checks_tor(self, mock_env):
        """verify checks service, circuit, and nftables."""
        env, log = mock_env
        result = run_tor(["verify", "tor-gw"], env)
        assert result.returncode == 0
        assert "Tor service: running" in result.stdout
        assert "Tor circuit: established" in result.stdout
        assert "nftables redirect: active" in result.stdout

    def test_verify_with_project(self, mock_env):
        """verify with --project passes it through."""
        env, log = mock_env
        result = run_tor(["verify", "tor-gw", "--project", "tor-gateway"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("--project" in c and "tor-gateway" in c for c in cmds)


# ── unknown command ──────────────────────────────────────────


class TestUnknown:
    def test_unknown_command(self):
        """Unknown subcommand gives clear error."""
        result = subprocess.run(
            ["bash", str(TOR_SH), "badcmd"],
            capture_output=True, text=True,
        )
        assert result.returncode != 0
        assert "Unknown command" in result.stderr
