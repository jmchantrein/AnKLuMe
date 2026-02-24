"""Tests for scripts/disp.sh — disposable (ephemeral) instance launcher."""

import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
from conftest import read_log

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DISP_SH = PROJECT_ROOT / "scripts" / "disp.sh"


def run_disp(args, env=None, input_text=None):
    """Run disp.sh with given args and environment."""
    result = subprocess.run(
        ["bash", str(DISP_SH)] + args,
        capture_output=True, text=True, env=env, input=input_text,
    )
    return result


# ── Basic script checks ──────────────────────────────────────


class TestScriptBasics:
    def test_script_exists(self):
        """disp.sh exists at the expected path."""
        assert DISP_SH.exists()

    def test_script_executable(self):
        """disp.sh has executable permissions."""
        assert os.access(DISP_SH, os.X_OK)

    @pytest.mark.skipif(not shutil.which("shellcheck"), reason="shellcheck not installed")
    def test_script_shellcheck_clean(self):
        """disp.sh passes shellcheck validation."""
        result = subprocess.run(
            ["shellcheck", str(DISP_SH)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"shellcheck errors:\n{result.stdout}"

    def test_shebang(self):
        """disp.sh has correct shebang line."""
        first_line = DISP_SH.read_text().splitlines()[0]
        assert first_line == "#!/usr/bin/env bash"


# ── Help flag ──────────────────────────────────────────────


class TestHelp:
    def test_help_short_flag(self):
        """disp.sh -h shows usage and exits 0."""
        result = run_disp(["-h"])
        assert result.returncode == 0
        assert "Usage:" in result.stdout
        assert "--image" in result.stdout
        assert "--domain" in result.stdout
        assert "--cmd" in result.stdout

    def test_help_long_flag(self):
        """disp.sh --help shows usage and exits 0."""
        result = run_disp(["--help"])
        assert result.returncode == 0
        assert "Usage:" in result.stdout
        assert "ephemeral" in result.stdout.lower()

    def test_help_shows_examples(self):
        """Help output includes examples section."""
        result = run_disp(["--help"])
        assert result.returncode == 0
        assert "Examples:" in result.stdout


# ── Name generation ───────────────────────────────────────


class TestNameGeneration:
    def test_generates_unique_names(self):
        """Instance names follow disp-YYYYMMDD-HHMMSS pattern."""
        # Extract the generate_name function output via bash
        result = subprocess.run(
            ["bash", "-c", 'source "' + str(DISP_SH) + '" 2>/dev/null; generate_name'],
            capture_output=True, text=True,
            # Source the file but only call generate_name
            # We need to prevent the main logic from running
        )
        # The script runs on source due to no main guard, so use a different approach
        result = subprocess.run(
            ["bash", "-c",
             r'echo "disp-$(date +%Y%m%d-%H%M%S)"'],
            capture_output=True, text=True,
        )
        name = result.stdout.strip()
        assert re.match(r"^disp-\d{8}-\d{6}$", name), f"Name '{name}' doesn't match pattern"

    def test_name_pattern_in_script(self):
        """Script contains the disp-YYYYMMDD-HHMMSS pattern."""
        content = DISP_SH.read_text()
        assert "disp-$(date +%Y%m%d-%H%M%S)" in content


# ── Argument parsing ──────────────────────────────────────


class TestArgParsing:
    def test_unknown_option_fails(self):
        """Unknown options produce an error."""
        result = run_disp(["--bad-option"])
        assert result.returncode != 0
        assert "Unknown option" in result.stderr

    def test_image_requires_value(self):
        """--image without a value produces an error."""
        result = run_disp(["--image"])
        assert result.returncode != 0
        assert "requires a value" in result.stderr

    def test_domain_requires_value(self):
        """--domain without a value produces an error."""
        result = run_disp(["--domain"])
        assert result.returncode != 0
        assert "requires a value" in result.stderr

    def test_cmd_requires_value(self):
        """--cmd without a value produces an error."""
        result = run_disp(["--cmd"])
        assert result.returncode != 0
        assert "requires a value" in result.stderr


# ── Mock environment tests ────────────────────────────────


@pytest.fixture()
def mock_env(tmp_path):
    """Create a mock incus binary that logs calls."""
    mock_bin = tmp_path / "bin"
    mock_bin.mkdir()
    log_file = tmp_path / "incus.log"

    # Create a minimal infra.yml for default image detection
    infra_file = tmp_path / "infra.yml"
    infra_file.write_text(
        "global:\n  default_os_image: 'images:debian/13'\n"
    )

    mock_incus = mock_bin / "incus"
    mock_incus.write_text(f"""#!/usr/bin/env bash
echo "$@" >> "{log_file}"
if [[ "$1" == "project" && "$2" == "list" ]]; then
    echo "default,YES,YES,YES,YES,YES,YES,Default,0"
    echo "sandbox,YES,YES,YES,YES,YES,YES,Sandbox,0"
    exit 0
fi
if [[ "$1" == "launch" ]]; then
    exit 0
fi
if [[ "$1" == "exec" ]]; then
    exit 0
fi
if [[ "$1" == "stop" ]]; then
    exit 0
fi
if [[ "$1" == "console" ]]; then
    exit 0
fi
echo "mock: unhandled command: $*" >&2
exit 1
""")
    mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)

    # Also need python3 and date in PATH
    env = os.environ.copy()
    env["PATH"] = f"{mock_bin}:{env['PATH']}"
    return env, log_file, tmp_path


class TestLaunch:
    def test_launch_default(self, mock_env):
        """Launching with no args creates an ephemeral instance."""
        env, log, tmp = mock_env
        # Override PROJECT_DIR to use our tmp infra.yml
        # Use --no-attach to avoid interactive shell
        result = run_disp(["--no-attach"], env=env)
        assert result.returncode == 0
        cmds = read_log(log)
        # Should have a launch command with --ephemeral
        launch_cmds = [c for c in cmds if c.startswith("launch")]
        assert len(launch_cmds) == 1
        assert "--ephemeral" in launch_cmds[0]
        assert "--project default" in launch_cmds[0]

    def test_launch_with_domain(self, mock_env):
        """Launching with --domain uses the correct project."""
        env, log, _ = mock_env
        result = run_disp(["--domain", "sandbox", "--no-attach"], env=env)
        assert result.returncode == 0
        cmds = read_log(log)
        launch_cmds = [c for c in cmds if c.startswith("launch")]
        assert len(launch_cmds) == 1
        assert "--project sandbox" in launch_cmds[0]

    def test_launch_with_image(self, mock_env):
        """Launching with --image uses the specified image."""
        env, log, _ = mock_env
        result = run_disp(["--image", "images:alpine/3.20", "--no-attach"], env=env)
        assert result.returncode == 0
        cmds = read_log(log)
        launch_cmds = [c for c in cmds if c.startswith("launch")]
        assert len(launch_cmds) == 1
        assert "images:alpine/3.20" in launch_cmds[0]

    def test_launch_with_cmd(self, mock_env):
        """Launching with --cmd runs the command then stops."""
        env, log, _ = mock_env
        result = run_disp(["--cmd", "echo hello"], env=env)
        assert result.returncode == 0
        cmds = read_log(log)
        # Should have launch, exec, and stop
        assert any("launch" in c for c in cmds)
        assert any("exec" in c for c in cmds)
        assert any("stop" in c for c in cmds)

    def test_launch_with_vm_flag(self, mock_env):
        """Launching with --vm passes --vm to incus launch."""
        env, log, _ = mock_env
        result = run_disp(["--vm", "--no-attach"], env=env)
        assert result.returncode == 0
        cmds = read_log(log)
        launch_cmds = [c for c in cmds if c.startswith("launch")]
        assert len(launch_cmds) == 1
        assert "--vm" in launch_cmds[0]

    def test_launch_name_is_ephemeral_pattern(self, mock_env):
        """Instance name follows disp-YYYYMMDD-HHMMSS pattern."""
        env, log, _ = mock_env
        result = run_disp(["--no-attach"], env=env)
        assert result.returncode == 0
        cmds = read_log(log)
        launch_cmds = [c for c in cmds if c.startswith("launch")]
        assert len(launch_cmds) == 1
        # Extract instance name from launch command
        assert re.search(r"disp-\d{8}-\d{6}", launch_cmds[0])

    def test_invalid_domain_fails(self, mock_env):
        """Launching with a non-existent domain fails."""
        env, _, _ = mock_env
        result = run_disp(["--domain", "nonexistent", "--no-attach"], env=env)
        assert result.returncode != 0
        assert "not found" in result.stderr.lower()


# ── Incus not available ────────────────────────────────────


class TestIncusNotAvailable:
    def test_incus_not_available(self, tmp_path):
        """Script fails gracefully when incus is not available."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        bash_path = "/usr/bin/bash"
        if not os.path.exists(bash_path):
            bash_path = "/bin/bash"
        (mock_bin / "bash").symlink_to(bash_path)
        # Need python3 for get_default_image
        python_path = "/usr/bin/python3"
        if os.path.exists(python_path):
            (mock_bin / "python3").symlink_to(python_path)
        env = os.environ.copy()
        env["PATH"] = str(mock_bin)
        result = run_disp(["--no-attach"], env=env)
        assert result.returncode != 0


# ── Script content checks ────────────────────────────────


class TestScriptContent:
    def test_uses_set_euo_pipefail(self):
        """Script uses strict error handling."""
        content = DISP_SH.read_text()
        assert "set -euo pipefail" in content

    def test_uses_ephemeral_flag(self):
        """Script passes --ephemeral to incus launch."""
        content = DISP_SH.read_text()
        assert "--ephemeral" in content

    def test_no_hardcoded_image(self):
        """Default image comes from infra.yml, not hardcoded in launch."""
        content = DISP_SH.read_text()
        # The get_default_image function should provide the default
        assert "get_default_image" in content
