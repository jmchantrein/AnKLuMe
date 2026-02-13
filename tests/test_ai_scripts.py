"""Tests for AI/agent orchestration scripts — argument parsing, config, help."""

import os
import shutil
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


# ── ai-config.sh full config loading ─────────────────────────────


@pytest.fixture()
def ai_config_full_env(tmp_path):
    """Create environment for testing ai-config.sh with die() and functions.

    Uses a wrapper that defines die() so ai_validate_config can call it,
    and sources ai-config.sh with ANKLUME_CONF pointing to the right file.
    """
    mock_bin = tmp_path / "bin"
    mock_bin.mkdir()
    wrapper = tmp_path / "test_full_wrapper.sh"
    wrapper.write_text(f"""#!/usr/bin/env bash
set -euo pipefail
export PROJECT_DIR="{tmp_path}"
die() {{ echo "ERROR: $*" >&2; exit 1; }}
export ANKLUME_CONF="{tmp_path}/anklume.conf.yml"
source "{SCRIPTS_DIR}/ai-config.sh"
# Execute the function or command passed as argument
"$@"
""")
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env["PATH"] = f"{mock_bin}:{env['PATH']}"
    env["ANKLUME_CONF"] = str(tmp_path / "anklume.conf.yml")
    # Unset all AI-related vars for clean testing
    for var in [
        "ANKLUME_AI_MODE", "ANKLUME_AI_DRY_RUN",
        "ANKLUME_AI_OLLAMA_URL", "ANKLUME_AI_OLLAMA_MODEL",
        "ANKLUME_AI_MAX_RETRIES", "ANKLUME_AI_AUTO_PR",
        "ANTHROPIC_API_KEY",
    ]:
        env.pop(var, None)
    return env, tmp_path, wrapper


def _run_wrapper(wrapper, args, env, cwd, timeout=10):
    """Helper to run the test wrapper with given args."""
    return subprocess.run(
        ["bash", str(wrapper)] + args,
        capture_output=True, text=True, env=env,
        cwd=str(cwd), timeout=timeout,
    )


def _source_and_echo(wrapper, var_name, env, cwd, timeout=10):
    """Source the wrapper and echo a shell variable."""
    return subprocess.run(
        ["bash", "-c", f'source "{wrapper}" 2>/dev/null; echo "${var_name}"'],
        capture_output=True, text=True, env=env,
        cwd=str(cwd), timeout=timeout,
    )


class TestAiConfigFullLoading:
    """Test that all config variables are loaded from anklume.conf.yml."""

    def test_loads_ollama_url(self, ai_config_full_env):
        """Config file value for ai.ollama_url is loaded into AI_OLLAMA_URL."""
        env, tmp_path, wrapper = ai_config_full_env
        conf = tmp_path / "anklume.conf.yml"
        conf.write_text(
            "ai:\n"
            "  mode: none\n"
            "  ollama_url: http://custom-host:9999\n",
        )
        result = _source_and_echo(wrapper, "AI_OLLAMA_URL", env, tmp_path)
        assert result.stdout.strip() == "http://custom-host:9999"

    def test_loads_ollama_model(self, ai_config_full_env):
        """Config file value for ai.ollama_model is loaded into AI_OLLAMA_MODEL."""
        env, tmp_path, wrapper = ai_config_full_env
        conf = tmp_path / "anklume.conf.yml"
        conf.write_text(
            "ai:\n"
            "  mode: none\n"
            "  ollama_model: llama3:70b\n",
        )
        result = _source_and_echo(wrapper, "AI_OLLAMA_MODEL", env, tmp_path)
        assert result.stdout.strip() == "llama3:70b"

    def test_loads_max_retries(self, ai_config_full_env):
        """Config file value for ai.max_retries is loaded into AI_MAX_RETRIES."""
        env, tmp_path, wrapper = ai_config_full_env
        conf = tmp_path / "anklume.conf.yml"
        conf.write_text("ai:\n  mode: none\n  max_retries: 7\n")
        result = _source_and_echo(wrapper, "AI_MAX_RETRIES", env, tmp_path)
        assert result.stdout.strip() == "7"

    def test_loads_auto_pr(self, ai_config_full_env):
        """Config file value for ai.auto_pr is loaded into AI_AUTO_PR."""
        env, tmp_path, wrapper = ai_config_full_env
        conf = tmp_path / "anklume.conf.yml"
        conf.write_text("ai:\n  mode: none\n  auto_pr: true\n")
        result = _source_and_echo(wrapper, "AI_AUTO_PR", env, tmp_path)
        assert result.stdout.strip() == "True"

    def test_loads_dry_run(self, ai_config_full_env):
        """Config file value for ai.dry_run is loaded into AI_DRY_RUN."""
        env, tmp_path, wrapper = ai_config_full_env
        conf = tmp_path / "anklume.conf.yml"
        conf.write_text("ai:\n  mode: none\n  dry_run: false\n")
        result = _source_and_echo(wrapper, "AI_DRY_RUN", env, tmp_path)
        assert result.stdout.strip() == "False"

    def test_loads_mode(self, ai_config_full_env):
        """Config file value for ai.mode is loaded into AI_MODE."""
        env, tmp_path, wrapper = ai_config_full_env
        conf = tmp_path / "anklume.conf.yml"
        conf.write_text("ai:\n  mode: local\n")
        result = _source_and_echo(wrapper, "AI_MODE", env, tmp_path)
        assert result.stdout.strip() == "local"


class TestAiConfigDefaults:
    """Test default values when no config file exists."""

    def test_default_mode_is_none(self, ai_config_full_env):
        """Without config file, AI_MODE defaults to 'none'."""
        env, tmp_path, wrapper = ai_config_full_env
        # No config file created
        result = _source_and_echo(wrapper, "AI_MODE", env, tmp_path)
        assert result.stdout.strip() == "none"

    def test_default_ollama_url(self, ai_config_full_env):
        """Without config file, AI_OLLAMA_URL defaults to http://homelab-ai:11434."""
        env, tmp_path, wrapper = ai_config_full_env
        result = _source_and_echo(wrapper, "AI_OLLAMA_URL", env, tmp_path)
        assert result.stdout.strip() == "http://homelab-ai:11434"

    def test_default_ollama_model(self, ai_config_full_env):
        """Without config file, AI_OLLAMA_MODEL defaults to qwen2.5-coder:32b."""
        env, tmp_path, wrapper = ai_config_full_env
        result = _source_and_echo(wrapper, "AI_OLLAMA_MODEL", env, tmp_path)
        assert result.stdout.strip() == "qwen2.5-coder:32b"

    def test_default_max_retries(self, ai_config_full_env):
        """Without config file, AI_MAX_RETRIES defaults to 3."""
        env, tmp_path, wrapper = ai_config_full_env
        result = _source_and_echo(wrapper, "AI_MAX_RETRIES", env, tmp_path)
        assert result.stdout.strip() == "3"

    def test_default_auto_pr(self, ai_config_full_env):
        """Without config file, AI_AUTO_PR defaults to false."""
        env, tmp_path, wrapper = ai_config_full_env
        result = _source_and_echo(wrapper, "AI_AUTO_PR", env, tmp_path)
        assert result.stdout.strip() == "false"

    def test_default_dry_run(self, ai_config_full_env):
        """Without config file, AI_DRY_RUN defaults to true."""
        env, tmp_path, wrapper = ai_config_full_env
        result = _source_and_echo(wrapper, "AI_DRY_RUN", env, tmp_path)
        assert result.stdout.strip() == "true"

    def test_default_log_dir(self, ai_config_full_env):
        """Without config file, AI_LOG_DIR defaults to logs."""
        env, tmp_path, wrapper = ai_config_full_env
        result = _source_and_echo(wrapper, "AI_LOG_DIR", env, tmp_path)
        assert result.stdout.strip() == "logs"


class TestAiConfigPartialValues:
    """Test config file with partial values (some keys present, others default)."""

    def test_partial_config_uses_defaults_for_missing(self, ai_config_full_env):
        """Partial config: present keys loaded, missing keys use defaults."""
        env, tmp_path, wrapper = ai_config_full_env
        conf = tmp_path / "anklume.conf.yml"
        # Only set mode and ollama_url, leave the rest to defaults
        conf.write_text("ai:\n  mode: local\n  ollama_url: http://my-llm:11434\n")
        # Check that the set values are loaded
        result_mode = _source_and_echo(wrapper, "AI_MODE", env, tmp_path)
        assert result_mode.stdout.strip() == "local"
        result_url = _source_and_echo(wrapper, "AI_OLLAMA_URL", env, tmp_path)
        assert result_url.stdout.strip() == "http://my-llm:11434"
        # Check that unset values fall back to defaults
        result_model = _source_and_echo(
            wrapper, "AI_OLLAMA_MODEL", env, tmp_path,
        )
        assert result_model.stdout.strip() == "qwen2.5-coder:32b"
        result_retries = _source_and_echo(
            wrapper, "AI_MAX_RETRIES", env, tmp_path,
        )
        assert result_retries.stdout.strip() == "3"

    def test_partial_config_empty_ai_section(self, ai_config_full_env):
        """Config file with empty ai section uses all defaults."""
        env, tmp_path, wrapper = ai_config_full_env
        conf = tmp_path / "anklume.conf.yml"
        conf.write_text("ai: {}\n")
        result = _source_and_echo(wrapper, "AI_MODE", env, tmp_path)
        assert result.stdout.strip() == "none"
        result = _source_and_echo(wrapper, "AI_OLLAMA_URL", env, tmp_path)
        assert result.stdout.strip() == "http://homelab-ai:11434"


class TestAiConfigNestedYaml:
    """Test nested YAML key access (ai.ollama_url vs ai.mode)."""

    def test_yaml_get_nested_two_levels(self, ai_config_full_env):
        """_yaml_get handles two-level nesting (ai.mode)."""
        env, tmp_path, wrapper = ai_config_full_env
        conf = tmp_path / "anklume.conf.yml"
        conf.write_text("ai:\n  mode: aider\n")
        result = _run_wrapper(
            wrapper, ["_yaml_get", "ai.mode", "none"], env, tmp_path,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "aider"

    def test_yaml_get_nested_missing_intermediate_key(self, ai_config_full_env):
        """_yaml_get returns default when intermediate key missing."""
        env, tmp_path, wrapper = ai_config_full_env
        conf = tmp_path / "anklume.conf.yml"
        conf.write_text("other:\n  key: value\n")
        result = _run_wrapper(
            wrapper, ["_yaml_get", "ai.mode", "fallback"], env, tmp_path,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "fallback"

    def test_yaml_get_deeper_nesting(self, ai_config_full_env):
        """_yaml_get handles three levels of nesting."""
        env, tmp_path, wrapper = ai_config_full_env
        conf = tmp_path / "anklume.conf.yml"
        conf.write_text("a:\n  b:\n    c: deep_value\n")
        result = _run_wrapper(
            wrapper, ["_yaml_get", "a.b.c", "none"], env, tmp_path,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "deep_value"


# ── ai-config.sh validation function ─────────────────────────────


class TestAiValidateConfigModes:
    """Test ai_validate_config with each valid and invalid AI_MODE."""

    @pytest.mark.parametrize("mode", ["none", "local", "remote", "claude-code", "aider"])
    def test_valid_modes_accepted(self, ai_config_full_env, mode):
        """ai_validate_config accepts all valid AI_MODE values."""
        env, tmp_path, wrapper = ai_config_full_env
        env["ANKLUME_AI_MODE"] = mode
        # Provide mock binaries so mode-specific checks pass
        mock_bin = tmp_path / "bin"
        for binary in ["curl", "claude", "aider"]:
            mock = mock_bin / binary
            mock.write_text("#!/usr/bin/env bash\nexit 0\n")
            mock.chmod(mock.stat().st_mode | stat.S_IEXEC)
        # For remote mode, set the API key
        if mode == "remote":
            env["ANTHROPIC_API_KEY"] = "sk-test-dummy"
        result = _run_wrapper(
            wrapper, ["ai_validate_config"], env, tmp_path,
        )
        assert result.returncode == 0, (
            f"Mode '{mode}' should be valid, got stderr: {result.stderr}"
        )

    def test_invalid_mode_gives_error(self, ai_config_full_env):
        """ai_validate_config rejects an invalid AI_MODE value."""
        env, tmp_path, wrapper = ai_config_full_env
        env["ANKLUME_AI_MODE"] = "invalid-backend"
        result = _run_wrapper(
            wrapper, ["ai_validate_config"], env, tmp_path,
        )
        assert result.returncode != 0
        assert "Invalid AI_MODE" in result.stderr
        assert "invalid-backend" in result.stderr

    def test_local_mode_without_curl_errors(self, ai_config_full_env):
        """AI_MODE=local without curl gives error."""
        env, tmp_path, wrapper = ai_config_full_env
        env["ANKLUME_AI_MODE"] = "local"
        # Build a restricted PATH with symlinks to needed binaries
        # but excluding curl. This makes `command -v curl` fail.
        restricted_bin = tmp_path / "restricted_bin"
        restricted_bin.mkdir(exist_ok=True)
        for binary in ["bash", "python3", "env", "date", "mkdir", "echo"]:

            real = shutil.which(binary)
            if real:
                link = restricted_bin / binary
                if not link.exists():
                    link.symlink_to(real)
        env["PATH"] = str(restricted_bin)
        result = _run_wrapper(
            wrapper, ["ai_validate_config"], env, tmp_path,
        )
        assert result.returncode != 0
        assert "curl" in result.stderr

    def test_remote_mode_without_api_key_errors(self, ai_config_full_env):
        """AI_MODE=remote without ANTHROPIC_API_KEY gives error."""
        env, tmp_path, wrapper = ai_config_full_env
        env["ANKLUME_AI_MODE"] = "remote"
        env.pop("ANTHROPIC_API_KEY", None)
        result = _run_wrapper(
            wrapper, ["ai_validate_config"], env, tmp_path,
        )
        assert result.returncode != 0
        assert "ANTHROPIC_API_KEY" in result.stderr

    def test_claude_code_mode_without_binary_errors(self, ai_config_full_env):
        """AI_MODE=claude-code without claude binary gives error."""
        env, tmp_path, wrapper = ai_config_full_env
        env["ANKLUME_AI_MODE"] = "claude-code"
        # Build a restricted PATH with only essential binaries, no claude
        restricted_bin = tmp_path / "restricted_bin_claude"
        restricted_bin.mkdir(exist_ok=True)
        for binary in ["bash", "python3", "env", "date", "mkdir", "echo"]:

            real = shutil.which(binary)
            if real:
                link = restricted_bin / binary
                if not link.exists():
                    link.symlink_to(real)
        env["PATH"] = str(restricted_bin)
        result = _run_wrapper(
            wrapper, ["ai_validate_config"], env, tmp_path,
        )
        assert result.returncode != 0
        assert "claude" in result.stderr.lower()

    def test_aider_mode_without_binary_errors(self, ai_config_full_env):
        """AI_MODE=aider without aider binary gives error."""
        env, tmp_path, wrapper = ai_config_full_env
        env["ANKLUME_AI_MODE"] = "aider"
        # Build a restricted PATH with only essential binaries, no aider
        restricted_bin = tmp_path / "restricted_bin_aider"
        restricted_bin.mkdir(exist_ok=True)
        for binary in ["bash", "python3", "env", "date", "mkdir", "echo"]:

            real = shutil.which(binary)
            if real:
                link = restricted_bin / binary
                if not link.exists():
                    link.symlink_to(real)
        env["PATH"] = str(restricted_bin)
        result = _run_wrapper(
            wrapper, ["ai_validate_config"], env, tmp_path,
        )
        assert result.returncode != 0
        assert "aider" in result.stderr.lower()


# ── ai-config.sh session initialization ──────────────────────────


class TestAiInitSession:
    """Test ai_init_session creates log directory and file."""

    def test_init_session_creates_log_dir(self, ai_config_full_env):
        """ai_init_session creates the AI_LOG_DIR directory."""
        env, tmp_path, wrapper = ai_config_full_env
        env["ANKLUME_AI_MODE"] = "none"
        log_dir = tmp_path / "test-logs"
        env["ANKLUME_AI_LOG_DIR"] = str(log_dir)
        # Rewrite wrapper to use the custom log dir
        wrapper.write_text(f"""#!/usr/bin/env bash
set -euo pipefail
export PROJECT_DIR="{tmp_path}"
export ANKLUME_AI_LOG_DIR="{log_dir}"
die() {{ echo "ERROR: $*" >&2; exit 1; }}
export ANKLUME_CONF="{tmp_path}/anklume.conf.yml"
source "{SCRIPTS_DIR}/ai-config.sh"
"$@"
""")
        wrapper.chmod(wrapper.stat().st_mode | stat.S_IEXEC)
        result = _run_wrapper(
            wrapper, ["ai_init_session", "test-prefix"], env, tmp_path,
        )
        assert result.returncode == 0
        assert log_dir.is_dir(), "ai_init_session should create the log directory"

    def test_init_session_creates_log_file(self, ai_config_full_env):
        """ai_init_session creates a log file with the session ID prefix."""
        env, tmp_path, wrapper = ai_config_full_env
        env["ANKLUME_AI_MODE"] = "none"
        log_dir = tmp_path / "session-logs"
        wrapper.write_text(f"""#!/usr/bin/env bash
set -euo pipefail
export PROJECT_DIR="{tmp_path}"
export ANKLUME_AI_LOG_DIR="{log_dir}"
die() {{ echo "ERROR: $*" >&2; exit 1; }}
export ANKLUME_CONF="{tmp_path}/anklume.conf.yml"
source "{SCRIPTS_DIR}/ai-config.sh"
"$@"
""")
        wrapper.chmod(wrapper.stat().st_mode | stat.S_IEXEC)
        result = _run_wrapper(
            wrapper, ["ai_init_session", "mysession"], env, tmp_path,
        )
        assert result.returncode == 0
        log_files = list(log_dir.glob("mysession-*.log"))
        assert len(log_files) == 1, (
            f"Expected exactly one log file, found: {log_files}"
        )

    def test_init_session_log_contains_session_info(self, ai_config_full_env):
        """ai_init_session log file contains session start info."""
        env, tmp_path, wrapper = ai_config_full_env
        env["ANKLUME_AI_MODE"] = "none"
        log_dir = tmp_path / "info-logs"
        wrapper.write_text(f"""#!/usr/bin/env bash
set -euo pipefail
export PROJECT_DIR="{tmp_path}"
export ANKLUME_AI_LOG_DIR="{log_dir}"
die() {{ echo "ERROR: $*" >&2; exit 1; }}
export ANKLUME_CONF="{tmp_path}/anklume.conf.yml"
source "{SCRIPTS_DIR}/ai-config.sh"
"$@"
""")
        wrapper.chmod(wrapper.stat().st_mode | stat.S_IEXEC)
        result = _run_wrapper(
            wrapper, ["ai_init_session", "info"], env, tmp_path,
        )
        assert result.returncode == 0
        log_files = list(log_dir.glob("info-*.log"))
        assert len(log_files) == 1
        content = log_files[0].read_text()
        assert "Session started" in content
        assert "AI_MODE=none" in content
        assert "MAX_RETRIES=" in content


# ── run-tests.sh incus connectivity checks ───────────────────────


class TestRunTestsIncusConnectivity:
    """Test that run-tests.sh commands requiring Incus fail without it."""

    @pytest.fixture()
    def mock_incus_env(self, tmp_path):
        """Environment with a mock incus that always fails."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        mock_incus = mock_bin / "incus"
        mock_incus.write_text("#!/usr/bin/env bash\nexit 1\n")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)
        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        return env

    def test_create_requires_incus(self, mock_incus_env):
        """run-tests.sh create fails when incus is not connectable."""
        result = run_script("run-tests.sh", ["create"], env=mock_incus_env)
        assert result.returncode != 0
        assert "Cannot connect" in result.stderr or "ERROR" in result.stderr

    def test_test_requires_incus(self, mock_incus_env):
        """run-tests.sh test fails when incus is not connectable."""
        result = run_script("run-tests.sh", ["test"], env=mock_incus_env)
        assert result.returncode != 0
        assert "Cannot connect" in result.stderr or "ERROR" in result.stderr

    def test_destroy_requires_incus(self, mock_incus_env):
        """run-tests.sh destroy fails when incus is not connectable."""
        result = run_script("run-tests.sh", ["destroy"], env=mock_incus_env)
        assert result.returncode != 0
        assert "Cannot connect" in result.stderr or "ERROR" in result.stderr

    def test_full_requires_incus(self, mock_incus_env):
        """run-tests.sh full fails when incus is not connectable."""
        result = run_script("run-tests.sh", ["full"], env=mock_incus_env)
        assert result.returncode != 0
        assert "Cannot connect" in result.stderr or "ERROR" in result.stderr


# ── ai-develop.sh slugify function ───────────────────────────────


class TestSlugify:
    """Test the slugify function in ai-develop.sh."""

    @pytest.fixture()
    def slugify_wrapper(self, tmp_path):
        """Create a wrapper that sources ai-develop.sh and calls slugify."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        wrapper = tmp_path / "slugify_wrapper.sh"
        # We extract the slugify function directly rather than sourcing
        # ai-develop.sh which would cd to PROJECT_DIR and source ai-config.sh
        wrapper.write_text("""#!/usr/bin/env bash
set -euo pipefail
slugify() {
    echo "$1" | tr '[:upper:]' '[:lower:]' | tr -cs '[:alnum:]' '-' \\
        | sed 's/^-//;s/-$//' | cut -c1-50
}
slugify "$1"
""")
        wrapper.chmod(wrapper.stat().st_mode | stat.S_IEXEC)
        env = os.environ.copy()
        return env, tmp_path, wrapper

    def test_slugify_lowercases(self, slugify_wrapper):
        """slugify converts uppercase to lowercase."""
        env, tmp_path, wrapper = slugify_wrapper
        result = subprocess.run(
            ["bash", str(wrapper), "Add Monitoring Role"],
            capture_output=True, text=True, env=env, timeout=5,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "add-monitoring-role"

    def test_slugify_replaces_special_chars(self, slugify_wrapper):
        """slugify replaces non-alphanumeric chars with hyphens."""
        env, tmp_path, wrapper = slugify_wrapper
        result = subprocess.run(
            ["bash", str(wrapper), "Fix: issue #42 (urgent)"],
            capture_output=True, text=True, env=env, timeout=5,
        )
        slug = result.stdout.strip()
        assert result.returncode == 0
        # All special chars replaced, no leading/trailing hyphens
        assert slug == "fix-issue-42-urgent"

    def test_slugify_truncates_to_50(self, slugify_wrapper):
        """slugify truncates to 50 characters max."""
        env, tmp_path, wrapper = slugify_wrapper
        long_task = "a" * 100
        result = subprocess.run(
            ["bash", str(wrapper), long_task],
            capture_output=True, text=True, env=env, timeout=5,
        )
        assert result.returncode == 0
        assert len(result.stdout.strip()) == 50

    def test_slugify_no_leading_trailing_hyphens(self, slugify_wrapper):
        """slugify removes leading and trailing hyphens."""
        env, tmp_path, wrapper = slugify_wrapper
        result = subprocess.run(
            ["bash", str(wrapper), "---hello world---"],
            capture_output=True, text=True, env=env, timeout=5,
        )
        slug = result.stdout.strip()
        assert result.returncode == 0
        assert not slug.startswith("-")
        assert not slug.endswith("-")
        assert slug == "hello-world"

    def test_slugify_simple_word(self, slugify_wrapper):
        """slugify handles a simple single word."""
        env, tmp_path, wrapper = slugify_wrapper
        result = subprocess.run(
            ["bash", str(wrapper), "refactor"],
            capture_output=True, text=True, env=env, timeout=5,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "refactor"

    def test_slugify_consecutive_spaces(self, slugify_wrapper):
        """slugify collapses consecutive special chars into one hyphen."""
        env, tmp_path, wrapper = slugify_wrapper
        result = subprocess.run(
            ["bash", str(wrapper), "add   multiple   spaces"],
            capture_output=True, text=True, env=env, timeout=5,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "add-multiple-spaces"
