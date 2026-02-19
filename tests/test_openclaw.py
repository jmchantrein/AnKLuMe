"""Tests for Phase 28b: OpenClaw Integration (Self-Hosted AI Assistant).

Covers:
- openclaw_server Ansible role files
- Default variables
- Task definitions
- Meta information
- Template content
- site.yml registration
- infra.yml machine definition
- Makefile target
"""

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SITE_YML = PROJECT_ROOT / "site.yml"
MAKEFILE = PROJECT_ROOT / "Makefile"
INFRA_YML = PROJECT_ROOT / "examples" / "ai-tools" / "infra.yml"
ROLE_DIR = PROJECT_ROOT / "roles" / "openclaw_server"


# -- openclaw_server role files ----------------------------------------


class TestOpenclawRole:
    """Verify openclaw_server Ansible role files exist."""

    def test_defaults_exist(self):
        assert (ROLE_DIR / "defaults" / "main.yml").is_file()

    def test_tasks_exist(self):
        assert (ROLE_DIR / "tasks" / "main.yml").is_file()

    def test_meta_exist(self):
        assert (ROLE_DIR / "meta" / "main.yml").is_file()

    def test_handlers_exist(self):
        assert (ROLE_DIR / "handlers" / "main.yml").is_file()

    def test_service_template_exists(self):
        assert (ROLE_DIR / "templates" / "openclaw.service.j2").is_file()

    def test_config_template_exists(self):
        assert (ROLE_DIR / "templates" / "openclaw-config.json.j2").is_file()


# -- openclaw_server defaults -----------------------------------------


class TestOpenclawDefaults:
    """Verify openclaw_server defaults contain expected variables."""

    @classmethod
    def setup_class(cls):
        cls.content = (ROLE_DIR / "defaults" / "main.yml").read_text()

    def test_port_var(self):
        assert "openclaw_server_port" in self.content

    def test_llm_provider_var(self):
        assert "openclaw_server_llm_provider" in self.content

    def test_ollama_url_var(self):
        assert "openclaw_server_ollama_url" in self.content

    def test_model_var(self):
        assert "openclaw_server_model" in self.content

    def test_channels_var(self):
        assert "openclaw_server_channels" in self.content

    def test_enabled_var(self):
        assert "openclaw_server_enabled" in self.content

    def test_ollama_ip(self):
        assert "10.100.4.10:11434" in self.content


# -- openclaw_server tasks --------------------------------------------


class TestOpenclawTasks:
    """Verify openclaw_server tasks contain expected steps."""

    @classmethod
    def setup_class(cls):
        cls.content = (ROLE_DIR / "tasks" / "main.yml").read_text()

    def test_nodejs_install(self):
        assert "nodesource" in self.content

    def test_system_deps_nodejs(self):
        assert "nodejs" in self.content

    def test_system_deps_git(self):
        assert "git" in self.content

    def test_openclaw_install(self):
        assert "npm install -g openclaw" in self.content

    def test_config_directory(self):
        assert "/root/.config/openclaw" in self.content

    def test_config_template(self):
        assert "openclaw-config.json.j2" in self.content

    def test_service_template(self):
        assert "openclaw.service.j2" in self.content

    def test_systemd_enable(self):
        assert "openclaw_server_enabled" in self.content

    def test_systemd_started(self):
        assert "started" in self.content

    def test_daemon_reload(self):
        assert "daemon_reload" in self.content


# -- openclaw_server meta ----------------------------------------------


class TestOpenclawMeta:
    """Verify openclaw_server meta/main.yml."""

    @classmethod
    def setup_class(cls):
        cls.content = (ROLE_DIR / "meta" / "main.yml").read_text()

    def test_role_name(self):
        assert "openclaw_server" in self.content

    def test_license(self):
        assert "AGPL-3.0" in self.content

    def test_platform(self):
        assert "Debian" in self.content


# -- openclaw_server templates -----------------------------------------


class TestOpenclawTemplates:
    """Verify openclaw_server template content."""

    @classmethod
    def setup_class(cls):
        cls.service = (ROLE_DIR / "templates" / "openclaw.service.j2").read_text()
        cls.config = (ROLE_DIR / "templates" / "openclaw-config.json.j2").read_text()

    def test_service_description(self):
        assert "Description" in self.service

    def test_service_execstart(self):
        assert "ExecStart" in self.service

    def test_service_wantedby(self):
        assert "WantedBy" in self.service

    def test_service_port_variable(self):
        assert "openclaw_server_port" in self.service

    def test_config_provider(self):
        assert "provider" in self.config

    def test_config_ollama(self):
        assert "ollama" in self.config

    def test_config_port(self):
        assert "port" in self.config

    def test_config_channels(self):
        assert "channels" in self.config

    def test_config_model(self):
        assert "openclaw_server_model" in self.config

    def test_service_llm_provider_env(self):
        assert "OPENCLAW_LLM_PROVIDER" in self.service

    def test_service_ollama_url_env(self):
        assert "OPENCLAW_OLLAMA_URL" in self.service


# -- site.yml registration --------------------------------------------


class TestSiteYmlRegistration:
    """Verify openclaw_server is registered in site.yml."""

    @classmethod
    def setup_class(cls):
        cls.content = SITE_YML.read_text()

    def test_openclaw_include(self):
        assert "openclaw_server" in self.content

    def test_openclaw_tag(self):
        """openclaw tag exists in site.yml."""
        assert "openclaw" in self.content

    def test_openclaw_condition(self):
        """openclaw_server is conditional on instance_roles."""
        match = re.search(
            r"Apply openclaw_server.*?tags:.*?openclaw",
            self.content,
            re.DOTALL,
        )
        assert match, "openclaw_server block not found in site.yml"

    def test_appears_after_code_sandbox(self):
        """openclaw_server appears after code_sandbox in site.yml."""
        sandbox_pos = self.content.index("code_sandbox")
        openclaw_pos = self.content.index("openclaw_server")
        assert openclaw_pos > sandbox_pos


# -- infra.yml ai-openclaw machine ------------------------------------


class TestInfraYmlOpenClaw:
    """Verify ai-openclaw machine definition in examples/ai-tools/infra.yml."""

    @classmethod
    def setup_class(cls):
        cls.content = INFRA_YML.read_text()

    def test_ai_openclaw_defined(self):
        assert "ai-openclaw:" in self.content

    def test_ai_openclaw_ip(self):
        assert "10.100.4.60" in self.content

    def test_ai_openclaw_roles(self):
        assert "openclaw_server" in self.content

    def test_ai_openclaw_type(self):
        """ai-openclaw is an LXC container."""
        match = re.search(
            r"ai-openclaw:.*?type:\s*lxc",
            self.content,
            re.DOTALL,
        )
        assert match, "ai-openclaw should be type: lxc"

    def test_in_ai_tools_domain(self):
        """ai-openclaw is in the ai-tools domain."""
        ai_tools_pos = self.content.index("ai-tools:")
        ai_openclaw_pos = self.content.index("ai-openclaw:")
        assert ai_openclaw_pos > ai_tools_pos


# -- Makefile target ---------------------------------------------------


class TestMakefileTarget:
    """Verify apply-openclaw target in Makefile."""

    @classmethod
    def setup_class(cls):
        cls.content = MAKEFILE.read_text()

    def test_target_exists(self):
        assert "apply-openclaw:" in self.content

    def test_target_uses_tags(self):
        assert "--tags openclaw" in self.content

    def test_phony(self):
        """apply-openclaw is in .PHONY."""
        phony_match = re.search(r'\.PHONY:.*', self.content, re.DOTALL)
        assert phony_match
        assert "apply-openclaw" in phony_match.group(0)
