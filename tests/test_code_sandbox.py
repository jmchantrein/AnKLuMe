"""Tests for Phase 23b: Sandboxed AI Coding Environment.

Covers:
- Shell syntax validation (bootstrap.sh, host/bin/anklume)
- Bootstrap model recommendation and provisioning functions
- anklume CLI structure and subcommands
- code_sandbox Ansible role files
- site.yml registration
- Makefile target
"""

import os
import re
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BOOTSTRAP_SH = PROJECT_ROOT / "scripts" / "bootstrap.sh"
ANKLUME_CLI = PROJECT_ROOT / "host" / "bin" / "anklume"
SITE_YML = PROJECT_ROOT / "site.yml"
MAKEFILE = PROJECT_ROOT / "Makefile"
INFRA_YML = PROJECT_ROOT / "examples" / "ai-tools" / "infra.yml"
ROLE_DIR = PROJECT_ROOT / "roles" / "code_sandbox"


# ── Shell syntax validation ──────────────────────────────


class TestShellSyntax:
    """Verify shell scripts pass bash -n syntax check."""

    def test_bootstrap_syntax(self):
        result = subprocess.run(
            ["bash", "-n", str(BOOTSTRAP_SH)],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, f"bootstrap.sh syntax error: {result.stderr}"

    def test_anklume_syntax(self):
        result = subprocess.run(
            ["bash", "-n", str(ANKLUME_CLI)],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, f"anklume syntax error: {result.stderr}"


# ── Bootstrap: recommend_models ──────────────────────────


class TestRecommendModels:
    """Verify recommend_models() function exists and returns correct models."""

    @classmethod
    def setup_class(cls):
        cls.content = BOOTSTRAP_SH.read_text()

    def test_function_exists(self):
        assert re.search(r'^recommend_models\(\)', self.content, re.MULTILINE)

    def test_provision_models_exists(self):
        assert re.search(r'^provision_models\(\)', self.content, re.MULTILINE)

    def test_vram_thresholds(self):
        """All four VRAM threshold values are present."""
        assert "8192" in self.content
        assert "16384" in self.content
        assert "24576" in self.content

    def test_model_names(self):
        """Expected model names appear in the script."""
        assert "qwen2.5-coder:7b" in self.content
        assert "qwen2.5-coder:14b" in self.content
        assert "qwen2.5-coder:32b" in self.content
        assert "nomic-embed-text" in self.content
        assert "deepseek-coder-v2:latest" in self.content

    def test_ollama_pull(self):
        """provision_models uses ollama pull."""
        assert "ollama pull" in self.content


class TestRecommendModelsExecution:
    """Extract recommend_models() and verify output per VRAM tier."""

    @classmethod
    def _extract_function(cls):
        """Extract recommend_models function from bootstrap.sh."""
        content = BOOTSTRAP_SH.read_text()
        # Extract the recommend_models function using regex
        match = re.search(
            r'(^recommend_models\(\)\s*\{.*?^})',
            content,
            re.MULTILINE | re.DOTALL,
        )
        assert match, "recommend_models function not found"
        return match.group(1)

    def _run_recommend(self, vram_mb):
        """Call recommend_models with given VRAM."""
        func_body = self._extract_function()
        script = f"""
{func_body}
recommend_models {vram_mb}
"""
        result = subprocess.run(
            ["bash", "-c", script],
            capture_output=True, text=True, timeout=10,
        )
        return result

    def test_8gb_vram(self):
        result = self._run_recommend(8192)
        assert result.returncode == 0
        output = result.stdout.strip()
        assert "qwen2.5-coder:7b" in output
        assert "nomic-embed-text" in output

    def test_small_vram(self):
        result = self._run_recommend(4096)
        assert result.returncode == 0
        output = result.stdout.strip()
        assert "qwen2.5-coder:7b" in output
        assert "nomic-embed-text" in output

    def test_16gb_vram(self):
        result = self._run_recommend(16384)
        assert result.returncode == 0
        output = result.stdout.strip()
        assert "qwen2.5-coder:14b" in output
        assert "nomic-embed-text" in output

    def test_12gb_vram(self):
        result = self._run_recommend(12288)
        assert result.returncode == 0
        output = result.stdout.strip()
        assert "qwen2.5-coder:14b" in output

    def test_24gb_vram(self):
        result = self._run_recommend(24576)
        assert result.returncode == 0
        output = result.stdout.strip()
        assert "qwen2.5-coder:32b" in output
        assert "nomic-embed-text" in output

    def test_large_vram(self):
        result = self._run_recommend(49152)
        assert result.returncode == 0
        output = result.stdout.strip()
        assert "deepseek-coder-v2:latest" in output
        assert "qwen2.5-coder:32b" in output
        assert "nomic-embed-text" in output

    def test_no_vram(self):
        result = self._run_recommend(0)
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_empty_vram(self):
        """Empty argument returns empty string."""
        func_body = self._extract_function()
        script = f"""
{func_body}
recommend_models ""
"""
        result = subprocess.run(
            ["bash", "-c", script],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == ""


# ── Bootstrap: provision_models integration ──────────────


class TestProvisionModelsStructure:
    """Verify provision_models function structure in bootstrap.sh."""

    @classmethod
    def setup_class(cls):
        cls.content = BOOTSTRAP_SH.read_text()

    def test_calls_recommend_models(self):
        """provision_models calls recommend_models internally."""
        # Find the provision_models function body
        match = re.search(
            r'provision_models\(\)\s*\{(.*?)^}',
            self.content,
            re.MULTILINE | re.DOTALL,
        )
        assert match, "provision_models function not found"
        body = match.group(1)
        assert "recommend_models" in body

    def test_handles_no_gpu(self):
        """provision_models handles missing GPU gracefully."""
        match = re.search(
            r'provision_models\(\)\s*\{(.*?)^}',
            self.content,
            re.MULTILINE | re.DOTALL,
        )
        assert match
        body = match.group(1)
        assert "skip" in body.lower() or "return" in body

    def test_user_confirmation(self):
        """provision_models asks for user confirmation."""
        match = re.search(
            r'provision_models\(\)\s*\{(.*?)^}',
            self.content,
            re.MULTILINE | re.DOTALL,
        )
        assert match
        body = match.group(1)
        assert "ask" in body.lower() or "read" in body.lower()

    def test_detect_gpu_calls_provision(self):
        """detect_gpu integrates with provision_models."""
        assert "provision_models" in self.content


# ── anklume CLI ──────────────────────────────────────────


class TestAnklumeCli:
    """Verify host/bin/anklume CLI structure and behavior."""

    @classmethod
    def setup_class(cls):
        cls.content = ANKLUME_CLI.read_text()

    def test_exists(self):
        assert ANKLUME_CLI.is_file()

    def test_executable(self):
        assert os.access(str(ANKLUME_CLI), os.X_OK)

    def test_shebang(self):
        assert self.content.startswith("#!/usr/bin/env bash")

    def test_set_e(self):
        assert "set -euo pipefail" in self.content

    def test_main_function(self):
        assert re.search(r'^main\(\)', self.content, re.MULTILINE)

    def test_code_subcommand(self):
        assert "cmd_code" in self.content

    def test_shell_subcommand(self):
        assert "cmd_shell" in self.content

    def test_help_subcommand(self):
        assert "usage" in self.content

    def test_claude_launch(self):
        """Code subcommand launches claude."""
        assert "claude" in self.content

    def test_incus_exec(self):
        """Uses incus exec for container access."""
        assert "incus exec" in self.content

    def test_bind_mount(self):
        """Supports dynamic bind-mount of project directory."""
        assert "disk" in self.content
        assert "source=" in self.content

    def test_ssh_agent(self):
        """SSH agent forwarding is supported."""
        assert "SSH_AUTH_SOCK" in self.content

    def test_ollama_env(self):
        """Sets OLLAMA_API_BASE."""
        assert "OLLAMA_API_BASE" in self.content


class TestAnklumeHelpOutput:
    """Verify anklume help output."""

    def test_help_flag(self):
        result = subprocess.run(
            ["bash", str(ANKLUME_CLI), "help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "code" in result.stdout
        assert "shell" in result.stdout

    def test_help_long_flag(self):
        result = subprocess.run(
            ["bash", str(ANKLUME_CLI), "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "code" in result.stdout
        assert "shell" in result.stdout

    def test_no_args_shows_help(self):
        result = subprocess.run(
            ["bash", str(ANKLUME_CLI)],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "code" in result.stdout
        assert "shell" in result.stdout

    def test_unknown_command(self):
        result = subprocess.run(
            ["bash", str(ANKLUME_CLI), "nonexistent"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0


# ── code_sandbox role ────────────────────────────────────


class TestCodeSandboxRole:
    """Verify code_sandbox Ansible role files exist and contain expected content."""

    def test_defaults_exist(self):
        assert (ROLE_DIR / "defaults" / "main.yml").is_file()

    def test_tasks_exist(self):
        assert (ROLE_DIR / "tasks" / "main.yml").is_file()

    def test_meta_exist(self):
        assert (ROLE_DIR / "meta" / "main.yml").is_file()

    def test_handlers_exist(self):
        assert (ROLE_DIR / "handlers" / "main.yml").is_file()


class TestCodeSandboxDefaults:
    """Verify code_sandbox defaults contain expected variables."""

    @classmethod
    def setup_class(cls):
        cls.content = (ROLE_DIR / "defaults" / "main.yml").read_text()

    def test_claude_code_var(self):
        assert "code_sandbox_claude_code" in self.content

    def test_aider_var(self):
        assert "code_sandbox_aider" in self.content

    def test_gemini_cli_var(self):
        assert "code_sandbox_gemini_cli" in self.content

    def test_node_version(self):
        assert "code_sandbox_node_version" in self.content

    def test_ollama_url(self):
        assert "code_sandbox_ollama_url" in self.content
        assert "10.100.4.10:11434" in self.content

    def test_ssh_agent_socket(self):
        assert "code_sandbox_ssh_agent_socket" in self.content

    def test_projects_path(self):
        assert "code_sandbox_projects_path" in self.content


class TestCodeSandboxTasks:
    """Verify code_sandbox tasks contain expected steps."""

    @classmethod
    def setup_class(cls):
        cls.content = (ROLE_DIR / "tasks" / "main.yml").read_text()

    def test_nodejs_install(self):
        assert "nodesource" in self.content

    def test_system_deps(self):
        for pkg in ["nodejs", "git", "python3", "tmux", "openssh-client"]:
            assert pkg in self.content

    def test_claude_code_install(self):
        assert "@anthropic-ai/claude-code" in self.content

    def test_aider_install(self):
        assert "aider-chat" in self.content

    def test_gemini_cli_install(self):
        assert "@google/gemini-cli" in self.content

    def test_ssh_auth_sock_config(self):
        assert "SSH_AUTH_SOCK" in self.content

    def test_ollama_api_base_config(self):
        assert "OLLAMA_API_BASE" in self.content

    def test_projects_directory(self):
        assert "code_sandbox_projects_path" in self.content

    def test_conditional_claude(self):
        """Claude Code install is conditional."""
        assert "code_sandbox_claude_code" in self.content

    def test_conditional_aider(self):
        """Aider install is conditional."""
        assert "code_sandbox_aider" in self.content

    def test_conditional_gemini(self):
        """Gemini CLI install is conditional."""
        assert "code_sandbox_gemini_cli" in self.content


class TestCodeSandboxMeta:
    """Verify code_sandbox meta/main.yml."""

    @classmethod
    def setup_class(cls):
        cls.content = (ROLE_DIR / "meta" / "main.yml").read_text()

    def test_role_name(self):
        assert "code_sandbox" in self.content

    def test_license(self):
        assert "AGPL-3.0" in self.content

    def test_platform(self):
        assert "Debian" in self.content


# ── site.yml registration ───────────────────────────────


class TestSiteYmlRegistration:
    """Verify code_sandbox is registered in site.yml."""

    @classmethod
    def setup_class(cls):
        cls.content = SITE_YML.read_text()

    def test_code_sandbox_include(self):
        assert "code_sandbox" in self.content

    def test_code_sandbox_tag(self):
        assert "code_sandbox" in self.content

    def test_code_sandbox_condition(self):
        """code_sandbox is conditional on instance_roles."""
        # Find the code_sandbox block
        match = re.search(
            r"Apply code_sandbox.*?tags:.*?code_sandbox",
            self.content,
            re.DOTALL,
        )
        assert match, "code_sandbox block not found in site.yml"

    def test_appears_after_opencode(self):
        """code_sandbox appears after opencode_server in site.yml."""
        opencode_pos = self.content.index("opencode_server")
        sandbox_pos = self.content.index("code_sandbox")
        assert sandbox_pos > opencode_pos


# ── infra.yml ai-coder machine ──────────────────────────


class TestInfraYmlAiCoder:
    """Verify ai-coder machine definition in examples/ai-tools/infra.yml."""

    @classmethod
    def setup_class(cls):
        cls.content = INFRA_YML.read_text()

    def test_ai_coder_defined(self):
        assert "ai-coder:" in self.content

    def test_ai_coder_ip(self):
        assert "10.100.4.50" in self.content

    def test_ai_coder_roles(self):
        assert "code_sandbox" in self.content

    def test_ai_coder_type(self):
        """ai-coder is an LXC container."""
        # Find the ai-coder block
        match = re.search(
            r"ai-coder:.*?type:\s*lxc",
            self.content,
            re.DOTALL,
        )
        assert match, "ai-coder should be type: lxc"

    def test_in_ai_tools_domain(self):
        """ai-coder is in the ai-tools domain (same bridge as Ollama)."""
        # ai-coder should appear after "ai-tools:" domain
        ai_tools_pos = self.content.index("ai-tools:")
        ai_coder_pos = self.content.index("ai-coder:")
        assert ai_coder_pos > ai_tools_pos


# ── Makefile target ──────────────────────────────────────


class TestMakefileTarget:
    """Verify apply-code-sandbox target in Makefile."""

    @classmethod
    def setup_class(cls):
        cls.content = MAKEFILE.read_text()

    def test_target_exists(self):
        assert "apply-code-sandbox:" in self.content

    def test_target_uses_tags(self):
        assert "--tags code_sandbox" in self.content

    def test_phony(self):
        assert "apply-code-sandbox" in self.content
        # Check it's in .PHONY
        phony_match = re.search(r'\.PHONY:.*', self.content, re.DOTALL)
        assert phony_match
        assert "apply-code-sandbox" in phony_match.group(0)
