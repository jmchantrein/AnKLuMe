"""Tests for scripts/incus-guard.sh — consolidated Incus network guard."""

import os
import stat
import subprocess
from pathlib import Path

import pytest

GUARD_SH = Path(__file__).resolve().parent.parent / "scripts" / "incus-guard.sh"


@pytest.fixture()
def mock_env(tmp_path):
    """Create a mock environment with fake ip, incus, systemctl, ping binaries."""
    mock_bin = tmp_path / "bin"
    mock_bin.mkdir()
    log_file = tmp_path / "commands.log"
    guard_state = tmp_path / "incus-guard-host-dev"

    # Mock ip command: returns fake network info
    mock_ip = mock_bin / "ip"
    mock_ip.write_text(f"""#!/usr/bin/env bash
echo "ip $@" >> "{log_file}"
if [[ "$*" == "route show default" ]]; then
    echo "default via 192.168.1.1 dev eth0 proto static"
    exit 0
fi
if [[ "$*" == *"-4 addr show eth0"* ]]; then
    echo "    inet 192.168.1.100/24 brd 192.168.1.255 scope global eth0"
    exit 0
fi
if [[ "$*" == *"-o link show type bridge"* ]]; then
    echo "10: net-test: <BROADCAST> mtu 1500"
    exit 0
fi
if [[ "$*" == *"-o link show"* ]]; then
    echo "10: net-test: <BROADCAST> mtu 1500"
    exit 0
fi
if [[ "$*" == *"-4 addr show net-"* ]]; then
    echo "    inet 192.168.1.1/24 brd 192.168.1.255 scope global net-test"
    exit 0
fi
if [[ "$*" == *"link set"* || "$*" == *"link delete"* ]]; then
    exit 0
fi
if [[ "$*" == *"route add"* ]]; then
    exit 0
fi
exit 0
""")
    mock_ip.chmod(mock_ip.stat().st_mode | stat.S_IEXEC)

    # Mock incus command
    mock_incus = mock_bin / "incus"
    mock_incus.write_text(f"""#!/usr/bin/env bash
echo "incus $@" >> "{log_file}"
if [[ "$1" == "network" && "$2" == "list" ]]; then
    echo "net-test,bridge,YES,YES"
    exit 0
fi
if [[ "$1" == "network" && "$2" == "get" ]]; then
    echo "192.168.1.1/24"
    exit 0
fi
if [[ "$1" == "network" && "$2" == "delete" ]]; then
    exit 0
fi
exit 0
""")
    mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)

    # Mock systemctl
    mock_systemctl = mock_bin / "systemctl"
    mock_systemctl.write_text(f"""#!/usr/bin/env bash
echo "systemctl $@" >> "{log_file}"
if [[ "$*" == "is-active --quiet incus" ]]; then
    exit 1  # Not running by default
fi
exit 0
""")
    mock_systemctl.chmod(mock_systemctl.stat().st_mode | stat.S_IEXEC)

    # Mock ping
    mock_ping = mock_bin / "ping"
    mock_ping.write_text(f"""#!/usr/bin/env bash
echo "ping $@" >> "{log_file}"
exit 0
""")
    mock_ping.chmod(mock_ping.stat().st_mode | stat.S_IEXEC)

    # Mock sleep (instant)
    mock_sleep = mock_bin / "sleep"
    mock_sleep.write_text("#!/usr/bin/env bash\nexit 0\n")
    mock_sleep.chmod(mock_sleep.stat().st_mode | stat.S_IEXEC)

    # Mock date
    mock_date = mock_bin / "date"
    mock_date.write_text('#!/usr/bin/env bash\necho "2026-01-01T00:00:00+00:00"\n')
    mock_date.chmod(mock_date.stat().st_mode | stat.S_IEXEC)

    # Mock tee (just pass through)
    mock_tee = mock_bin / "tee"
    mock_tee.write_text("#!/usr/bin/env bash\ncat\n")
    mock_tee.chmod(mock_tee.stat().st_mode | stat.S_IEXEC)

    # Mock install
    mock_install_cmd = mock_bin / "install"
    mock_install_cmd.write_text(f"""#!/usr/bin/env bash
echo "install $@" >> "{log_file}"
exit 0
""")
    mock_install_cmd.chmod(mock_install_cmd.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env["PATH"] = f"{mock_bin}:{env['PATH']}"
    env["LOGFILE"] = str(tmp_path / "guard.log")

    # Override GUARD_STATE to use tmp_path
    return env, log_file, tmp_path


def run_guard(args, env, tmp_path):
    """Run incus-guard.sh with given args and environment."""
    # Create a wrapper that overrides paths
    wrapper = tmp_path / "run-guard.sh"
    wrapper.write_text(f"""#!/usr/bin/env bash
export LOGFILE="{tmp_path}/guard.log"
# Override guard state path in the script
export GUARD_STATE="{tmp_path}/incus-guard-host-dev"
# Source the guard script with modified variables
sed 's|LOGFILE=.*|LOGFILE="{tmp_path}/guard.log"|;s|GUARD_STATE=.*|GUARD_STATE="{tmp_path}/incus-guard-host-dev"|;s|GUARD_SCRIPT_INSTALL=.*|GUARD_SCRIPT_INSTALL="{tmp_path}/installed-guard.sh"|;s|DROPIN_DIR=.*|DROPIN_DIR="{tmp_path}/dropin"|;s|DROPIN_FILE=.*|DROPIN_FILE="{tmp_path}/dropin/network-guard.conf"|' "{GUARD_SH}" > "{tmp_path}/guard-patched.sh"
chmod +x "{tmp_path}/guard-patched.sh"
bash "{tmp_path}/guard-patched.sh" "$@"
""")
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IEXEC)

    result = subprocess.run(
        ["bash", str(wrapper)] + args,
        capture_output=True, text=True, env=env, timeout=10,
    )
    return result


def read_log(log_file):
    """Return list of commands from the log file."""
    if log_file.exists():
        return [line.strip() for line in log_file.read_text().splitlines() if line.strip()]
    return []


# ── help / no args ──────────────────────────────────────────


class TestHelp:
    def test_no_args_shows_usage(self, mock_env):
        env, log_file, tmp_path = mock_env
        result = run_guard([], env, tmp_path)
        assert result.returncode != 0
        assert "Usage" in result.stdout or "Usage" in result.stderr

    def test_help_flag(self, mock_env):
        env, log_file, tmp_path = mock_env
        result = run_guard(["--help"], env, tmp_path)
        assert "start" in result.stdout
        assert "post-start" in result.stdout
        assert "install" in result.stdout

    def test_unknown_subcommand(self, mock_env):
        env, log_file, tmp_path = mock_env
        result = run_guard(["invalid"], env, tmp_path)
        assert result.returncode != 0
        assert "Unknown subcommand" in result.stderr or "ERROR" in result.stderr


# ── post-start ──────────────────────────────────────────────


class TestPostStart:
    def test_post_start_detects_conflicts(self, mock_env):
        env, log_file, tmp_path = mock_env
        result = run_guard(["post-start"], env, tmp_path)
        assert result.returncode == 0
        cmds = read_log(log_file)
        # Should have called ip route show default
        assert any("ip route show default" in c for c in cmds)

    def test_post_start_cleans_incus_db(self, mock_env):
        env, log_file, tmp_path = mock_env
        result = run_guard(["post-start"], env, tmp_path)
        assert result.returncode == 0
        cmds = read_log(log_file)
        # Should detect and attempt to clean conflicting networks
        assert any("ip" in c and "link show type bridge" in c for c in cmds)

    def test_post_start_exits_zero_on_no_route(self, mock_env):
        """Post-start should not block Incus if network detection fails."""
        env, log_file, tmp_path = mock_env
        # Override ip to return nothing for route
        mock_ip = Path(env["PATH"].split(":")[0]) / "ip"
        mock_ip.write_text(f"""#!/usr/bin/env bash
echo "ip $@" >> "{log_file}"
exit 0
""")
        mock_ip.chmod(mock_ip.stat().st_mode | stat.S_IEXEC)
        result = run_guard(["post-start"], env, tmp_path)
        # Should exit 0 even with failure — don't block Incus
        assert result.returncode == 0


# ── start ───────────────────────────────────────────────────


class TestStart:
    def test_start_invokes_systemctl(self, mock_env):
        env, log_file, tmp_path = mock_env
        result = run_guard(["start"], env, tmp_path)
        assert result.returncode == 0
        cmds = read_log(log_file)
        assert any("systemctl start incus" in c for c in cmds)

    def test_start_verifies_connectivity(self, mock_env):
        env, log_file, tmp_path = mock_env
        result = run_guard(["start"], env, tmp_path)
        assert result.returncode == 0
        assert "Network connectivity verified" in result.stdout

    def test_start_skips_if_already_running(self, mock_env):
        """If Incus is already running, skip systemctl start."""
        env, log_file, tmp_path = mock_env
        # Override systemctl to report incus as active
        mock_systemctl = Path(env["PATH"].split(":")[0]) / "systemctl"
        mock_systemctl.write_text(f"""#!/usr/bin/env bash
echo "systemctl $@" >> "{log_file}"
exit 0
""")
        mock_systemctl.chmod(mock_systemctl.stat().st_mode | stat.S_IEXEC)
        result = run_guard(["start"], env, tmp_path)
        assert result.returncode == 0
        assert "already running" in result.stdout


# ── install ─────────────────────────────────────────────────


class TestInstall:
    def test_install_creates_dropin(self, mock_env):
        env, log_file, tmp_path = mock_env
        result = run_guard(["install"], env, tmp_path)
        assert result.returncode == 0
        assert "Installed" in result.stdout
        cmds = read_log(log_file)
        assert any("systemctl daemon-reload" in c for c in cmds)

    def test_install_mentions_guard_location(self, mock_env):
        env, log_file, tmp_path = mock_env
        result = run_guard(["install"], env, tmp_path)
        assert result.returncode == 0
        assert "Guard script:" in result.stdout
        assert "Systemd drop-in:" in result.stdout
