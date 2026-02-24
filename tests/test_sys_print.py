"""Tests for scripts/sys-print.sh — CUPS print service management."""

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from conftest import read_log

PRINT_SH = Path(__file__).resolve().parent.parent / "scripts" / "sys-print.sh"

# Fake Incus JSON output: two instances across two projects
FAKE_INCUS_LIST = json.dumps([
    {"name": "sys-print", "project": "print-service", "status": "Running"},
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

# exec (apt-get, systemctl, lpstat, etc.)
if [[ "$1" == "exec" ]]; then
    # systemctl status cups
    if [[ "$*" == *"status cups"* ]]; then
        echo "cups.service - CUPS Scheduler"
        echo "   Active: active (running)"
        exit 0
    fi
    # lpstat -p
    if [[ "$*" == *"lpstat"* ]]; then
        echo "printer HP_LaserJet is idle."
        exit 0
    fi
    exit 0
fi

# file push (config files)
if [[ "$1" == "file" && "$2" == "push" ]]; then
    cat > /dev/null
    exit 0
fi

# config device add (USB and NIC)
if [[ "$1" == "config" && "$2" == "device" && "$3" == "add" ]]; then
    exit 0
fi

# config show (for status)
if [[ "$1" == "config" && "$2" == "show" ]]; then
    echo "devices: {{}}"
    exit 0
fi

echo "mock: unhandled command: $*" >&2
exit 1
""")
    mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env["PATH"] = f"{mock_bin}:{env['PATH']}"
    return env, log_file


def run_print(args, env):
    """Run sys-print.sh with given args and environment."""
    return subprocess.run(
        ["bash", str(PRINT_SH)] + args,
        capture_output=True, text=True, env=env,
    )


# ── shellcheck + executable ──────────────────────────────────


class TestScriptQuality:
    @pytest.mark.skipif(not shutil.which("shellcheck"), reason="shellcheck not installed")
    def test_script_shellcheck_clean(self):
        """sys-print.sh passes shellcheck."""
        result = subprocess.run(
            ["shellcheck", str(PRINT_SH)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"shellcheck errors:\n{result.stdout}"

    def test_script_executable(self):
        """sys-print.sh has the executable bit set."""
        assert os.access(PRINT_SH, os.X_OK)


# ── help ─────────────────────────────────────────────────────


class TestHelp:
    def test_help_flag(self):
        """--help shows usage and exits 0."""
        result = subprocess.run(
            ["bash", str(PRINT_SH), "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "Usage:" in result.stdout
        assert "setup" in result.stdout
        assert "add-usb" in result.stdout
        assert "add-network" in result.stdout
        assert "status" in result.stdout

    def test_no_args_shows_usage(self):
        """No arguments shows usage and exits 0."""
        result = subprocess.run(
            ["bash", str(PRINT_SH)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "Usage:" in result.stdout


# ── setup ────────────────────────────────────────────────────


class TestSetup:
    def test_setup_requires_instance(self, mock_env):
        """setup without instance name fails."""
        env, _ = mock_env
        result = run_print(["setup"], env)
        assert result.returncode != 0
        assert "Usage:" in result.stderr or "ERROR:" in result.stderr

    def test_setup_installs_and_configures(self, mock_env):
        """setup installs CUPS and pushes configuration."""
        env, log = mock_env
        result = run_print(["setup", "sys-print"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        # Should exec apt-get install (via bash -c)
        assert any("exec" in c and "sys-print" in c for c in cmds)
        # Should push cupsd.conf via file push
        assert any("file push" in c and "cupsd.conf" in c for c in cmds)
        # Should enable and restart cups
        assert any("systemctl" in c and "enable" in c and "cups" in c for c in cmds)
        assert any("systemctl" in c and "restart" in c and "cups" in c for c in cmds)

    def test_setup_with_explicit_project(self, mock_env):
        """setup with --project skips auto-detection."""
        env, log = mock_env
        result = run_print(["setup", "sys-print", "--project", "print-service"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("--project" in c and "print-service" in c for c in cmds)
        assert not any("--all-projects" in c for c in cmds)

    def test_setup_output_message(self, mock_env):
        """setup shows completion message with web interface URL."""
        env, _ = mock_env
        result = run_print(["setup", "sys-print"], env)
        assert result.returncode == 0
        assert "Done" in result.stdout
        assert "631" in result.stdout


# ── add-usb ──────────────────────────────────────────────────


class TestAddUsb:
    def test_add_usb_requires_instance(self, mock_env):
        """add-usb without instance fails."""
        env, _ = mock_env
        result = run_print(["add-usb"], env)
        assert result.returncode != 0
        assert "Usage:" in result.stderr or "ERROR:" in result.stderr

    def test_add_usb_requires_vendor(self, mock_env):
        """add-usb without --vendor fails."""
        env, _ = mock_env
        result = run_print(["add-usb", "sys-print", "--product", "0005"], env)
        assert result.returncode != 0
        assert "vendor" in result.stderr.lower() or "ERROR" in result.stderr

    def test_add_usb_requires_product(self, mock_env):
        """add-usb without --product fails."""
        env, _ = mock_env
        result = run_print(["add-usb", "sys-print", "--vendor", "04b8"], env)
        assert result.returncode != 0
        assert "product" in result.stderr.lower() or "ERROR" in result.stderr

    def test_add_usb_adds_device(self, mock_env):
        """add-usb adds USB device to instance."""
        env, log = mock_env
        result = run_print(
            ["add-usb", "sys-print", "--vendor", "04b8", "--product", "0005"],
            env,
        )
        assert result.returncode == 0
        cmds = read_log(log)
        assert any(
            "config device add" in c and "usb" in c
            and "vendorid=04b8" in c and "productid=0005" in c
            for c in cmds
        )

    def test_add_usb_with_project(self, mock_env):
        """add-usb with --project passes it through."""
        env, log = mock_env
        result = run_print(
            ["add-usb", "sys-print", "--vendor", "04b8", "--product", "0005",
             "--project", "print-service"],
            env,
        )
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("--project" in c and "print-service" in c for c in cmds)


# ── add-network ──────────────────────────────────────────────


class TestAddNetwork:
    def test_add_network_requires_instance(self, mock_env):
        """add-network without instance fails."""
        env, _ = mock_env
        result = run_print(["add-network"], env)
        assert result.returncode != 0
        assert "Usage:" in result.stderr or "ERROR:" in result.stderr

    def test_add_network_requires_nic_parent(self, mock_env):
        """add-network without --nic-parent fails."""
        env, _ = mock_env
        result = run_print(["add-network", "sys-print"], env)
        assert result.returncode != 0
        assert "nic-parent" in result.stderr.lower() or "ERROR" in result.stderr

    def test_add_network_adds_macvlan(self, mock_env):
        """add-network adds macvlan NIC device."""
        env, log = mock_env
        result = run_print(
            ["add-network", "sys-print", "--nic-parent", "enp3s0"],
            env,
        )
        assert result.returncode == 0
        cmds = read_log(log)
        assert any(
            "config device add" in c and "nic" in c
            and "nictype=macvlan" in c and "parent=enp3s0" in c
            for c in cmds
        )

    def test_add_network_with_project(self, mock_env):
        """add-network with --project passes it through."""
        env, log = mock_env
        result = run_print(
            ["add-network", "sys-print", "--nic-parent", "enp3s0",
             "--project", "print-service"],
            env,
        )
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("--project" in c and "print-service" in c for c in cmds)


# ── status ───────────────────────────────────────────────────


class TestStatus:
    def test_status_requires_instance(self, mock_env):
        """status without instance name fails."""
        env, _ = mock_env
        result = run_print(["status"], env)
        assert result.returncode != 0
        assert "Usage:" in result.stderr or "ERROR:" in result.stderr

    def test_status_shows_cups_info(self, mock_env):
        """status queries systemctl and lpstat."""
        env, log = mock_env
        result = run_print(["status", "sys-print"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("systemctl" in c and "status" in c and "cups" in c for c in cmds)


# ── unknown command ──────────────────────────────────────────


class TestUnknown:
    def test_unknown_command(self):
        """Unknown subcommand gives clear error."""
        result = subprocess.run(
            ["bash", str(PRINT_SH), "badcmd"],
            capture_output=True, text=True,
        )
        assert result.returncode != 0
        assert "Unknown command" in result.stderr
