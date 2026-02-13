"""Tests for Ansible role structure, defaults, and templates.

Validates that all roles follow AnKLuMe conventions:
- Required files exist (tasks/main.yml, defaults/main.yml, meta/main.yml)
- Defaults are valid YAML with expected types
- Templates render correctly with sample data
- Task names follow the RoleName | Description convention
"""

import re
from pathlib import Path

import pytest
import yaml

try:
    from jinja2 import Environment, FileSystemLoader
except ImportError:
    pytest.skip("jinja2 not installed", allow_module_level=True)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ROLES_DIR = PROJECT_ROOT / "roles"

# All roles in the project
ALL_ROLES = sorted([d.name for d in ROLES_DIR.iterdir() if d.is_dir() and (d / "tasks").exists()])


# ── Role structure ──────────────────────────────────────────


class TestRoleStructure:
    """Verify all roles have required files and structure."""

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_tasks_main_exists(self, role):
        """Every role has tasks/main.yml."""
        assert (ROLES_DIR / role / "tasks" / "main.yml").exists()

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_meta_main_exists(self, role):
        """Every role has meta/main.yml."""
        assert (ROLES_DIR / role / "meta" / "main.yml").exists()

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_molecule_directory_exists(self, role):
        """Every role has a molecule/ directory."""
        assert (ROLES_DIR / role / "molecule").exists()

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_molecule_verify_exists(self, role):
        """Every role has a molecule verify.yml."""
        assert (ROLES_DIR / role / "molecule" / "default" / "verify.yml").exists()


# ── Defaults validation ─────────────────────────────────────


class TestRoleDefaults:
    """Verify role defaults are valid YAML."""

    def _get_roles_with_defaults(self):
        return [r for r in ALL_ROLES if (ROLES_DIR / r / "defaults" / "main.yml").exists()]

    @pytest.mark.parametrize("role", [r for r in ALL_ROLES if (ROLES_DIR / r / "defaults" / "main.yml").exists()])
    def test_defaults_valid_yaml(self, role):
        """Role defaults are valid YAML."""
        defaults_file = ROLES_DIR / role / "defaults" / "main.yml"
        with open(defaults_file) as f:
            data = yaml.safe_load(f)
        assert data is None or isinstance(data, dict), \
            f"Defaults for {role} should be a dict or empty"

    @pytest.mark.parametrize("role", [r for r in ALL_ROLES if (ROLES_DIR / r / "defaults" / "main.yml").exists()])
    def test_defaults_no_conflicts(self, role):
        """Role defaults should not shadow Ansible built-in variables."""
        defaults_file = ROLES_DIR / role / "defaults" / "main.yml"
        with open(defaults_file) as f:
            data = yaml.safe_load(f)
        if not data:
            return  # Empty defaults are fine
        # Check no variable shadows Ansible built-ins
        builtin_vars = {"ansible_host", "ansible_connection", "ansible_user",
                         "ansible_become", "ansible_port", "gather_facts",
                         "hosts", "tasks", "roles", "vars"}
        for key in data:
            assert key not in builtin_vars, \
                f"Variable '{key}' in {role}/defaults shadows an Ansible built-in"


# ── Task naming convention ──────────────────────────────────


class TestTaskNaming:
    """Verify tasks follow the RoleName | Description convention."""

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_task_names_follow_convention(self, role):
        """Task names should follow 'RoleName | Description' pattern."""
        tasks_dir = ROLES_DIR / role / "tasks"
        for yml_file in tasks_dir.glob("*.yml"):
            with open(yml_file) as f:
                tasks = yaml.safe_load(f)
            if not isinstance(tasks, list):
                continue
            for task in tasks:
                if not isinstance(task, dict):
                    continue
                name = task.get("name", "")
                if not name:
                    continue
                # Skip blocks and includes
                if "block" in task or "ansible.builtin.include_tasks" in task:
                    continue
                # Convention: RoleName | Description
                assert " | " in name, \
                    f"Task name '{name}' in {role}/{yml_file.name} should contain ' | '"


# ── FQCN compliance ─────────────────────────────────────────


class TestFQCN:
    """Verify all modules use Fully Qualified Collection Names."""

    BUILTIN_MODULES = {
        "ansible.builtin.command", "ansible.builtin.shell",
        "ansible.builtin.copy", "ansible.builtin.template",
        "ansible.builtin.file", "ansible.builtin.lineinfile",
        "ansible.builtin.apt", "ansible.builtin.pip",
        "ansible.builtin.systemd", "ansible.builtin.service",
        "ansible.builtin.debug", "ansible.builtin.assert",
        "ansible.builtin.set_fact", "ansible.builtin.stat",
        "ansible.builtin.slurp", "ansible.builtin.user",
        "ansible.builtin.group", "ansible.builtin.include_tasks",
        "ansible.builtin.import_tasks", "ansible.builtin.include_role",
        "ansible.builtin.import_role", "ansible.builtin.meta",
        "ansible.builtin.raw", "ansible.builtin.uri",
        "ansible.builtin.wait_for", "ansible.builtin.package_facts",
        "ansible.builtin.get_url", "ansible.builtin.unarchive",
        "ansible.builtin.pause", "ansible.builtin.fail",
        "ansible.builtin.git", "ansible.builtin.blockinfile",
        "ansible.builtin.replace", "ansible.builtin.tempfile",
        "ansible.builtin.package",
    }

    SHORT_TO_FQCN = {
        "command": "ansible.builtin.command",
        "shell": "ansible.builtin.shell",
        "copy": "ansible.builtin.copy",
        "template": "ansible.builtin.template",
        "file": "ansible.builtin.file",
        "apt": "ansible.builtin.apt",
        "pip": "ansible.builtin.pip",
        "systemd": "ansible.builtin.systemd",
        "service": "ansible.builtin.service",
        "debug": "ansible.builtin.debug",
        "set_fact": "ansible.builtin.set_fact",
        "stat": "ansible.builtin.stat",
        "lineinfile": "ansible.builtin.lineinfile",
        "user": "ansible.builtin.user",
        "group": "ansible.builtin.group",
        "include_tasks": "ansible.builtin.include_tasks",
        "import_tasks": "ansible.builtin.import_tasks",
        "uri": "ansible.builtin.uri",
        "wait_for": "ansible.builtin.wait_for",
        "git": "ansible.builtin.git",
        "get_url": "ansible.builtin.get_url",
        "fail": "ansible.builtin.fail",
        "raw": "ansible.builtin.raw",
        "package": "ansible.builtin.package",
    }

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_no_short_module_names(self, role):
        """Tasks should use FQCN (ansible.builtin.X), not short names (X)."""
        tasks_dir = ROLES_DIR / role / "tasks"
        for yml_file in tasks_dir.glob("*.yml"):
            with open(yml_file) as f:
                tasks = yaml.safe_load(f)
            if not isinstance(tasks, list):
                continue
            for task in tasks:
                if not isinstance(task, dict):
                    continue
                for short_name in self.SHORT_TO_FQCN:
                    if short_name in task and short_name not in (
                        "name", "when", "register", "changed_when",
                        "failed_when", "loop", "with_items", "tags",
                        "notify", "become", "become_user", "vars",
                        "block", "rescue", "always", "environment",
                        "retries", "delay", "until", "no_log",
                    ):
                        # This task uses a short module name
                        msg = (
                            f"Task in {role}/{yml_file.name} uses short name '{short_name}', "
                            f"use '{self.SHORT_TO_FQCN[short_name]}' instead"
                        )
                        raise AssertionError(msg)


# ── Template rendering ──────────────────────────────────────


def _ansible_env(tmpl_dir):
    """Create a Jinja2 Environment with Ansible-compatible filters."""
    env = Environment(loader=FileSystemLoader(str(tmpl_dir)))
    # Add Ansible's regex_replace filter
    env.filters["regex_replace"] = lambda value, pattern, replacement: re.sub(pattern, replacement, value)
    return env


class TestTemplates:
    """Test Jinja2 template rendering with sample data."""

    def test_nftables_isolation_template(self):
        """nftables isolation template renders correctly."""
        tmpl_dir = ROLES_DIR / "incus_nftables" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("anklume-isolation.nft.j2")

        result = template.render(
            incus_nftables_all_bridges=["net-admin", "net-pro", "net-perso"],
            incus_nftables_resolved_policies=[
                {
                    "description": "Pro accesses AI",
                    "from_bridge": "net-pro",
                    "to_bridge": "net-ai-tools",
                    "ports": [3000, 8080],
                    "protocol": "tcp",
                    "bidirectional": False,
                },
            ],
        )
        assert "table inet anklume" in result
        assert "priority -1" in result
        assert 'iifname "net-admin" oifname "net-admin" accept' in result
        assert 'iifname "net-pro" oifname "net-ai-tools" tcp dport { 3000, 8080 } accept' in result
        assert "drop" in result

    def test_nftables_no_policies(self):
        """nftables template works without network policies."""
        tmpl_dir = ROLES_DIR / "incus_nftables" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("anklume-isolation.nft.j2")

        result = template.render(
            incus_nftables_all_bridges=["net-admin", "net-work"],
            incus_nftables_resolved_policies=[],
        )
        assert "table inet anklume" in result
        assert "Network policies" not in result
        # Should have same-bridge accept rules
        assert 'iifname "net-admin" oifname "net-admin" accept' in result
        assert 'iifname "net-work" oifname "net-work" accept' in result

    def test_nftables_single_bridge(self):
        """nftables template with a single bridge skips inter-bridge drop."""
        tmpl_dir = ROLES_DIR / "incus_nftables" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("anklume-isolation.nft.j2")

        result = template.render(
            incus_nftables_all_bridges=["net-solo"],
            incus_nftables_resolved_policies=[],
        )
        assert "table inet anklume" in result
        # No inter-bridge drop with only one bridge
        lines = [line.strip() for line in result.splitlines() if line.strip()]
        drop_lines = [line for line in lines if "drop" in line and "invalid" not in line]
        # Should only have the ct state invalid drop, not the inter-bridge drop
        assert len(drop_lines) <= 1

    def test_firewall_router_template(self):
        """Firewall router template renders with multiple interfaces."""
        tmpl_dir = ROLES_DIR / "firewall_router" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("firewall-router.nft.j2")

        result = template.render(
            firewall_router_interfaces=[
                {"name": "eth0", "bridge": "net-admin"},
                {"name": "eth1", "bridge": "net-pro"},
                {"name": "eth2", "bridge": "net-perso"},
            ],
            firewall_router_logging=True,
            firewall_router_log_prefix="FW",
        )
        assert "table inet anklume" in result
        assert "chain forward" in result
        assert "chain input" in result
        assert 'FW-DENY-ADMIN' in result
        assert 'FW-DENY-PRO' in result

    def test_firewall_router_no_logging(self):
        """Firewall router template works without logging."""
        tmpl_dir = ROLES_DIR / "firewall_router" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("firewall-router.nft.j2")

        result = template.render(
            firewall_router_interfaces=[
                {"name": "eth0", "bridge": "net-admin"},
                {"name": "eth1", "bridge": "net-pro"},
            ],
            firewall_router_logging=False,
            firewall_router_log_prefix="FW",
        )
        assert "table inet anklume" in result
        assert "log prefix" not in result

    def test_speaches_service_template(self):
        """Speaches STT service template renders correctly."""
        tmpl_dir = ROLES_DIR / "stt_server" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("speaches.service.j2")

        result = template.render(
            stt_server_host="0.0.0.0",
            stt_server_port=8000,
            stt_server_model="large-v3-turbo",
            stt_server_quantization="float16",
            stt_server_language="",
        )
        assert "[Unit]" in result
        assert "[Service]" in result
        assert "8000" in result
        assert "large-v3-turbo" in result

    def test_lobechat_service_template(self):
        """LobeChat service template renders correctly."""
        tmpl_dir = ROLES_DIR / "lobechat" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("lobechat.service.j2")

        result = template.render(
            lobechat_port=3210,
            lobechat_ollama_url="http://ai-ollama:11434",
        )
        assert "[Unit]" in result
        assert "[Service]" in result
        assert "3210" in result

    def test_opencode_service_template(self):
        """OpenCode service template renders correctly."""
        tmpl_dir = ROLES_DIR / "opencode_server" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("opencode.service.j2")

        result = template.render(
            opencode_server_port=4096,
            opencode_server_host="0.0.0.0",
            opencode_server_password="secret123",
        )
        assert "[Unit]" in result
        assert "[Service]" in result
        assert "4096" in result
        assert "secret123" in result
        assert "opencode serve" in result

    def test_opencode_config_template(self):
        """OpenCode config JSON template renders correctly."""
        tmpl_dir = ROLES_DIR / "opencode_server" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("opencode-config.json.j2")

        result = template.render(
            opencode_server_ollama_url="http://ai-ollama:11434/v1",
            opencode_server_model="qwen2.5-coder:32b",
        )
        import json
        data = json.loads(result)
        assert "provider" in data
        assert "ollama" in data["provider"]
        assert data["provider"]["ollama"]["options"]["baseURL"] == "http://ai-ollama:11434/v1"
        assert "qwen2.5-coder:32b" in data["provider"]["ollama"]["models"]

    def test_claude_settings_template(self):
        """Claude Code settings JSON template renders correctly."""
        tmpl_dir = ROLES_DIR / "dev_agent_runner" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("claude-settings.json.j2")

        result = template.render(
            dev_agent_runner_enable_teams=True,
            dev_agent_runner_permissions_mode="bypassPermissions",
        )
        import json
        data = json.loads(result)
        assert data["env"]["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] == "1"
        assert data["defaultMode"] == "bypassPermissions"
        assert "Edit" in data["permissions"]["allow"]
        assert "Bash(molecule *)" in data["permissions"]["allow"]

    def test_claude_settings_no_teams(self):
        """Claude settings without Agent Teams omits the flag."""
        tmpl_dir = ROLES_DIR / "dev_agent_runner" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("claude-settings.json.j2")

        result = template.render(
            dev_agent_runner_enable_teams=False,
            dev_agent_runner_permissions_mode="default",
        )
        import json
        data = json.loads(result)
        assert "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS" not in data.get("env", {})
        assert data["defaultMode"] == "default"


# ── Meta validation ─────────────────────────────────────────


class TestRoleMeta:
    """Verify role meta/main.yml has required fields."""

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_meta_has_galaxy_info(self, role):
        """Role meta has galaxy_info section."""
        meta_file = ROLES_DIR / role / "meta" / "main.yml"
        with open(meta_file) as f:
            data = yaml.safe_load(f)
        assert data is not None
        assert "galaxy_info" in data

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_meta_has_author(self, role):
        """Role meta has author field."""
        meta_file = ROLES_DIR / role / "meta" / "main.yml"
        with open(meta_file) as f:
            data = yaml.safe_load(f)
        gi = data.get("galaxy_info", {})
        assert "author" in gi, f"Missing author in {role}/meta/main.yml"
