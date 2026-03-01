"""Tests for scripts/guide.sh — interactive capability tour & setup wizard."""

import os
import stat
import subprocess
from pathlib import Path

import pytest

GUIDE_SH = Path(__file__).resolve().parent.parent / "scripts" / "guide.sh"
GUIDE_SETUP_SH = Path(__file__).resolve().parent.parent / "scripts" / "guide-setup.sh"
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# CI detection: GitHub Actions sets CI=true and GITHUB_ACTIONS=true
CI = os.environ.get("CI") == "true"


@pytest.fixture()
def guide_env(tmp_path):
    """Create a mock environment for guide testing."""
    mock_bin = tmp_path / "bin"
    mock_bin.mkdir()

    # Mock commands that the guide checks for
    for cmd in ["ansible-playbook", "ansible-lint",
                "yamllint", "python3", "git", "make"]:
        mock_cmd = mock_bin / cmd
        mock_cmd.write_text("#!/usr/bin/env bash\nexit 0\n")
        mock_cmd.chmod(mock_cmd.stat().st_mode | stat.S_IEXEC)

    # Mock incus — output RUNNING for list commands
    mock_incus = mock_bin / "incus"
    mock_incus.write_text(
        '#!/usr/bin/env bash\n'
        'if [[ "$1" == "list" ]]; then echo "RUNNING"; fi\n'
        'exit 0\n'
    )
    mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)

    # Real python3 for actual use
    mock_python = mock_bin / "python3"
    mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
    mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env["PATH"] = f"{mock_bin}:{env['PATH']}"
    env["TERM"] = "dumb"  # Avoid ANSI clearing issues
    return env


def run_guide(args, env, cwd=None, script=None):
    """Run guide.sh or guide-setup.sh with given args."""
    script_path = script or GUIDE_SH
    result = subprocess.run(
        ["bash", str(script_path)] + args,
        capture_output=True, text=True, env=env,
        cwd=cwd or str(PROJECT_ROOT), timeout=30,
    )
    return result


# ── auto mode ──────────────────────────────────────────────


class TestGuideAutoMode:
    @pytest.mark.skipif(
        CI,
        reason="Full auto run hits chapter demos which need mock incus",
    )
    def test_auto_mode_runs(self, guide_env):
        """--auto mode runs the capability tour without prompts."""
        result = run_guide(["--auto"], guide_env)
        assert result.returncode == 0
        assert "Chapter" in result.stdout or "Tour complete" in result.stdout

    def test_auto_mode_checks_prerequisites(self, guide_env):
        """Auto mode checks for incus before proceeding."""
        result = run_guide(["--auto", "--step", "1"], guide_env)
        output = result.stdout.lower()
        assert "incus" in output or "prerequisit" in output \
            or "Step 1" in result.stdout


# ── setup wizard step resume ──────────────────────────────


class TestGuideStepResume:
    def test_resume_from_step(self, guide_env):
        """--step N dispatches to setup wizard from that step."""
        result = run_guide(["--auto", "--step", "1"], guide_env)
        assert result.returncode == 0 or "Step 1" in result.stdout

    def test_step_max_valid(self, guide_env):
        """--step 8 (TOTAL_STEPS) is valid in setup wizard."""
        result = run_guide(
            ["--auto", "--step", "8"], guide_env, script=GUIDE_SETUP_SH,
        )
        assert result.returncode == 0

    def test_step_out_of_range_error(self, guide_env):
        """--step 99 gives an error (above TOTAL_STEPS)."""
        result = run_guide(
            ["--step", "99"], guide_env, script=GUIDE_SETUP_SH,
        )
        assert result.returncode != 0


# ── missing prerequisites ─────────────────────────────────


class TestGuidePrerequisitesMissing:
    """Test with missing required tools."""

    @staticmethod
    def _make_env_hiding_tools(tmp_path, hidden_cmds):
        """Build an env where specific commands are absent from PATH."""
        mock_bin = tmp_path / "restricted_bin"
        mock_bin.mkdir(exist_ok=True)

        essential = [
            "bash", "env", "sed", "awk", "head", "tail", "cat",
            "grep", "seq", "clear", "true", "false", "dirname",
            "pwd", "cd", "rm", "cp", "mkdir", "chmod", "tee",
            "sort", "tr", "wc", "uname", "id", "readlink",
        ]
        for util in essential:
            src = Path(f"/usr/bin/{util}")
            if not src.exists():
                src = Path(f"/bin/{util}")
            if src.exists() and not (mock_bin / util).exists():
                (mock_bin / util).symlink_to(src)

        all_guide_tools = [
            "incus", "ansible-playbook", "ansible-lint", "ansible",
            "yamllint", "python3", "git", "make",
            "shellcheck", "ruff",
        ]
        for tool in all_guide_tools:
            if tool in hidden_cmds:
                continue
            mock_cmd = mock_bin / tool
            if not mock_cmd.exists():
                mock_cmd.write_text("#!/usr/bin/env bash\nexit 0\n")
                mock_cmd.chmod(mock_cmd.stat().st_mode | stat.S_IEXEC)

        mock_python = mock_bin / "python3"
        if mock_python.exists():
            mock_python.unlink()
        mock_python.write_text(
            "#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n"
        )
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)

        env = os.environ.copy()
        env["PATH"] = str(mock_bin)
        env["TERM"] = "dumb"
        return env

    @pytest.fixture()
    def env_missing_incus(self, tmp_path):
        return self._make_env_hiding_tools(tmp_path, {"incus"})

    @pytest.mark.skipif(
        CI,
        reason="Restricted PATH may lack essential utilities at expected "
        "locations on ubuntu-latest",
    )
    def test_missing_incus_fails_auto(self, env_missing_incus):
        """Auto mode exits with error when incus is missing."""
        result = run_guide(["--auto"], env_missing_incus)
        assert result.returncode != 0
        output = result.stdout.lower()
        assert "incus" in output


# ── help flag ──────────────────────────────────────────────


class TestGuideHelp:
    def test_help_flag(self, guide_env):
        """--help shows usage and exits 0."""
        result = run_guide(["--help"], guide_env)
        assert result.returncode == 0
        assert "--chapter" in result.stdout
        assert "--setup" in result.stdout


# ── setup wizard steps ─────────────────────────────────────


class TestGuideSetupSteps:
    """Test setup wizard steps via guide-setup.sh."""

    def test_step_1_checks_tools(self, guide_env):
        """Step 1 checks for required tools."""
        result = run_guide(
            ["--auto", "--step", "1"], guide_env, script=GUIDE_SETUP_SH,
        )
        output = result.stdout.lower()
        assert "incus" in output or "prerequisit" in output

    def test_step_2_selects_use_case(self, guide_env):
        """Step 2 selects a use case in auto mode."""
        result = run_guide(
            ["--auto", "--step", "2"], guide_env, script=GUIDE_SETUP_SH,
        )
        assert "custom" in result.stdout or "Selected" in result.stdout

    def test_step_8_completes(self, guide_env):
        """Step 8 (Setup Complete) shows completion message."""
        result = run_guide(
            ["--auto", "--step", "8"], guide_env, script=GUIDE_SETUP_SH,
        )
        assert result.returncode == 0
        assert "Setup complete" in result.stdout or "complete" in result.stdout.lower()
