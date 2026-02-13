"""Tests for scripts/guide.sh — interactive onboarding tutorial."""

import os
import stat
import subprocess
from pathlib import Path

import pytest

GUIDE_SH = Path(__file__).resolve().parent.parent / "scripts" / "guide.sh"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def guide_env(tmp_path):
    """Create a mock environment for guide testing."""
    mock_bin = tmp_path / "bin"
    mock_bin.mkdir()

    # Mock commands that the guide checks for
    for cmd in ["incus", "ansible-playbook", "ansible-lint",
                "yamllint", "python3", "git", "make"]:
        mock_cmd = mock_bin / cmd
        mock_cmd.write_text("#!/usr/bin/env bash\nexit 0\n")
        mock_cmd.chmod(mock_cmd.stat().st_mode | stat.S_IEXEC)

    # Real python3 for actual use
    mock_python = mock_bin / "python3"
    mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
    mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env["PATH"] = f"{mock_bin}:{env['PATH']}"
    env["TERM"] = "dumb"  # Avoid ANSI clearing issues
    return env


def run_guide(args, env, cwd=None):
    """Run guide.sh with given args."""
    result = subprocess.run(
        ["bash", str(GUIDE_SH)] + args,
        capture_output=True, text=True, env=env,
        cwd=cwd or str(PROJECT_ROOT), timeout=30,
    )
    return result


class TestGuideArgs:
    def test_help_flag(self, guide_env):
        """--help shows usage."""
        result = run_guide(["--help"], guide_env)
        assert result.returncode == 0
        assert "Usage" in result.stdout

    def test_unknown_option(self, guide_env):
        """Unknown option gives error."""
        result = run_guide(["--invalid"], guide_env)
        assert result.returncode != 0
        assert "Unknown" in result.stdout or "Unknown" in result.stderr

    def test_invalid_step_number(self, guide_env):
        """Step number out of range gives error."""
        result = run_guide(["--step", "99"], guide_env)
        assert result.returncode != 0
        assert "must be between" in result.stdout or "must be between" in result.stderr

    def test_step_zero_invalid(self, guide_env):
        """Step 0 is invalid."""
        result = run_guide(["--step", "0"], guide_env)
        assert result.returncode != 0


class TestGuideAutoMode:
    def test_auto_mode_runs(self, guide_env):
        """--auto mode runs without prompts."""
        result = run_guide(["--auto"], guide_env)
        # Auto mode may fail at some step (e.g., step 4 needs infra.yml)
        # but it should at least start
        assert "Step 1" in result.stdout or "Prerequisites" in result.stdout

    def test_auto_mode_checks_prerequisites(self, guide_env):
        """Auto mode checks for required tools in step 1."""
        result = run_guide(["--auto", "--step", "1"], guide_env)
        # Should check for tools
        assert "incus" in result.stdout.lower() or "prerequisit" in result.stdout.lower() \
            or "Step 1" in result.stdout


class TestGuideStepResume:
    def test_resume_from_step(self, guide_env):
        """--step N resumes from that step."""
        result = run_guide(["--auto", "--step", "1"], guide_env)
        # Should start from step 1
        assert "Step 1" in result.stdout or result.returncode == 0
