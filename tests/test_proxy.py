"""Tests for MCP proxy archive and OpenClaw infrastructure (Phase 35).

The MCP proxy (scripts/mcp-anklume-dev.py) was archived in Phase 35.
This file verifies:
- Archive structure is intact
- OpenClaw documentation completeness (still active)
- Agent reproducibility templates (ADR-036, still active)
"""

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_DIR = PROJECT_ROOT / "scripts" / "archive"
ARCHIVED_PROXY = ARCHIVE_DIR / "mcp-anklume-dev.py"
ARCHIVED_SERVICE = ARCHIVE_DIR / "mcp-anklume-dev.service"
ARCHIVED_CREDS = ARCHIVE_DIR / "sync-claude-credentials.sh"
OPENCLAW_DOC_EN = PROJECT_ROOT / "docs" / "openclaw.md"
OPENCLAW_DOC_FR = PROJECT_ROOT / "docs" / "openclaw.fr.md"
OPENCLAW_ROLE = PROJECT_ROOT / "roles" / "openclaw_server"
OPENCLAW_TEMPLATES = OPENCLAW_ROLE / "templates"
OPENCLAW_DEFAULTS = OPENCLAW_ROLE / "defaults" / "main.yml"
OPENCLAW_TASKS = OPENCLAW_ROLE / "tasks" / "main.yml"


# -- Archive structure (Phase 35) ------------------------------------------


class TestProxyArchive:
    """Verify Phase 35 archive structure."""

    def test_archive_directory_exists(self):
        assert ARCHIVE_DIR.is_dir(), "scripts/archive/ directory missing"

    def test_archive_readme_exists(self):
        readme = ARCHIVE_DIR / "README.md"
        assert readme.exists(), "scripts/archive/README.md missing"

    def test_archived_proxy_exists(self):
        assert ARCHIVED_PROXY.exists(), "Archived proxy script missing"

    def test_archived_service_exists(self):
        assert ARCHIVED_SERVICE.exists(), "Archived systemd service missing"

    def test_archived_creds_script_exists(self):
        assert ARCHIVED_CREDS.exists(), "Archived credential sync script missing"

    def test_proxy_not_in_active_scripts(self):
        """Proxy must NOT exist in active scripts/ directory."""
        active = PROJECT_ROOT / "scripts" / "mcp-anklume-dev.py"
        assert not active.exists(), \
            "mcp-anklume-dev.py should be archived, not in scripts/"

    def test_service_not_in_active_scripts(self):
        """Service file must NOT exist in active scripts/ directory."""
        active = PROJECT_ROOT / "scripts" / "mcp-anklume-dev.service"
        assert not active.exists(), \
            "mcp-anklume-dev.service should be archived, not in scripts/"

    def test_creds_not_in_host_boot(self):
        """Credential sync script must NOT exist in host/boot/."""
        active = PROJECT_ROOT / "host" / "boot" / "sync-claude-credentials.sh"
        assert not active.exists(), \
            "sync-claude-credentials.sh should be archived, not in host/boot/"


# -- Documentation (OpenClaw) ----------------------------------------------


class TestOpenClawDocumentation:
    """Verify OpenClaw documentation completeness."""

    @classmethod
    def setup_class(cls):
        if not OPENCLAW_DOC_EN.exists() or not OPENCLAW_DOC_FR.exists():
            pytest.skip("OpenClaw docs not present")
        cls.en = OPENCLAW_DOC_EN.read_text()
        cls.fr = OPENCLAW_DOC_FR.read_text()

    def test_en_value_add_section_exists(self):
        assert "Value-add over native OpenClaw" in self.en

    def test_fr_value_add_section_exists(self):
        assert "Valeur ajoutee par rapport a OpenClaw natif" in self.fr

    def test_en_10_value_adds_documented(self):
        """All 10 value-adds are documented in English."""
        for i in range(1, 11):
            assert f"### {i}." in self.en, f"Value-add #{i} missing in EN doc"

    def test_fr_10_value_adds_documented(self):
        """All 10 value-adds are documented in French."""
        for i in range(1, 11):
            assert f"### {i}." in self.fr, f"Value-add #{i} missing in FR doc"

    def test_en_summary_table(self):
        assert "| Capability |" in self.en

    def test_fr_summary_table(self):
        assert "| Capacite |" in self.fr

    def test_en_agents_md_structure(self):
        """AGENTS.md mode markers are documented in English."""
        assert "[ALL MODES]" in self.en
        assert "[ANKLUME MODE]" in self.en

    def test_fr_agents_md_structure(self):
        """AGENTS.md mode markers are documented in French."""
        assert "[ALL MODES]" in self.fr
        assert "[ANKLUME MODE]" in self.fr


# -- Agent reproducibility (ADR-036) ---------------------------------------


class TestOpenClawTemplates:
    """Verify ADR-036: agent operational knowledge is framework-reproducible."""

    @classmethod
    def setup_class(cls):
        if not OPENCLAW_TEMPLATES.exists():
            pytest.skip("OpenClaw role templates not present")

    def test_all_templates_exist(self):
        """All 5 workspace templates exist in the role."""
        expected = [
            "AGENTS.md.j2", "TOOLS.md.j2", "USER.md.j2",
            "IDENTITY.md.j2", "MEMORY.md.j2",
        ]
        for template in expected:
            path = OPENCLAW_TEMPLATES / template
            assert path.exists(), f"Template missing: {template}"

    def test_agents_md_has_mode_markers(self):
        """AGENTS.md.j2 contains all mode markers."""
        content = (OPENCLAW_TEMPLATES / "AGENTS.md.j2").read_text()
        for marker in ["[ALL MODES]", "[ANKLUME MODE]",
                        "[ASSISTANT MODE]", "[LOCAL MODE]"]:
            assert marker in content, f"Missing mode marker: {marker}"

    def test_agents_md_has_critical_rule(self):
        """AGENTS.md.j2 contains the non-modification rule."""
        content = (OPENCLAW_TEMPLATES / "AGENTS.md.j2").read_text()
        assert "MUST NOT modify your operational files directly" in content

    def test_agents_md_has_soul_exception(self):
        """AGENTS.md.j2 documents the SOUL.md exception."""
        content = (OPENCLAW_TEMPLATES / "AGENTS.md.j2").read_text()
        assert "SOUL.md" in content
        assert "NEVER committed to git" in content

    def test_agents_md_has_git_credentials_doc(self):
        """AGENTS.md.j2 documents git credential mechanism."""
        content = (OPENCLAW_TEMPLATES / "AGENTS.md.j2").read_text()
        assert "git-credentials" in content

    def test_tools_md_has_api_reference(self):
        """TOOLS.md.j2 contains API tool reference."""
        content = (OPENCLAW_TEMPLATES / "TOOLS.md.j2").read_text()
        assert "git_status" in content
        assert "incus_exec" in content
        assert "web_search" in content

    def test_templates_use_jinja_variables(self):
        """Templates reference Jinja2 variables (not hardcoded IPs)."""
        for template in ["AGENTS.md.j2", "TOOLS.md.j2"]:
            content = (OPENCLAW_TEMPLATES / template).read_text()
            assert "openclaw_server_proxy_ip" in content, \
                f"{template} missing proxy_ip variable"

    def test_defaults_has_all_variables(self):
        """defaults/main.yml declares all template variables."""
        content = OPENCLAW_DEFAULTS.read_text()
        expected_vars = [
            "openclaw_server_proxy_ip",
            "openclaw_server_proxy_port",
            "openclaw_server_openclaw_ip",
            "openclaw_server_ollama_ip",
            "openclaw_server_ollama_port",
            "openclaw_server_agent_name",
            "openclaw_server_agent_emoji",
            "openclaw_server_user_name",
            "openclaw_server_user_timezone",
            "openclaw_server_user_languages",
        ]
        for var in expected_vars:
            assert var in content, f"Missing default variable: {var}"

    def test_tasks_deploy_agents_md(self):
        """tasks/main.yml deploys AGENTS.md from template."""
        content = OPENCLAW_TASKS.read_text()
        assert "AGENTS.md.j2" in content

    def test_tasks_deploy_operational_files(self):
        """tasks/main.yml deploys TOOLS.md, USER.md, IDENTITY.md."""
        content = OPENCLAW_TASKS.read_text()
        for template in ["TOOLS.md.j2", "USER.md.j2", "IDENTITY.md.j2"]:
            assert template in content, f"Task missing for {template}"

    def test_tasks_seed_memory_with_force_false(self):
        """tasks/main.yml seeds MEMORY.md with force: false."""
        content = OPENCLAW_TASKS.read_text()
        assert "MEMORY.md.j2" in content
        assert "force: false" in content

    def test_gitignore_has_soul_md(self):
        """SOUL.md is globally gitignored."""
        gitignore = (PROJECT_ROOT / ".gitignore").read_text()
        assert "SOUL.md" in gitignore

    def test_architecture_has_adr_036(self):
        """ADR-036 is documented in ARCHITECTURE.md."""
        arch = (PROJECT_ROOT / "docs" / "ARCHITECTURE.md").read_text()
        assert "ADR-036" in arch
        assert "framework-reproducible" in arch
