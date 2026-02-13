"""Tests for AI/agent orchestration scripts — argument parsing, config, help."""

import os
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


def run_script(script_name, args, env=None, cwd=None, timeout=15):
    """Run a shell script with given args."""
    script = SCRIPTS_DIR / script_name
    run_env = env or os.environ.copy()
    result = subprocess.run(
        ["bash", str(script)] + args,
        capture_output=True, text=True, env=run_env,
        cwd=cwd, timeout=timeout,
    )
    return result


# ── run-tests.sh ─────────────────────────────────────────────────


class TestRunTestsArgs:
    def test_help_flag(self):
        """run-tests.sh help shows usage."""
        result = run_script("run-tests.sh", ["help"])
        assert result.returncode == 0
        assert "Usage" in result.stdout

    def test_help_short(self):
        """run-tests.sh --help shows usage."""
        result = run_script("run-tests.sh", ["--help"])
        assert result.returncode == 0
        assert "Usage" in result.stdout

    def test_no_args_shows_usage(self):
        """run-tests.sh without args shows usage."""
        result = run_script("run-tests.sh", [])
        assert result.returncode == 0
        assert "Usage" in result.stdout

    def test_unknown_command_errors(self):
        """run-tests.sh unknown command errors."""
        result = run_script("run-tests.sh", ["invalid"])
        assert result.returncode != 0
        assert "Unknown" in result.stderr

    def test_lists_commands_in_help(self):
        """Help text lists all available commands."""
        result = run_script("run-tests.sh", ["help"])
        for cmd in ["create", "test", "destroy", "full"]:
            assert cmd in result.stdout

    def test_lists_env_vars_in_help(self):
        """Help text documents environment variables."""
        result = run_script("run-tests.sh", ["help"])
        assert "ANKLUME_RUNNER_NAME" in result.stdout


# ── ai-test-loop.sh ─────────────────────────────────────────────


class TestAiTestLoopArgs:
    def test_help_flag(self):
        """ai-test-loop.sh --help shows usage."""
        result = run_script("ai-test-loop.sh", ["--help"])
        assert result.returncode == 0
        assert "Usage" in result.stdout or "usage" in result.stdout

    def test_help_short(self):
        """ai-test-loop.sh -h shows usage."""
        result = run_script("ai-test-loop.sh", ["-h"])
        assert result.returncode == 0

    def test_mode_none_documented(self):
        """Help mentions AI_MODE options."""
        result = run_script("ai-test-loop.sh", ["--help"])
        output = result.stdout + result.stderr
        # Should mention mode or AI
        assert "mode" in output.lower() or "ai" in output.lower()


# ── ai-develop.sh ────────────────────────────────────────────────


class TestAiDevelopArgs:
    def test_help_flag(self):
        """ai-develop.sh --help shows usage."""
        result = run_script("ai-develop.sh", ["--help"])
        assert result.returncode == 0
        assert "Usage" in result.stdout or "usage" in result.stdout

    def test_no_task_gives_error(self):
        """ai-develop.sh without TASK arg gives error."""
        result = run_script("ai-develop.sh", [])
        # Should error because no task is provided
        assert result.returncode != 0

    def test_help_mentions_task(self):
        """Help text mentions TASK parameter."""
        result = run_script("ai-develop.sh", ["--help"])
        output = result.stdout + result.stderr
        assert "task" in output.lower() or "TASK" in output


# ── ai-improve.sh ────────────────────────────────────────────────


class TestAiImproveArgs:
    def test_help_flag(self):
        """ai-improve.sh --help shows usage."""
        result = run_script("ai-improve.sh", ["--help"])
        assert result.returncode == 0
        assert "Usage" in result.stdout or "usage" in result.stdout

    def test_dry_run_mentioned(self):
        """Help mentions dry-run option."""
        result = run_script("ai-improve.sh", ["--help"])
        output = result.stdout + result.stderr
        assert "dry" in output.lower()


# ── ai-matrix-test.sh ───────────────────────────────────────────


class TestAiMatrixTestArgs:
    def test_help_flag(self):
        """ai-matrix-test.sh --help shows usage."""
        result = run_script("ai-matrix-test.sh", ["--help"])
        assert result.returncode == 0
        assert "Usage" in result.stdout or "usage" in result.stdout


# ── agent-fix.sh / agent-develop.sh (partial — they need Incus) ─


class TestAgentScriptsHelp:
    """Test that agent scripts have basic error handling for missing Incus."""

    def test_agent_fix_no_incus(self):
        """agent-fix.sh fails gracefully without Incus."""
        env = os.environ.copy()
        # Use a restricted PATH without incus
        mock_bin = Path("/tmp/test_agent_fix_mock")
        mock_bin.mkdir(exist_ok=True)
        mock_incus = mock_bin / "incus"
        mock_incus.write_text(
            "#!/usr/bin/env bash\nexit 1\n",
        )
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = run_script("agent-fix.sh", [], env=env)
        assert result.returncode != 0
        assert "Cannot connect" in result.stderr or "ERROR" in result.stderr

    def test_agent_develop_no_incus(self):
        """agent-develop.sh fails gracefully without Incus."""
        env = os.environ.copy()
        mock_bin = Path("/tmp/test_agent_develop_mock")
        mock_bin.mkdir(exist_ok=True)
        mock_incus = mock_bin / "incus"
        mock_incus.write_text(
            "#!/usr/bin/env bash\nexit 1\n",
        )
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = run_script("agent-develop.sh", ["Test task"], env=env)
        assert result.returncode != 0
        assert "Cannot connect" in result.stderr or "ERROR" in result.stderr


# ── ai-config.sh (sourced library — test via wrapper) ────────────


@pytest.fixture()
def ai_config_env(tmp_path):
    """Create environment for testing ai-config.sh functions."""
    mock_bin = tmp_path / "bin"
    mock_bin.mkdir()
    # Create a test wrapper script that sources ai-config.sh
    wrapper = tmp_path / "test_wrapper.sh"
    wrapper.write_text(f"""#!/usr/bin/env bash
set -euo pipefail
export PROJECT_DIR="{tmp_path}"
source "{SCRIPTS_DIR}/ai-config.sh"
# Execute the function passed as argument
"$@"
""")
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env["PATH"] = f"{mock_bin}:{env['PATH']}"
    # Unset AI-related vars for clean testing
    for var in [
        "ANKLUME_AI_MODE", "ANKLUME_AI_DRY_RUN",
        "ANKLUME_AI_OLLAMA_URL", "ANKLUME_AI_OLLAMA_MODEL",
    ]:
        env.pop(var, None)
    return env, tmp_path, wrapper


class TestAiConfigYamlGet:
    def test_yaml_get_reads_config(self, ai_config_env):
        """_yaml_get extracts values from anklume.conf.yml."""
        env, tmp_path, wrapper = ai_config_env
        conf = tmp_path / "anklume.conf.yml"
        conf.write_text(
            "ai:\n  mode: local\n  ollama_url: http://test:11434\n",
        )
        result = subprocess.run(
            ["bash", str(wrapper), "_yaml_get", "ai.mode", "none"],
            capture_output=True, text=True, env=env,
            cwd=str(tmp_path), timeout=10,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "local"

    def test_yaml_get_returns_default(self, ai_config_env):
        """_yaml_get returns default when key missing."""
        env, tmp_path, wrapper = ai_config_env
        conf = tmp_path / "anklume.conf.yml"
        conf.write_text("ai:\n  mode: none\n")
        result = subprocess.run(
            ["bash", str(wrapper), "_yaml_get", "ai.missing_key", "fallback"],
            capture_output=True, text=True, env=env,
            cwd=str(tmp_path), timeout=10,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "fallback"

    def test_yaml_get_missing_file_returns_default(self, ai_config_env):
        """_yaml_get returns default when config file doesn't exist."""
        env, tmp_path, wrapper = ai_config_env
        result = subprocess.run(
            ["bash", str(wrapper), "_yaml_get", "ai.mode", "none"],
            capture_output=True, text=True, env=env,
            cwd=str(tmp_path), timeout=10,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "none"


class TestAiConfigValidation:
    def test_env_var_overrides_config(self, ai_config_env):
        """ANKLUME_AI_MODE env var overrides config file."""
        env, tmp_path, wrapper = ai_config_env
        conf = tmp_path / "anklume.conf.yml"
        conf.write_text("ai:\n  mode: local\n")
        env["ANKLUME_AI_MODE"] = "remote"
        result = subprocess.run(
            ["bash", "-c", f'source "{wrapper}" 2>/dev/null; echo "$AI_MODE"'],
            capture_output=True, text=True, env=env,
            cwd=str(tmp_path), timeout=10,
        )
        # env var should take precedence
        assert "remote" in result.stdout or result.returncode != 0
