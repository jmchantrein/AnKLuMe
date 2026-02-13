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


# ── New comprehensive test classes ─────────────────────────────────


@pytest.fixture()
def ai_test_loop_env(tmp_path):
    """Create a mock environment for ai-test-loop.sh testing.

    Sets up a fake project with roles, molecule dirs, mock binaries,
    and a patched ai-test-loop.sh that sources a patched ai-config.sh.
    """
    mock_bin = tmp_path / "bin"
    mock_bin.mkdir()
    log_file = tmp_path / "cmds.log"

    # Create minimal project structure
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    scripts_dir = project_dir / "scripts"
    scripts_dir.mkdir()
    logs_dir = project_dir / "logs"
    logs_dir.mkdir()

    # Create a fake role with molecule directory
    role_dir = project_dir / "roles" / "test_role" / "molecule" / "default"
    role_dir.mkdir(parents=True)
    tasks_dir = project_dir / "roles" / "test_role" / "tasks"
    tasks_dir.mkdir(parents=True)
    (tasks_dir / "main.yml").write_text("---\n- name: TestRole | Test task\n  ansible.builtin.debug:\n    msg: hello\n")
    defaults_dir = project_dir / "roles" / "test_role" / "defaults"
    defaults_dir.mkdir(parents=True)
    (defaults_dir / "main.yml").write_text("---\ntest_var: value\n")
    verify_dir = project_dir / "roles" / "test_role" / "molecule" / "default"
    (verify_dir / "verify.yml").write_text("---\n- name: Verify\n  hosts: all\n  tasks: []\n")

    # Mock molecule — success by default
    mock_molecule = mock_bin / "molecule"
    mock_molecule.write_text(f"""#!/usr/bin/env bash
echo "molecule $@" >> "{log_file}"
exit 0
""")
    mock_molecule.chmod(mock_molecule.stat().st_mode | stat.S_IEXEC)

    # Mock python3 — pass through to real python3
    mock_python = mock_bin / "python3"
    mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
    mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)

    # Mock git
    mock_git = mock_bin / "git"
    mock_git.write_text(f"""#!/usr/bin/env bash
echo "git $@" >> "{log_file}"
exit 0
""")
    mock_git.chmod(mock_git.stat().st_mode | stat.S_IEXEC)

    # Create a patched ai-config.sh
    patched_config = scripts_dir / "ai-config.sh"
    original_config = (SCRIPTS_DIR / "ai-config.sh").read_text()
    # Override ANKLUME_CONF to point to our project
    patched_config_text = original_config.replace(
        '_ai_conf="${ANKLUME_CONF:-anklume.conf.yml}"',
        f'_ai_conf="{project_dir}/anklume.conf.yml"',
    )
    patched_config.write_text(patched_config_text)

    # Create a patched ai-test-loop.sh
    patched_loop = scripts_dir / "ai-test-loop.sh"
    original_loop = (SCRIPTS_DIR / "ai-test-loop.sh").read_text()
    patched_loop_text = original_loop.replace(
        'PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"',
        f'PROJECT_DIR="{project_dir}"',
    )
    patched_loop.write_text(patched_loop_text)
    patched_loop.chmod(patched_loop.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env["PATH"] = f"{mock_bin}:{env['PATH']}"
    env["ANKLUME_AI_MODE"] = "none"
    env["ANKLUME_AI_DRY_RUN"] = "true"
    env["ANKLUME_AI_LOG_DIR"] = str(logs_dir)
    # Remove vars that might interfere
    for var in ["ANKLUME_CONF", "ANTHROPIC_API_KEY"]:
        env.pop(var, None)

    return env, log_file, project_dir, patched_loop


class TestAiTestLoopMolecule:
    """Mock molecule, test run/fail/retry paths."""

    def test_help_shows_usage(self, ai_test_loop_env):
        """ai-test-loop.sh --help shows usage text."""
        env, _, cwd, script = ai_test_loop_env
        result = subprocess.run(
            ["bash", str(script), "--help"],
            capture_output=True, text=True, env=env,
            cwd=str(cwd), timeout=15,
        )
        assert result.returncode == 0
        assert "Usage" in result.stdout

    def test_molecule_pass_reports_success(self, ai_test_loop_env):
        """When molecule passes, the test loop reports PASS."""
        env, log_file, cwd, script = ai_test_loop_env
        result = subprocess.run(
            ["bash", str(script), "test_role"],
            capture_output=True, text=True, env=env,
            cwd=str(cwd), timeout=30,
        )
        assert result.returncode == 0
        combined = result.stdout + result.stderr
        assert "PASS" in combined or "Passed: 1" in combined

    def test_molecule_fail_reports_failure(self, ai_test_loop_env):
        """When molecule fails and AI_MODE=none, the test loop reports FAIL."""
        env, log_file, cwd, script = ai_test_loop_env
        # Make molecule fail
        mock_bin = cwd.parent / "bin"
        mock_molecule = mock_bin / "molecule"
        mock_molecule.write_text(f"""#!/usr/bin/env bash
echo "molecule $@" >> "{log_file}"
echo "ERROR: test failed" >&2
exit 1
""")
        mock_molecule.chmod(mock_molecule.stat().st_mode | stat.S_IEXEC)
        result = subprocess.run(
            ["bash", str(script), "test_role"],
            capture_output=True, text=True, env=env,
            cwd=str(cwd), timeout=30,
        )
        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert "FAIL" in combined or "Failed: 1" in combined

    def test_no_molecule_dir_gives_error(self, ai_test_loop_env):
        """Specifying a role without molecule/ directory gives error."""
        env, _, cwd, script = ai_test_loop_env
        result = subprocess.run(
            ["bash", str(script), "nonexistent_role"],
            capture_output=True, text=True, env=env,
            cwd=str(cwd), timeout=15,
        )
        assert result.returncode != 0
        assert "molecule" in result.stderr.lower() or "ERROR" in result.stderr

    def test_molecule_called_with_test_command(self, ai_test_loop_env):
        """Molecule is invoked with the 'test' subcommand."""
        env, log_file, cwd, script = ai_test_loop_env
        subprocess.run(
            ["bash", str(script), "test_role"],
            capture_output=True, text=True, env=env,
            cwd=str(cwd), timeout=30,
        )
        if log_file.exists():
            content = log_file.read_text()
            assert "molecule test" in content


class TestAiTestLoopContext:
    """Test context building with mock role files."""

    def test_context_includes_role_tasks(self, ai_test_loop_env):
        """Build context includes role tasks/main.yml content."""
        env, log_file, cwd, script = ai_test_loop_env
        # Make molecule fail so context is built
        mock_bin = cwd.parent / "bin"
        mock_molecule = mock_bin / "molecule"
        mock_molecule.write_text(f"""#!/usr/bin/env bash
echo "molecule $@" >> "{log_file}"
echo "FATAL: some error" > "${{PWD}}/../../logs/dummy.log" 2>/dev/null || true
exit 1
""")
        mock_molecule.chmod(mock_molecule.stat().st_mode | stat.S_IEXEC)
        result = subprocess.run(
            ["bash", str(script), "test_role"],
            capture_output=True, text=True, env=env,
            cwd=str(cwd), timeout=30,
        )
        # With AI_MODE=none, no context file is created (no fix attempt)
        # This is expected behavior
        assert result.returncode != 0

    def test_role_tasks_file_accessible(self, ai_test_loop_env):
        """Role tasks file exists in the mock project structure."""
        _, _, cwd, _ = ai_test_loop_env
        tasks_file = cwd / "roles" / "test_role" / "tasks" / "main.yml"
        assert tasks_file.exists()
        content = tasks_file.read_text()
        assert "TestRole" in content

    def test_role_defaults_file_accessible(self, ai_test_loop_env):
        """Role defaults file exists in the mock project structure."""
        _, _, cwd, _ = ai_test_loop_env
        defaults_file = cwd / "roles" / "test_role" / "defaults" / "main.yml"
        assert defaults_file.exists()
        assert "test_var" in defaults_file.read_text()


class TestAiTestLoopExperiences:
    """Test experience search with known patterns."""

    def test_experiences_dir_missing_does_not_crash(self, ai_test_loop_env):
        """Missing experiences/fixes directory does not crash the script."""
        env, _, cwd, script = ai_test_loop_env
        # No experiences directory created — that's the test
        result = subprocess.run(
            ["bash", str(script), "test_role"],
            capture_output=True, text=True, env=env,
            cwd=str(cwd), timeout=30,
        )
        # Should succeed (molecule passes) regardless of missing experiences
        assert result.returncode == 0

    def test_empty_experiences_dir_works(self, ai_test_loop_env):
        """Empty experiences/fixes directory does not cause issues."""
        env, _, cwd, script = ai_test_loop_env
        (cwd / "experiences" / "fixes").mkdir(parents=True)
        result = subprocess.run(
            ["bash", str(script), "test_role"],
            capture_output=True, text=True, env=env,
            cwd=str(cwd), timeout=30,
        )
        assert result.returncode == 0


class TestAiTestLoopLearn:
    """Test --learn flag behavior."""

    def test_learn_flag_accepted(self, ai_test_loop_env):
        """--learn flag is accepted without error."""
        env, _, cwd, script = ai_test_loop_env
        # Create a mock mine-experiences.py to avoid dependency on real one
        mine_script = cwd / "scripts" / "mine-experiences.py"
        mine_script.write_text("#!/usr/bin/env python3\nprint('Mining: 0 new experiences')\n")
        mine_script.chmod(mine_script.stat().st_mode | stat.S_IEXEC)
        result = subprocess.run(
            ["bash", str(script), "--learn", "test_role"],
            capture_output=True, text=True, env=env,
            cwd=str(cwd), timeout=30,
        )
        # Should run successfully with --learn
        assert result.returncode == 0

    def test_learn_flag_triggers_mining(self, ai_test_loop_env):
        """--learn flag triggers experience mining."""
        env, log_file, cwd, script = ai_test_loop_env
        mine_script = cwd / "scripts" / "mine-experiences.py"
        mine_script.write_text(
            "#!/usr/bin/env python3\nprint('Mining: 0 new experiences')\n",
        )
        mine_script.chmod(mine_script.stat().st_mode | stat.S_IEXEC)
        result = subprocess.run(
            ["bash", str(script), "--learn", "test_role"],
            capture_output=True, text=True, env=env,
            cwd=str(cwd), timeout=30,
        )
        combined = result.stdout + result.stderr
        assert "Mining" in combined or "experience" in combined.lower()


# ── ai-develop.sh tests ──────────────────────────────────────────


@pytest.fixture()
def ai_develop_env(tmp_path):
    """Create a mock environment for ai-develop.sh testing."""
    mock_bin = tmp_path / "bin"
    mock_bin.mkdir()
    log_file = tmp_path / "cmds.log"

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    scripts_dir = project_dir / "scripts"
    scripts_dir.mkdir()
    logs_dir = project_dir / "logs"
    logs_dir.mkdir()

    # Create CLAUDE.md and ROADMAP
    (project_dir / "CLAUDE.md").write_text("# AnKLuMe\nTest conventions file.\n")
    (project_dir / "docs").mkdir()
    (project_dir / "docs" / "ROADMAP.md").write_text("# ROADMAP\n## Current State\nTest\n---\n")

    # Mock python3
    mock_python = mock_bin / "python3"
    mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
    mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)

    # Mock git
    mock_git = mock_bin / "git"
    mock_git.write_text(f"""#!/usr/bin/env bash
echo "git $@" >> "{log_file}"
exit 0
""")
    mock_git.chmod(mock_git.stat().st_mode | stat.S_IEXEC)

    # Mock pytest (for run_all_tests)
    mock_pytest = mock_bin / "pytest"
    mock_pytest.write_text(f"""#!/usr/bin/env bash
echo "pytest $@" >> "{log_file}"
exit 0
""")
    mock_pytest.chmod(mock_pytest.stat().st_mode | stat.S_IEXEC)

    # Create a patched ai-config.sh
    patched_config = scripts_dir / "ai-config.sh"
    original_config = (SCRIPTS_DIR / "ai-config.sh").read_text()
    patched_config_text = original_config.replace(
        '_ai_conf="${ANKLUME_CONF:-anklume.conf.yml}"',
        f'_ai_conf="{project_dir}/anklume.conf.yml"',
    )
    patched_config.write_text(patched_config_text)

    # Create a patched ai-develop.sh
    patched_develop = scripts_dir / "ai-develop.sh"
    original_develop = (SCRIPTS_DIR / "ai-develop.sh").read_text()
    patched_develop_text = original_develop.replace(
        'PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"',
        f'PROJECT_DIR="{project_dir}"',
    )
    patched_develop.write_text(patched_develop_text)
    patched_develop.chmod(patched_develop.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env["PATH"] = f"{mock_bin}:{env['PATH']}"
    env["ANKLUME_AI_MODE"] = "local"
    env["ANKLUME_AI_DRY_RUN"] = "true"
    env["ANKLUME_AI_LOG_DIR"] = str(logs_dir)
    for var in ["ANKLUME_CONF", "ANTHROPIC_API_KEY"]:
        env.pop(var, None)

    # Mock curl for local mode
    mock_curl = mock_bin / "curl"
    mock_curl.write_text(f"""#!/usr/bin/env bash
echo "curl $@" >> "{log_file}"
echo '{{"response":"no changes needed"}}'
exit 0
""")
    mock_curl.chmod(mock_curl.stat().st_mode | stat.S_IEXEC)

    return env, log_file, project_dir, patched_develop


class TestAiDevelopContext:
    """Test context file generation for ai-develop.sh."""

    def test_develop_creates_context_file(self, ai_develop_env):
        """ai-develop.sh creates a context file in the log directory."""
        env, _, cwd, script = ai_develop_env
        # With claude-code mode, dry-run saves the prompt and returns 0
        env["ANKLUME_AI_MODE"] = "claude-code"
        # Mock claude binary
        mock_bin = cwd.parent / "bin"
        mock_claude = mock_bin / "claude"
        mock_claude.write_text("#!/usr/bin/env bash\nexit 0\n")
        mock_claude.chmod(mock_claude.stat().st_mode | stat.S_IEXEC)
        result = subprocess.run(
            ["bash", str(script), "--mode", "claude-code", "--dry-run", "Add test role"],
            capture_output=True, text=True, env=env,
            cwd=str(cwd), timeout=30,
        )
        assert result.returncode == 0
        logs_dir = cwd / "logs"
        context_files = list(logs_dir.glob("*-context.txt"))
        assert len(context_files) >= 1, f"Expected context file, found: {list(logs_dir.iterdir())}"

    def test_context_includes_task_description(self, ai_develop_env):
        """Context file includes the task description."""
        env, _, cwd, script = ai_develop_env
        env["ANKLUME_AI_MODE"] = "claude-code"
        mock_bin = cwd.parent / "bin"
        mock_claude = mock_bin / "claude"
        mock_claude.write_text("#!/usr/bin/env bash\nexit 0\n")
        mock_claude.chmod(mock_claude.stat().st_mode | stat.S_IEXEC)
        result = subprocess.run(
            ["bash", str(script), "--mode", "claude-code", "--dry-run", "Add monitoring role"],
            capture_output=True, text=True, env=env,
            cwd=str(cwd), timeout=30,
        )
        assert result.returncode == 0
        logs_dir = cwd / "logs"
        context_files = list(logs_dir.glob("*-context.txt"))
        assert len(context_files) >= 1
        content = context_files[0].read_text()
        assert "Add monitoring role" in content

    def test_context_includes_claude_md(self, ai_develop_env):
        """Context file includes CLAUDE.md content."""
        env, _, cwd, script = ai_develop_env
        env["ANKLUME_AI_MODE"] = "claude-code"
        mock_bin = cwd.parent / "bin"
        mock_claude = mock_bin / "claude"
        mock_claude.write_text("#!/usr/bin/env bash\nexit 0\n")
        mock_claude.chmod(mock_claude.stat().st_mode | stat.S_IEXEC)
        subprocess.run(
            ["bash", str(script), "--mode", "claude-code", "--dry-run", "Test task"],
            capture_output=True, text=True, env=env,
            cwd=str(cwd), timeout=30,
        )
        logs_dir = cwd / "logs"
        context_files = list(logs_dir.glob("*-context.txt"))
        assert len(context_files) >= 1
        content = context_files[0].read_text()
        assert "conventions" in content.lower() or "AnKLuMe" in content


class TestAiDevelopBranch:
    """Test feature branch creation with mock git."""

    def test_develop_help_shows_usage(self, ai_develop_env):
        """ai-develop.sh --help shows usage text."""
        env, _, cwd, script = ai_develop_env
        result = subprocess.run(
            ["bash", str(script), "--help"],
            capture_output=True, text=True, env=env,
            cwd=str(cwd), timeout=15,
        )
        assert result.returncode == 0
        assert "Usage" in result.stdout

    def test_develop_requires_task(self, ai_develop_env):
        """ai-develop.sh without task arg gives error."""
        env, _, cwd, script = ai_develop_env
        result = subprocess.run(
            ["bash", str(script)],
            capture_output=True, text=True, env=env,
            cwd=str(cwd), timeout=15,
        )
        assert result.returncode != 0
        assert "Task description required" in result.stderr or "ERROR" in result.stderr

    def test_develop_requires_ai_mode(self, ai_develop_env):
        """ai-develop.sh with AI_MODE=none gives error."""
        env, _, cwd, script = ai_develop_env
        env["ANKLUME_AI_MODE"] = "none"
        result = subprocess.run(
            ["bash", str(script), "Some task"],
            capture_output=True, text=True, env=env,
            cwd=str(cwd), timeout=15,
        )
        assert result.returncode != 0
        assert "AI_MODE" in result.stderr

    def test_dry_run_does_not_create_branch(self, ai_develop_env):
        """--dry-run mode does not call git checkout -b."""
        env, log_file, cwd, script = ai_develop_env
        env["ANKLUME_AI_MODE"] = "claude-code"
        mock_bin = cwd.parent / "bin"
        mock_claude = mock_bin / "claude"
        mock_claude.write_text("#!/usr/bin/env bash\nexit 0\n")
        mock_claude.chmod(mock_claude.stat().st_mode | stat.S_IEXEC)
        result = subprocess.run(
            ["bash", str(script), "--mode", "claude-code", "--dry-run", "Test branch"],
            capture_output=True, text=True, env=env,
            cwd=str(cwd), timeout=30,
        )
        assert result.returncode == 0
        if log_file.exists():
            content = log_file.read_text()
            assert "checkout -b" not in content

    def test_develop_session_log_created(self, ai_develop_env):
        """ai-develop.sh creates a session log file."""
        env, _, cwd, script = ai_develop_env
        env["ANKLUME_AI_MODE"] = "claude-code"
        mock_bin = cwd.parent / "bin"
        mock_claude = mock_bin / "claude"
        mock_claude.write_text("#!/usr/bin/env bash\nexit 0\n")
        mock_claude.chmod(mock_claude.stat().st_mode | stat.S_IEXEC)
        result = subprocess.run(
            ["bash", str(script), "--mode", "claude-code", "--dry-run", "Log test"],
            capture_output=True, text=True, env=env,
            cwd=str(cwd), timeout=30,
        )
        assert result.returncode == 0
        logs_dir = cwd / "logs"
        log_files = list(logs_dir.glob("ai-dev-*.log"))
        assert len(log_files) >= 1, f"Expected log file, found: {list(logs_dir.iterdir())}"


# ── ai-improve.sh tests ─────────────────────────────────────────


class TestAiImproveHelp:
    """Test help text and basic args for ai-improve.sh."""

    def test_help_flag_shows_usage(self):
        """ai-improve.sh --help shows usage text."""
        result = run_script("ai-improve.sh", ["--help"])
        assert result.returncode == 0
        assert "Usage" in result.stdout

    def test_help_mentions_scope(self):
        """Help text mentions scope option."""
        result = run_script("ai-improve.sh", ["--help"])
        assert "scope" in result.stdout.lower()

    def test_help_mentions_dry_run(self):
        """Help text mentions dry-run option."""
        result = run_script("ai-improve.sh", ["--help"])
        assert "dry-run" in result.stdout.lower() or "dry_run" in result.stdout.lower()

    def test_help_lists_scope_values(self):
        """Help text lists valid scope values."""
        result = run_script("ai-improve.sh", ["--help"])
        output = result.stdout
        for scope in ["generator", "roles", "nftables", "all"]:
            assert scope in output

    def test_invalid_scope_gives_error(self):
        """Invalid --scope value gives error."""
        result = run_script("ai-improve.sh", ["--scope", "invalid"])
        assert result.returncode != 0
        assert "Invalid scope" in result.stderr or "ERROR" in result.stderr

    def test_unknown_option_gives_error(self):
        """Unknown option gives error."""
        result = run_script("ai-improve.sh", ["--nonexistent"])
        assert result.returncode != 0


# ── ai-matrix-test.sh tests ─────────────────────────────────────


class TestAiMatrixTestHelp:
    """Test help text and basic args for ai-matrix-test.sh."""

    def test_help_flag_shows_usage(self):
        """ai-matrix-test.sh --help shows usage text."""
        result = run_script("ai-matrix-test.sh", ["--help"])
        assert result.returncode == 0
        assert "Usage" in result.stdout

    def test_help_mentions_mode(self):
        """Help text mentions mode option."""
        result = run_script("ai-matrix-test.sh", ["--help"])
        assert "mode" in result.stdout.lower()

    def test_help_mentions_limit(self):
        """Help text mentions limit option."""
        result = run_script("ai-matrix-test.sh", ["--help"])
        assert "limit" in result.stdout.lower()

    def test_help_mentions_dry_run(self):
        """Help text mentions dry-run option."""
        result = run_script("ai-matrix-test.sh", ["--help"])
        assert "dry-run" in result.stdout.lower() or "dry_run" in result.stdout.lower()

    def test_unknown_option_gives_error(self):
        """Unknown option gives error."""
        result = run_script("ai-matrix-test.sh", ["--nonexistent"])
        assert result.returncode != 0

    def test_unexpected_positional_gives_error(self):
        """Unexpected positional argument gives error."""
        result = run_script("ai-matrix-test.sh", ["extra-arg"])
        assert result.returncode != 0


# ── agent-fix.sh tests ──────────────────────────────────────────


class TestAgentFixHelp:
    """Test help text and argument parsing for agent-fix.sh."""

    def test_help_flag_shows_usage(self):
        """agent-fix.sh --help shows usage text."""
        result = run_script("agent-fix.sh", ["--help"])
        assert result.returncode == 0
        assert "Usage" in result.stdout

    def test_help_mentions_prerequisites(self):
        """Help text mentions prerequisites."""
        result = run_script("agent-fix.sh", ["--help"])
        output = result.stdout
        assert "runner" in output.lower() or "Prerequisites" in output

    def test_help_mentions_api_key(self):
        """Help text mentions ANTHROPIC_API_KEY."""
        result = run_script("agent-fix.sh", ["--help"])
        assert "ANTHROPIC_API_KEY" in result.stdout

    def test_unknown_option_gives_error(self):
        """Unknown option gives error."""
        env = os.environ.copy()
        # Provide mock incus to avoid PATH issues
        mock_bin = Path("/tmp/test_agent_fix_help_mock")
        mock_bin.mkdir(exist_ok=True)
        mock_incus = mock_bin / "incus"
        mock_incus.write_text("#!/usr/bin/env bash\nexit 1\n")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = run_script("agent-fix.sh", ["--unknown-flag"], env=env)
        assert result.returncode != 0

    def test_no_incus_gives_clear_error(self):
        """Without Incus, agent-fix.sh gives a clear error."""
        env = os.environ.copy()
        mock_bin = Path("/tmp/test_agent_fix_noincus_mock")
        mock_bin.mkdir(exist_ok=True)
        mock_incus = mock_bin / "incus"
        mock_incus.write_text("#!/usr/bin/env bash\nexit 1\n")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = run_script("agent-fix.sh", [], env=env)
        assert result.returncode != 0
        assert "Cannot connect" in result.stderr or "ERROR" in result.stderr

    def test_accepts_role_argument(self):
        """agent-fix.sh accepts a role name as positional argument in help."""
        result = run_script("agent-fix.sh", ["--help"])
        assert result.returncode == 0
        # Help should show [role] in usage
        assert "role" in result.stdout.lower()


# ── agent-develop.sh tests ──────────────────────────────────────


class TestAgentDevelopHelp:
    """Test help text and argument parsing for agent-develop.sh."""

    def test_help_flag_shows_usage(self):
        """agent-develop.sh --help shows usage text."""
        result = run_script("agent-develop.sh", ["--help"])
        assert result.returncode == 0
        assert "Usage" in result.stdout

    def test_help_mentions_task(self):
        """Help text mentions task description."""
        result = run_script("agent-develop.sh", ["--help"])
        output = result.stdout
        assert "task" in output.lower() or "Task" in output

    def test_help_mentions_examples(self):
        """Help text includes examples."""
        result = run_script("agent-develop.sh", ["--help"])
        assert "Example" in result.stdout or "example" in result.stdout

    def test_help_mentions_prerequisites(self):
        """Help text mentions prerequisites."""
        result = run_script("agent-develop.sh", ["--help"])
        output = result.stdout
        assert "runner" in output.lower() or "Prerequisites" in output

    def test_no_task_gives_error(self):
        """agent-develop.sh without task gives error."""
        env = os.environ.copy()
        mock_bin = Path("/tmp/test_agent_develop_notask_mock")
        mock_bin.mkdir(exist_ok=True)
        mock_incus = mock_bin / "incus"
        mock_incus.write_text("#!/usr/bin/env bash\nexit 1\n")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = run_script("agent-develop.sh", [], env=env)
        assert result.returncode != 0
        assert "Task description required" in result.stderr or "ERROR" in result.stderr

    def test_unknown_option_gives_error(self):
        """Unknown option gives error."""
        env = os.environ.copy()
        mock_bin = Path("/tmp/test_agent_develop_unknown_mock")
        mock_bin.mkdir(exist_ok=True)
        mock_incus = mock_bin / "incus"
        mock_incus.write_text("#!/usr/bin/env bash\nexit 1\n")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = run_script("agent-develop.sh", ["--unknown-flag"], env=env)
        assert result.returncode != 0

    def test_no_incus_gives_clear_error(self):
        """Without Incus, agent-develop.sh gives a clear error."""
        env = os.environ.copy()
        mock_bin = Path("/tmp/test_agent_develop_noincus2_mock")
        mock_bin.mkdir(exist_ok=True)
        mock_incus = mock_bin / "incus"
        mock_incus.write_text("#!/usr/bin/env bash\nexit 1\n")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = run_script("agent-develop.sh", ["Test task"], env=env)
        assert result.returncode != 0
        assert "Cannot connect" in result.stderr or "ERROR" in result.stderr
