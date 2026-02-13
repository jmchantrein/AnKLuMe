"""Tests for scripts/deploy-nftables.sh — nftables host deployment."""

import os
import stat
import subprocess
from pathlib import Path

import pytest

DEPLOY_SH = Path(__file__).resolve().parent.parent / "scripts" / "deploy-nftables.sh"


@pytest.fixture()
def mock_env(tmp_path):
    """Create a mock environment for deploy-nftables testing."""
    mock_bin = tmp_path / "bin"
    mock_bin.mkdir()
    log_file = tmp_path / "cmds.log"

    # Create a fake rules file that incus file pull will "retrieve"
    rules_content = """table inet anklume {
    chain isolation {
        type filter hook forward priority -1; policy accept;
        ct state established,related accept
        ct state invalid drop
        iifname "net-admin" oifname "net-admin" accept
        iifname "net-work" oifname "net-work" accept
        drop
    }
}
"""
    rules_file = tmp_path / "mock-rules.nft"
    rules_file.write_text(rules_content)

    # Mock incus
    mock_incus = mock_bin / "incus"
    mock_incus.write_text(f"""#!/usr/bin/env bash
echo "incus $@" >> "{log_file}"

# project list --format csv (pre-flight)
if [[ "$1" == "project" && "$2" == "list" ]]; then
    echo "default"
    echo "admin"
    exit 0
fi

# info (find container)
if [[ "$1" == "info" ]]; then
    exit 0
fi

# file pull (retrieve rules)
if [[ "$1" == "file" && "$2" == "pull" ]]; then
    # Copy our mock rules to the destination
    cp "{rules_file}" "$4"
    exit 0
fi

exit 0
""")
    mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)

    # Mock nft (validate syntax)
    mock_nft = mock_bin / "nft"
    mock_nft.write_text(f"""#!/usr/bin/env bash
echo "nft $@" >> "{log_file}"
# -c = check mode (dry validation)
if [[ "$1" == "-c" ]]; then
    exit 0
fi
# -f = apply file
if [[ "$1" == "-f" ]]; then
    exit 0
fi
exit 0
""")
    mock_nft.chmod(mock_nft.stat().st_mode | stat.S_IEXEC)

    # Mock python3
    mock_python = mock_bin / "python3"
    mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
    mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)

    # Mock other tools
    for cmd in ["mkdir", "cp", "chmod", "wc", "cat", "mktemp"]:
        p = mock_bin / cmd
        if not p.exists():
            real = f"/usr/bin/{cmd}"
            if os.path.exists(real):
                p.symlink_to(real)

    # Create patched deploy script to avoid /etc writes
    patched_deploy = tmp_path / "deploy_patched.sh"
    original = DEPLOY_SH.read_text()
    patched_dest = tmp_path / "nftables.d"
    patched_dest.mkdir()
    patched = original.replace('/etc/nftables.d', str(patched_dest))
    patched_deploy.write_text(patched)
    patched_deploy.chmod(patched_deploy.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env["PATH"] = f"{mock_bin}:{env['PATH']}"
    return env, log_file, tmp_path, patched_deploy


def run_deploy(args, env, cwd=None, script=None):
    """Run deploy-nftables.sh with given args."""
    script_path = script or DEPLOY_SH
    result = subprocess.run(
        ["bash", str(script_path)] + args,
        capture_output=True, text=True, env=env, cwd=cwd, timeout=15,
    )
    return result


def read_log(log_file):
    """Return list of commands from the log file."""
    if log_file.exists():
        return [line.strip() for line in log_file.read_text().splitlines() if line.strip()]
    return []


class TestDeployArgs:
    def test_help_flag(self, mock_env):
        """--help shows usage."""
        env, _, _, script = mock_env
        result = run_deploy(["--help"], env, script=script)
        assert result.returncode == 0
        assert "Usage" in result.stdout

    def test_unknown_option(self, mock_env):
        """Unknown option gives error."""
        env, _, _, script = mock_env
        result = run_deploy(["--invalid"], env, script=script)
        assert result.returncode != 0
        assert "Unknown" in result.stderr

    def test_source_requires_value(self, mock_env):
        """--source without value gives error."""
        env, _, _, script = mock_env
        result = run_deploy(["--source"], env, script=script)
        assert result.returncode != 0


class TestDeployDryRun:
    def test_dry_run_validates_without_installing(self, mock_env):
        """--dry-run validates syntax but does not install."""
        env, log, _, script = mock_env
        result = run_deploy(["--dry-run"], env, script=script)
        assert result.returncode == 0
        assert "Dry run" in result.stdout or "dry run" in result.stdout.lower()
        cmds = read_log(log)
        # Should validate (nft -c -f)
        assert any("nft -c" in c for c in cmds)
        # Should NOT install (no nft -f without -c)
        nft_apply = [c for c in cmds if c.startswith("nft -f")]
        assert len(nft_apply) == 0


class TestDeployExecution:
    def test_full_deploy_pulls_and_applies(self, mock_env):
        """Full deploy pulls rules, validates, and applies."""
        env, log, _, script = mock_env
        result = run_deploy([], env, script=script)
        assert result.returncode == 0
        assert "deployed successfully" in result.stdout
        cmds = read_log(log)
        # Should pull file from container
        assert any("file pull" in c for c in cmds)
        # Should validate
        assert any("nft -c" in c for c in cmds)

    def test_custom_source_container(self, mock_env):
        """--source changes the container name."""
        env, log, _, script = mock_env
        run_deploy(["--source", "my-admin"], env, script=script)
        cmds = read_log(log)
        assert any("my-admin" in c for c in cmds)


class TestDeployNoIncus:
    def test_no_incus_fails(self, tmp_path):
        """Deploy fails when Incus is not available."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        mock_incus = mock_bin / "incus"
        mock_incus.write_text("#!/usr/bin/env bash\nexit 1\n")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)
        # Need mktemp
        for cmd in ["mktemp"]:
            real = f"/usr/bin/{cmd}"
            if os.path.exists(real):
                (mock_bin / cmd).symlink_to(real)
        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = run_deploy([], env, cwd=tmp_path)
        assert result.returncode != 0
        assert "Cannot connect" in result.stderr
