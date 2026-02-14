"""Tests for overall project structure integrity.

Validates:
- Required project files exist
- site.yml references only existing roles (cross-reference)
- infra.yml parses and has required keys
"""

from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ROLES_DIR = PROJECT_ROOT / "roles"


class TestRequiredFiles:
    """Verify essential project files exist."""

    REQUIRED = [
        "site.yml",
        "infra.yml",
        "Makefile",
        "pyproject.toml",
        "CLAUDE.md",
    ]

    def test_required_files_exist(self):
        missing = [f for f in self.REQUIRED if not (PROJECT_ROOT / f).exists()]
        assert not missing, f"Missing required files: {missing}"


class TestSiteYmlRoles:
    """Verify site.yml only references roles that exist on disk."""

    def test_all_referenced_roles_exist(self):
        data = yaml.safe_load((PROJECT_ROOT / "site.yml").read_text())
        existing_roles = {d.name for d in ROLES_DIR.iterdir() if d.is_dir()}
        missing = []
        for play in data:
            # Roles included via tasks (include_role)
            for task in play.get("tasks", []):
                if not isinstance(task, dict):
                    continue
                block = task.get("ansible.builtin.include_role", {})
                if isinstance(block, dict) and block.get("name"):
                    name = block["name"]
                    if name not in existing_roles:
                        missing.append(name)
            # Roles included via roles: key
            for role in play.get("roles", []):
                name = role.get("role", role) if isinstance(role, dict) else role
                if name not in existing_roles:
                    missing.append(name)
        assert not missing, f"site.yml references missing roles: {missing}"


class TestInfraYml:
    """Verify infra.yml parses and has required structure."""

    def test_parses_with_required_keys(self):
        data = yaml.safe_load((PROJECT_ROOT / "infra.yml").read_text())
        assert isinstance(data, dict)
        assert "project_name" in data, "infra.yml missing project_name"
        assert "domains" in data, "infra.yml missing domains"
        assert isinstance(data["domains"], dict)
        assert len(data["domains"]) >= 1, "infra.yml has no domains"
