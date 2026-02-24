"""Tests for service Jinja2 template edge cases.

Covers boundary conditions and advanced rendering for service templates:
- Speaches (stt_server role)
- LobeChat (lobechat role)
- OpenCode (opencode_server role)
- Claude settings (dev_agent_runner role)
"""

import json
import re
from pathlib import Path

import pytest

try:
    from jinja2 import Environment, FileSystemLoader
except ImportError:
    pytest.skip("jinja2 not installed", allow_module_level=True)

ROLES_DIR = Path(__file__).resolve().parent.parent / "roles"


def _ansible_env(tmpl_dir):
    """Create a Jinja2 Environment with Ansible-compatible filters."""
    env = Environment(loader=FileSystemLoader(str(tmpl_dir)))
    env.filters["regex_replace"] = lambda value, pattern, replacement: re.sub(
        pattern, replacement, value,
    )
    return env


# ── speaches service template edge cases ────────────────────


class TestSpeachesEdgeCases:
    def _render(self, **kwargs):
        tmpl_dir = ROLES_DIR / "stt_server" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("speaches.service.j2")
        return template.render(ansible_managed="Ansible managed", **kwargs)

    def test_with_language_set(self):
        """Speaches template includes language when set."""
        result = self._render(
            stt_server_host="0.0.0.0",
            stt_server_port=8000,
            stt_server_model="large-v3-turbo",
            stt_server_quantization="float16",
            stt_server_language="fr",
        )
        assert "WHISPER__LANGUAGE=fr" in result

    def test_without_language(self):
        """Speaches template omits language when empty."""
        result = self._render(
            stt_server_host="0.0.0.0",
            stt_server_port=8000,
            stt_server_model="large-v3-turbo",
            stt_server_quantization="float16",
            stt_server_language="",
        )
        assert "WHISPER__LANGUAGE" not in result
        assert "WHISPER__MODEL=large-v3-turbo" in result

    def test_int8_quantization(self):
        """Speaches template renders int8 quantization."""
        result = self._render(
            stt_server_host="0.0.0.0",
            stt_server_port=9000,
            stt_server_model="medium",
            stt_server_quantization="int8",
            stt_server_language="",
        )
        assert "WHISPER__COMPUTE_TYPE=int8" in result
        assert "WHISPER__MODEL=medium" in result

    def test_custom_host_and_port(self):
        """Speaches template uses custom host and port."""
        result = self._render(
            stt_server_host="127.0.0.1",
            stt_server_port=9999,
            stt_server_model="small",
            stt_server_quantization="float16",
            stt_server_language="",
        )
        assert "--host 127.0.0.1" in result
        assert "--port 9999" in result

    def test_systemd_restart_policy(self):
        """Speaches service has restart always policy."""
        result = self._render(
            stt_server_host="0.0.0.0",
            stt_server_port=8000,
            stt_server_model="large-v3-turbo",
            stt_server_quantization="float16",
            stt_server_language="",
        )
        assert "Restart=always" in result
        assert "RestartSec=5" in result


# ── lobechat service template edge cases ────────────────────


class TestLobechatEdgeCases:
    def _render(self, **kwargs):
        tmpl_dir = ROLES_DIR / "lobechat" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("lobechat.service.j2")
        return template.render(**kwargs)

    def test_custom_port(self):
        """LobeChat template uses custom port."""
        result = self._render(
            lobechat_port=4000,
            lobechat_ollama_url="http://localhost:11434",
        )
        assert '"PORT=4000"' in result or "PORT=4000" in result

    def test_remote_ollama_url(self):
        """LobeChat template connects to remote Ollama."""
        result = self._render(
            lobechat_port=3210,
            lobechat_ollama_url="http://10.100.3.10:11434",
        )
        assert "10.100.3.10:11434" in result

    def test_has_enabled_ollama(self):
        """LobeChat template enables Ollama integration."""
        result = self._render(
            lobechat_port=3210,
            lobechat_ollama_url="http://gpu-server:11434",
        )
        assert "ENABLED_OLLAMA=1" in result

    def test_working_directory(self):
        """LobeChat service runs from /opt/lobechat."""
        result = self._render(
            lobechat_port=3210,
            lobechat_ollama_url="http://gpu-server:11434",
        )
        assert "WorkingDirectory=/opt/lobechat" in result

    def test_hostname_binds_all(self):
        """LobeChat listens on all interfaces."""
        result = self._render(
            lobechat_port=3210,
            lobechat_ollama_url="http://gpu-server:11434",
        )
        assert "HOSTNAME=0.0.0.0" in result


# ── opencode templates edge cases ───────────────────────────


class TestOpencodeEdgeCases:
    def test_service_custom_host(self):
        """OpenCode service uses custom host binding."""
        tmpl_dir = ROLES_DIR / "opencode_server" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("opencode.service.j2")
        result = template.render(
            opencode_server_port=5000,
            opencode_server_host="127.0.0.1",
            opencode_server_password="mypass",
        )
        assert "--hostname 127.0.0.1" in result
        assert "--port 5000" in result
        assert "OPENCODE_SERVER_PASSWORD=mypass" in result

    def test_config_custom_model(self):
        """OpenCode config renders with custom model name."""
        tmpl_dir = ROLES_DIR / "opencode_server" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("opencode-config.json.j2")
        result = template.render(
            opencode_server_ollama_url="http://localhost:11434/v1",
            opencode_server_model="codellama:70b",
        )
        data = json.loads(result)
        assert "codellama:70b" in data["provider"]["ollama"]["models"]
        model_entry = data["provider"]["ollama"]["models"]["codellama:70b"]
        assert model_entry["name"] == "codellama:70b"

    def test_config_valid_json(self):
        """OpenCode config renders valid JSON with various inputs."""
        tmpl_dir = ROLES_DIR / "opencode_server" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("opencode-config.json.j2")
        result = template.render(
            opencode_server_ollama_url="http://10.0.0.1:11434/v1",
            opencode_server_model="deepseek-coder:6.7b",
        )
        data = json.loads(result)
        assert data["$schema"] == "https://opencode.ai/config.json"
        assert data["provider"]["ollama"]["npm"] == "@ai-sdk/openai-compatible"


# ── claude-settings template edge cases ─────────────────────


class TestClaudeSettingsEdgeCases:
    def _render(self, **kwargs):
        tmpl_dir = ROLES_DIR / "dev_agent_runner" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("claude-settings.json.j2")
        return template.render(**kwargs)

    def test_deny_list_present(self):
        """Claude settings include deny list for dangerous commands."""
        result = self._render(
            dev_agent_runner_enable_teams=True,
            dev_agent_runner_permissions_mode="bypassPermissions",
        )
        data = json.loads(result)
        deny = data["permissions"]["deny"]
        assert "Bash(rm -rf /)" in deny
        assert "Bash(curl * | bash)" in deny
        assert "Bash(wget * | bash)" in deny

    def test_all_expected_permissions(self):
        """Claude settings include all expected tool permissions."""
        result = self._render(
            dev_agent_runner_enable_teams=True,
            dev_agent_runner_permissions_mode="bypassPermissions",
        )
        data = json.loads(result)
        allow = data["permissions"]["allow"]
        expected = [
            "Edit", "MultiEdit", "Write", "Read", "Glob", "Grep",
            "Bash(molecule *)", "Bash(ansible-lint *)", "Bash(yamllint *)",
            "Bash(ruff *)", "Bash(git *)", "Bash(incus *)",
            "Bash(make *)", "Bash(python3 *)", "Bash(pytest *)",
        ]
        for perm in expected:
            assert perm in allow, f"Missing permission: {perm}"

    def test_different_permission_modes(self):
        """Claude settings render different permission modes."""
        for mode in ["bypassPermissions", "default", "plan"]:
            result = self._render(
                dev_agent_runner_enable_teams=True,
                dev_agent_runner_permissions_mode=mode,
            )
            data = json.loads(result)
            assert data["defaultMode"] == mode


# ── Speaches: model/quantization combinations ────────────────


class TestSpeachesModelCombinations:
    """Test Speaches template with various model/quantization combos."""

    def _render(self, **kwargs):
        tmpl_dir = ROLES_DIR / "stt_server" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("speaches.service.j2")
        return template.render(ansible_managed="Ansible managed", **kwargs)

    def test_tiny_model_with_int8(self):
        """Tiny model with int8 quantization renders correctly."""
        result = self._render(
            stt_server_host="0.0.0.0",
            stt_server_port=8000,
            stt_server_model="tiny",
            stt_server_quantization="int8",
            stt_server_language="",
        )
        assert "WHISPER__MODEL=tiny" in result
        assert "WHISPER__COMPUTE_TYPE=int8" in result

    def test_large_v3_with_float16(self):
        """large-v3 model with float16 quantization renders correctly."""
        result = self._render(
            stt_server_host="0.0.0.0",
            stt_server_port=8000,
            stt_server_model="large-v3",
            stt_server_quantization="float16",
            stt_server_language="",
        )
        assert "WHISPER__MODEL=large-v3" in result
        assert "WHISPER__COMPUTE_TYPE=float16" in result

    def test_int8_float16_quantization(self):
        """int8_float16 quantization renders correctly."""
        result = self._render(
            stt_server_host="0.0.0.0",
            stt_server_port=8000,
            stt_server_model="medium",
            stt_server_quantization="int8_float16",
            stt_server_language="",
        )
        assert "WHISPER__COMPUTE_TYPE=int8_float16" in result

    def test_english_language(self):
        """English language code renders correctly."""
        result = self._render(
            stt_server_host="0.0.0.0",
            stt_server_port=8000,
            stt_server_model="small",
            stt_server_quantization="float16",
            stt_server_language="en",
        )
        assert "WHISPER__LANGUAGE=en" in result

    def test_japanese_language(self):
        """Japanese language code renders correctly."""
        result = self._render(
            stt_server_host="0.0.0.0",
            stt_server_port=8000,
            stt_server_model="large-v3-turbo",
            stt_server_quantization="float16",
            stt_server_language="ja",
        )
        assert "WHISPER__LANGUAGE=ja" in result

    def test_custom_port_in_exec_start(self):
        """Custom port appears in ExecStart line."""
        result = self._render(
            stt_server_host="0.0.0.0",
            stt_server_port=12345,
            stt_server_model="small",
            stt_server_quantization="float16",
            stt_server_language="",
        )
        assert "--port 12345" in result

    def test_systemd_unit_structure(self):
        """Speaches service has correct systemd structure."""
        result = self._render(
            stt_server_host="0.0.0.0",
            stt_server_port=8000,
            stt_server_model="large-v3-turbo",
            stt_server_quantization="float16",
            stt_server_language="",
        )
        assert "[Unit]" in result
        assert "[Service]" in result
        assert "[Install]" in result
        assert "WantedBy=multi-user.target" in result

    def test_managed_header_present(self):
        """Speaches template includes ansible_managed comment."""
        result = self._render(
            stt_server_host="0.0.0.0",
            stt_server_port=8000,
            stt_server_model="large-v3-turbo",
            stt_server_quantization="float16",
            stt_server_language="",
        )
        assert "Ansible managed" in result


# ── LobeChat additional edge cases ───────────────────────────


class TestLobechatAdditionalEdgeCases:
    """Additional edge case tests for LobeChat template."""

    def _render(self, **kwargs):
        tmpl_dir = ROLES_DIR / "lobechat" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("lobechat.service.j2")
        return template.render(**kwargs)

    def test_large_port_number(self):
        """LobeChat renders with a high port number."""
        result = self._render(
            lobechat_port=65535,
            lobechat_ollama_url="http://localhost:11434",
        )
        assert "PORT=65535" in result

    def test_port_one(self):
        """LobeChat renders with port 1."""
        result = self._render(
            lobechat_port=1,
            lobechat_ollama_url="http://localhost:11434",
        )
        assert "PORT=1" in result

    def test_ip_based_ollama_url(self):
        """LobeChat renders with an IP-based Ollama URL."""
        result = self._render(
            lobechat_port=3210,
            lobechat_ollama_url="http://192.168.1.100:11434",
        )
        assert "192.168.1.100:11434" in result

    def test_systemd_structure(self):
        """LobeChat template has correct systemd unit structure."""
        result = self._render(
            lobechat_port=3210,
            lobechat_ollama_url="http://localhost:11434",
        )
        assert "[Unit]" in result
        assert "[Service]" in result
        assert "[Install]" in result
        assert "WantedBy=multi-user.target" in result

    def test_restart_policy(self):
        """LobeChat has restart=always policy."""
        result = self._render(
            lobechat_port=3210,
            lobechat_ollama_url="http://localhost:11434",
        )
        assert "Restart=always" in result
        assert "RestartSec=5" in result

    def test_node_server_exec(self):
        """LobeChat uses node to run the server."""
        result = self._render(
            lobechat_port=3210,
            lobechat_ollama_url="http://localhost:11434",
        )
        assert "node .next/standalone/server.js" in result


# ── OpenCode additional edge cases ───────────────────────────


class TestOpencodeAdditionalEdgeCases:
    """Additional edge case tests for OpenCode templates."""

    def test_service_all_interfaces(self):
        """OpenCode service with 0.0.0.0 binding."""
        tmpl_dir = ROLES_DIR / "opencode_server" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("opencode.service.j2")
        result = template.render(
            opencode_server_port=8080,
            opencode_server_host="0.0.0.0",
            opencode_server_password="secret",
        )
        assert "--hostname 0.0.0.0" in result
        assert "--port 8080" in result

    def test_config_with_special_model_name(self):
        """OpenCode config with model name containing special chars."""
        tmpl_dir = ROLES_DIR / "opencode_server" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("opencode-config.json.j2")
        result = template.render(
            opencode_server_ollama_url="http://localhost:11434/v1",
            opencode_server_model="qwen2.5-coder:32b-instruct-q4_K_M",
        )
        data = json.loads(result)
        assert "qwen2.5-coder:32b-instruct-q4_K_M" in data["provider"]["ollama"]["models"]

    def test_config_with_different_url(self):
        """OpenCode config with non-localhost URL."""
        tmpl_dir = ROLES_DIR / "opencode_server" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("opencode-config.json.j2")
        result = template.render(
            opencode_server_ollama_url="http://10.100.10.10:11434/v1",
            opencode_server_model="codellama:7b",
        )
        data = json.loads(result)
        assert data["provider"]["ollama"]["options"]["baseURL"] == "http://10.100.10.10:11434/v1"

    def test_service_systemd_structure(self):
        """OpenCode service has correct systemd structure."""
        tmpl_dir = ROLES_DIR / "opencode_server" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("opencode.service.j2")
        result = template.render(
            opencode_server_port=5000,
            opencode_server_host="127.0.0.1",
            opencode_server_password="pass",
        )
        assert "[Unit]" in result
        assert "[Service]" in result
        assert "[Install]" in result
        assert "Restart=always" in result


# ── Claude settings additional edge cases ────────────────────


class TestClaudeSettingsAdditionalEdgeCases:
    """Additional edge case tests for Claude settings template."""

    def _render(self, **kwargs):
        tmpl_dir = ROLES_DIR / "dev_agent_runner" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("claude-settings.json.j2")
        return template.render(**kwargs)

    def test_teams_disabled(self):
        """Teams flag not present when disabled."""
        result = self._render(
            dev_agent_runner_enable_teams=False,
            dev_agent_runner_permissions_mode="default",
        )
        data = json.loads(result)
        assert "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS" not in data.get("env", {})

    def test_teams_enabled(self):
        """Teams flag is '1' when enabled."""
        result = self._render(
            dev_agent_runner_enable_teams=True,
            dev_agent_runner_permissions_mode="default",
        )
        data = json.loads(result)
        assert data["env"]["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] == "1"

    def test_valid_json_output(self):
        """Output is always valid JSON regardless of mode."""
        for mode in ["bypassPermissions", "default", "plan"]:
            for teams in [True, False]:
                result = self._render(
                    dev_agent_runner_enable_teams=teams,
                    dev_agent_runner_permissions_mode=mode,
                )
                data = json.loads(result)
                assert isinstance(data, dict)

    def test_plan_mode(self):
        """Plan mode renders correctly."""
        result = self._render(
            dev_agent_runner_enable_teams=True,
            dev_agent_runner_permissions_mode="plan",
        )
        data = json.loads(result)
        assert data["defaultMode"] == "plan"

    def test_permissions_structure(self):
        """Permissions has both allow and deny lists."""
        result = self._render(
            dev_agent_runner_enable_teams=True,
            dev_agent_runner_permissions_mode="bypassPermissions",
        )
        data = json.loads(result)
        assert "allow" in data["permissions"]
        assert "deny" in data["permissions"]
        assert isinstance(data["permissions"]["allow"], list)
        assert isinstance(data["permissions"]["deny"], list)

    def test_no_dangerous_bash_commands(self):
        """Deny list contains dangerous bash patterns."""
        result = self._render(
            dev_agent_runner_enable_teams=True,
            dev_agent_runner_permissions_mode="bypassPermissions",
        )
        data = json.loads(result)
        deny = data["permissions"]["deny"]
        # Check all three dangerous patterns
        assert len(deny) == 3
        assert any("rm -rf" in d for d in deny)
        assert any("curl" in d for d in deny)
        assert any("wget" in d for d in deny)

    def test_essential_tools_in_allow(self):
        """Essential tools (Edit, Read, Write) are in the allow list."""
        result = self._render(
            dev_agent_runner_enable_teams=True,
            dev_agent_runner_permissions_mode="default",
        )
        data = json.loads(result)
        allow = data["permissions"]["allow"]
        for tool in ["Edit", "MultiEdit", "Write", "Read", "Glob", "Grep"]:
            assert tool in allow
