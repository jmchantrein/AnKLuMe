"""Tests for AI/agent orchestration scripts — config loading, mode selection, safety."""

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


# ── ai-config.sh config loading ──────────────────────────────────


@pytest.fixture()
def ai_config_env(tmp_path):
    """Create environment for testing ai-config.sh functions."""
    mock_bin = tmp_path / "bin"
    mock_bin.mkdir()
    wrapper = tmp_path / "test_wrapper.sh"
    wrapper.write_text(f"""#!/usr/bin/env bash
set -euo pipefail
export PROJECT_DIR="{tmp_path}"
source "{SCRIPTS_DIR}/ai-config.sh"
"$@"
""")
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env["PATH"] = f"{mock_bin}:{env['PATH']}"
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


# ── ai-config.sh full config loading ─────────────────────────────


@pytest.fixture()
def ai_config_full_env(tmp_path):
    """Create environment for testing ai-config.sh with die() and functions."""
    mock_bin = tmp_path / "bin"
    mock_bin.mkdir()
    wrapper = tmp_path / "test_full_wrapper.sh"
    wrapper.write_text(f"""#!/usr/bin/env bash
set -euo pipefail
export PROJECT_DIR="{tmp_path}"
die() {{ echo "ERROR: $*" >&2; exit 1; }}
export ANKLUME_CONF="{tmp_path}/anklume.conf.yml"
source "{SCRIPTS_DIR}/ai-config.sh"
"$@"
""")
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env["PATH"] = f"{mock_bin}:{env['PATH']}"
    env["ANKLUME_CONF"] = str(tmp_path / "anklume.conf.yml")
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

    def test_loads_mode(self, ai_config_full_env):
        """Config file value for ai.mode is loaded into AI_MODE."""
        env, tmp_path, wrapper = ai_config_full_env
        conf = tmp_path / "anklume.conf.yml"
        conf.write_text("ai:\n  mode: local\n")
        result = _source_and_echo(wrapper, "AI_MODE", env, tmp_path)
        assert result.stdout.strip() == "local"

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

    def test_loads_max_retries(self, ai_config_full_env):
        """Config file value for ai.max_retries is loaded into AI_MAX_RETRIES."""
        env, tmp_path, wrapper = ai_config_full_env
        conf = tmp_path / "anklume.conf.yml"
        conf.write_text("ai:\n  mode: none\n  max_retries: 7\n")
        result = _source_and_echo(wrapper, "AI_MAX_RETRIES", env, tmp_path)
        assert result.stdout.strip() == "7"

    def test_loads_dry_run(self, ai_config_full_env):
        """Config file value for ai.dry_run is loaded into AI_DRY_RUN."""
        env, tmp_path, wrapper = ai_config_full_env
        conf = tmp_path / "anklume.conf.yml"
        conf.write_text("ai:\n  mode: none\n  dry_run: false\n")
        result = _source_and_echo(wrapper, "AI_DRY_RUN", env, tmp_path)
        assert result.stdout.strip() == "False"


class TestAiConfigDefaults:
    """Test default values when no config file exists."""

    def test_default_mode_is_none(self, ai_config_full_env):
        """Without config file, AI_MODE defaults to 'none'."""
        env, tmp_path, wrapper = ai_config_full_env
        result = _source_and_echo(wrapper, "AI_MODE", env, tmp_path)
        assert result.stdout.strip() == "none"

    def test_default_dry_run(self, ai_config_full_env):
        """Without config file, AI_DRY_RUN defaults to true."""
        env, tmp_path, wrapper = ai_config_full_env
        result = _source_and_echo(wrapper, "AI_DRY_RUN", env, tmp_path)
        assert result.stdout.strip() == "true"

    def test_default_max_retries(self, ai_config_full_env):
        """Without config file, AI_MAX_RETRIES defaults to 3."""
        env, tmp_path, wrapper = ai_config_full_env
        result = _source_and_echo(wrapper, "AI_MAX_RETRIES", env, tmp_path)
        assert result.stdout.strip() == "3"


class TestAiConfigEnvOverride:
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
        assert "remote" in result.stdout or result.returncode != 0


# ── ai-config.sh validation function ─────────────────────────────


class TestAiValidateConfigModes:
    """Test ai_validate_config with each valid and invalid AI_MODE."""

    @pytest.mark.parametrize("mode", ["none", "local", "remote", "claude-code", "aider"])
    def test_valid_modes_accepted(self, ai_config_full_env, mode):
        """ai_validate_config accepts all valid AI_MODE values."""
        env, tmp_path, wrapper = ai_config_full_env
        env["ANKLUME_AI_MODE"] = mode
        mock_bin = tmp_path / "bin"
        for binary in ["curl", "claude", "aider"]:
            mock = mock_bin / binary
            mock.write_text("#!/usr/bin/env bash\nexit 0\n")
            mock.chmod(mock.stat().st_mode | stat.S_IEXEC)
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

    def test_local_mode_without_curl_errors(self, ai_config_full_env):
        """AI_MODE=local without curl gives error."""
        env, tmp_path, wrapper = ai_config_full_env
        env["ANKLUME_AI_MODE"] = "local"
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


# ── ai-config.sh session initialization ──────────────────────────


class TestAiInitSession:
    """Test ai_init_session creates log directory and file."""

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
        assert log_dir.is_dir()
        log_files = list(log_dir.glob("mysession-*.log"))
        assert len(log_files) == 1


# ── ai-test-loop.sh mock tests ──────────────────────────────────


@pytest.fixture()
def ai_test_loop_env(tmp_path):
    """Create a mock environment for ai-test-loop.sh testing."""
    mock_bin = tmp_path / "bin"
    mock_bin.mkdir()
    log_file = tmp_path / "cmds.log"

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
    (role_dir / "verify.yml").write_text("---\n- name: Verify\n  hosts: all\n  tasks: []\n")

    # Mock molecule
    mock_molecule = mock_bin / "molecule"
    mock_molecule.write_text(f"""#!/usr/bin/env bash
echo "molecule $@" >> "{log_file}"
exit 0
""")
    mock_molecule.chmod(mock_molecule.stat().st_mode | stat.S_IEXEC)

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

    # Create a patched ai-config.sh
    patched_config = scripts_dir / "ai-config.sh"
    original_config = (SCRIPTS_DIR / "ai-config.sh").read_text()
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
    for var in ["ANKLUME_CONF", "ANTHROPIC_API_KEY"]:
        env.pop(var, None)

    return env, log_file, project_dir, patched_loop


class TestAiTestLoopMolecule:
    """Mock molecule, test run/fail paths."""

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


class TestAiTestLoopExperiences:
    """Test experience search before LLM call."""

    def test_experiences_dir_missing_does_not_crash(self, ai_test_loop_env):
        """Missing experiences/fixes directory does not crash the script."""
        env, _, cwd, script = ai_test_loop_env
        result = subprocess.run(
            ["bash", str(script), "test_role"],
            capture_output=True, text=True, env=env,
            cwd=str(cwd), timeout=30,
        )
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
    """Test --learn flag triggers experience mining."""

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
        assert result.returncode == 0
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

    (project_dir / "CLAUDE.md").write_text("# anklume\nTest conventions file.\n")
    (project_dir / "docs").mkdir()
    (project_dir / "docs" / "ROADMAP.md").write_text("# ROADMAP\n## Current State\nTest\n---\n")

    mock_python = mock_bin / "python3"
    mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
    mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)

    mock_git = mock_bin / "git"
    mock_git.write_text(f"""#!/usr/bin/env bash
echo "git $@" >> "{log_file}"
exit 0
""")
    mock_git.chmod(mock_git.stat().st_mode | stat.S_IEXEC)

    mock_pytest = mock_bin / "pytest"
    mock_pytest.write_text(f"""#!/usr/bin/env bash
echo "pytest $@" >> "{log_file}"
exit 0
""")
    mock_pytest.chmod(mock_pytest.stat().st_mode | stat.S_IEXEC)

    patched_config = scripts_dir / "ai-config.sh"
    original_config = (SCRIPTS_DIR / "ai-config.sh").read_text()
    patched_config_text = original_config.replace(
        '_ai_conf="${ANKLUME_CONF:-anklume.conf.yml}"',
        f'_ai_conf="{project_dir}/anklume.conf.yml"',
    )
    patched_config.write_text(patched_config_text)

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

    mock_curl = mock_bin / "curl"
    mock_curl.write_text(f"""#!/usr/bin/env bash
echo "curl $@" >> "{log_file}"
echo '{{"response":"no changes needed"}}'
exit 0
""")
    mock_curl.chmod(mock_curl.stat().st_mode | stat.S_IEXEC)

    return env, log_file, project_dir, patched_develop


class TestAiDevelopBehavior:
    """Test ai-develop.sh core behavior."""

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
        assert len(log_files) >= 1


# ── agent scripts graceful failure without Incus ─────────────────


class TestAgentScriptsNoIncus:
    """Test that agent scripts fail gracefully without Incus."""

    @pytest.fixture()
    def mock_incus_env(self):
        """Environment with a mock incus that always fails."""
        mock_bin = Path("/tmp/test_agent_mock")
        mock_bin.mkdir(exist_ok=True)
        mock_incus = mock_bin / "incus"
        mock_incus.write_text("#!/usr/bin/env bash\nexit 1\n")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)
        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        return env

    def test_agent_fix_no_incus(self, mock_incus_env):
        """agent-fix.sh fails gracefully without Incus."""
        result = run_script("agent-fix.sh", [], env=mock_incus_env)
        assert result.returncode != 0
        assert "Cannot connect" in result.stderr or "ERROR" in result.stderr

    def test_agent_develop_no_incus(self, mock_incus_env):
        """agent-develop.sh fails gracefully without Incus."""
        result = run_script("agent-develop.sh", ["Test task"], env=mock_incus_env)
        assert result.returncode != 0
        assert "Cannot connect" in result.stderr or "ERROR" in result.stderr
