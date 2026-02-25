"""Tests for Phase 41: Official Roles and Galaxy Integration.

Covers:
- requirements.yml structure
- ansible.cfg roles_path configuration
- .gitignore vendor roles entry
- ADR-045 in ARCHITECTURE.md
- SPEC.md role resolution documentation
- Behavior matrix cells GR-001 to GR-005, GR-2-001
"""

import re
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = PROJECT_ROOT / "requirements.yml"
ANSIBLE_CFG = PROJECT_ROOT / "ansible.cfg"
GITIGNORE = PROJECT_ROOT / ".gitignore"
ARCHITECTURE = PROJECT_ROOT / "docs" / "ARCHITECTURE.md"
SPEC = PROJECT_ROOT / "docs" / "SPEC.md"
MAKEFILE = PROJECT_ROOT / "Makefile"


# -- GR-001: requirements.yml structure --------------------------------------


class TestRequirementsYml:
    """Verify requirements.yml has both collections and roles sections.

    # Matrix: GR-001
    """

    @classmethod
    def setup_class(cls):
        with open(REQUIREMENTS) as f:
            cls.data = yaml.safe_load(f)
        cls.content = REQUIREMENTS.read_text()

    def test_file_exists(self):
        assert REQUIREMENTS.is_file()

    def test_has_collections_key(self):
        assert "collections" in self.data

    def test_has_roles_key(self):
        assert "roles" in self.data

    def test_collections_is_list(self):
        assert isinstance(self.data["collections"], list)

    def test_roles_is_list(self):
        assert isinstance(self.data["roles"], list)

    def test_community_general_present(self):
        names = [c["name"] for c in self.data["collections"]]
        assert "community.general" in names

    def test_ansible_posix_present(self):
        names = [c["name"] for c in self.data["collections"]]
        assert "ansible.posix" in names


# -- GR-002: ansible.cfg roles_path -----------------------------------------


class TestAnsibleCfg:
    """Verify ansible.cfg has three-tier roles_path.

    # Matrix: GR-002
    """

    @classmethod
    def setup_class(cls):
        cls.content = ANSIBLE_CFG.read_text()

    def test_has_roles_path(self):
        assert "roles_path" in self.content

    def test_roles_path_three_tiers(self):
        """roles_path includes roles_custom, roles, roles_vendor."""
        match = re.search(r"roles_path\s*=\s*(.+)", self.content)
        assert match is not None
        path_value = match.group(1).strip()
        parts = [p.strip().rstrip("/") for p in path_value.split(":")]
        assert "roles_custom" in parts[0], "roles_custom should be first"
        assert parts[1] == "roles", "roles should be second"
        assert "roles_vendor" in parts[2], "roles_vendor should be third"

    def test_roles_custom_highest_priority(self):
        """roles_custom/ is first in path (highest priority)."""
        match = re.search(r"roles_path\s*=\s*(.+)", self.content)
        path_value = match.group(1).strip()
        parts = path_value.split(":")
        assert "roles_custom" in parts[0]


# -- GR-002 (depth 2): Priority order verified -----

class TestRolesPathPriority:
    """Verify roles_path resolves custom > native > vendor.

    # Matrix: GR-2-001
    """

    def test_exact_roles_path(self):
        content = ANSIBLE_CFG.read_text()
        assert "roles_path = roles_custom/:roles/:roles_vendor/" in content


# -- GR-003: .gitignore vendor roles ----------------------------------------


class TestGitignoreVendor:
    """Verify .gitignore contains roles_vendor entry.

    # Matrix: GR-003
    """

    @classmethod
    def setup_class(cls):
        cls.content = GITIGNORE.read_text()

    def test_roles_vendor_gitignored(self):
        assert "/roles_vendor/" in self.content

    def test_roles_custom_gitignored(self):
        """Also verify roles_custom is still gitignored."""
        assert "/roles_custom/" in self.content


# -- GR-004: ADR-045 in ARCHITECTURE.md -------------------------------------


class TestADR045:
    """Verify ADR-045 documents Galaxy role integration.

    # Matrix: GR-004
    """

    @classmethod
    def setup_class(cls):
        cls.content = ARCHITECTURE.read_text()

    def test_adr045_exists(self):
        assert "ADR-045" in self.content

    def test_adr045_title(self):
        assert "Official roles via Galaxy" in self.content

    def test_adr045_three_tiers(self):
        assert "roles_custom" in self.content
        assert "roles_vendor" in self.content

    def test_adr045_requirements_yml(self):
        assert "requirements.yml" in self.content

    def test_adr045_make_init(self):
        assert "make init" in self.content


# -- GR-005: SPEC.md role resolution ----------------------------------------


class TestSpecRoleResolution:
    """Verify SPEC.md documents role resolution order.

    # Matrix: GR-005
    """

    @classmethod
    def setup_class(cls):
        cls.content = SPEC.read_text()

    def test_roles_section_exists(self):
        assert "### Roles and provisioning" in self.content

    def test_three_directories_documented(self):
        assert "roles_custom" in self.content
        assert "roles_vendor" in self.content

    def test_priority_order_documented(self):
        """Priority order is documented (custom > native > vendor)."""
        assert "priority" in self.content.lower()

    def test_galaxy_role_integration(self):
        assert "Galaxy" in self.content

    def test_requirements_yml_format(self):
        assert "requirements.yml" in self.content


# -- Makefile integration ---------------------------------------------------


class TestMakefileInit:
    """Verify make init installs Galaxy roles."""

    @classmethod
    def setup_class(cls):
        cls.content = MAKEFILE.read_text()

    def test_init_installs_galaxy_roles(self):
        """make init includes ansible-galaxy role install."""
        assert "ansible-galaxy role install" in self.content

    def test_init_creates_roles_vendor(self):
        """make init creates roles_vendor directory."""
        assert "roles_vendor" in self.content
