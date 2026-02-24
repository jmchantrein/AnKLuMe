"""Tests for Phase 37: Per-domain OpenClaw instances (ADR-043).

Covers:
- Generator validation of openclaw boolean directive
- Enrichment: auto-creation of <domain>-openclaw machines
- Multi-instance configuration: domain_openclaw in group_vars
- User-declared openclaw machines take precedence
- Domain-aware role defaults and templates
"""

from pathlib import Path

import yaml
from generate import enrich_infra, generate, get_warnings, validate

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ROLE_DIR = PROJECT_ROOT / "roles" / "openclaw_server"


def _base_infra(**overrides):
    """Build a minimal valid infra with addressing."""
    infra = {
        "project_name": "test-openclaw",
        "global": {
            "addressing": {"base_octet": 10, "zone_base": 100, "zone_step": 10},
            "default_os_image": "images:debian/13",
            "default_connection": "community.general.incus",
            "default_user": "root",
        },
        "domains": {
            "pro": {
                "trust_level": "trusted",
                "description": "Professional workspace",
                "machines": {
                    "pw-dev": {
                        "description": "Dev env",
                        "type": "lxc",
                        "roles": ["base_system"],
                    },
                },
            },
        },
    }
    for k, v in overrides.items():
        if k == "domains":
            infra["domains"].update(v)
        else:
            infra[k] = v
    return infra


# -- Validation ---------------------------------------------------------------


class TestOpenclawValidation:
    """Validate the openclaw directive on domains."""

    def test_openclaw_true_valid(self):  # Matrix: OC-001
        """openclaw: true is accepted."""
        infra = _base_infra()
        infra["domains"]["pro"]["openclaw"] = True
        errors = validate(infra, check_host_subnets=False)
        assert not any("openclaw" in e for e in errors)

    def test_openclaw_false_valid(self):  # Matrix: OC-001
        """openclaw: false is accepted."""
        infra = _base_infra()
        infra["domains"]["pro"]["openclaw"] = False
        errors = validate(infra, check_host_subnets=False)
        assert not any("openclaw" in e for e in errors)

    def test_openclaw_absent_valid(self):  # Matrix: OC-001
        """Absent openclaw field raises no error."""
        infra = _base_infra()
        errors = validate(infra, check_host_subnets=False)
        assert not any("openclaw" in e for e in errors)

    def test_openclaw_invalid_string(self):  # Matrix: OC-002
        """openclaw: 'yes' is rejected."""
        infra = _base_infra()
        infra["domains"]["pro"]["openclaw"] = "yes"
        errors = validate(infra, check_host_subnets=False)
        assert any("openclaw must be a boolean" in e for e in errors)

    def test_openclaw_invalid_int(self):  # Matrix: OC-002
        """openclaw: 1 is rejected."""
        infra = _base_infra()
        infra["domains"]["pro"]["openclaw"] = 1
        errors = validate(infra, check_host_subnets=False)
        assert any("openclaw must be a boolean" in e for e in errors)


# -- Enrichment ---------------------------------------------------------------


class TestOpenclawEnrichment:
    """Test auto-creation of <domain>-openclaw machines."""

    def test_auto_creates_machine(self):  # Matrix: OC-003
        """openclaw: true creates <domain>-openclaw machine."""
        infra = _base_infra()
        infra["domains"]["pro"]["openclaw"] = True
        errors = validate(infra, check_host_subnets=False)
        assert not errors
        enrich_infra(infra)
        machines = infra["domains"]["pro"]["machines"]
        assert "pro-openclaw" in machines

    def test_auto_created_machine_properties(self):  # Matrix: OC-003
        """Auto-created machine has correct type, roles, ephemeral."""
        infra = _base_infra()
        infra["domains"]["pro"]["openclaw"] = True
        errors = validate(infra, check_host_subnets=False)
        assert not errors
        enrich_infra(infra)
        m = infra["domains"]["pro"]["machines"]["pro-openclaw"]
        assert m["type"] == "lxc"
        assert m["roles"] == ["base_system", "openclaw_server"]
        assert m["ephemeral"] is False

    def test_auto_created_gets_ip(self):  # Matrix: OC-003
        """Auto-created machine gets auto-assigned IP."""
        infra = _base_infra()
        infra["domains"]["pro"]["openclaw"] = True
        errors = validate(infra, check_host_subnets=False)
        assert not errors
        enrich_infra(infra)
        m = infra["domains"]["pro"]["machines"]["pro-openclaw"]
        assert m.get("ip") is not None
        assert m["ip"].startswith("10.110.")

    def test_user_declared_not_overwritten(self):  # Matrix: OC-004
        """Explicit <domain>-openclaw is preserved."""
        infra = _base_infra()
        infra["domains"]["pro"]["openclaw"] = True
        infra["domains"]["pro"]["machines"]["pro-openclaw"] = {
            "description": "Custom OpenClaw",
            "type": "lxc",
            "roles": ["base_system", "openclaw_server"],
        }
        errors = validate(infra, check_host_subnets=False)
        assert not errors
        enrich_infra(infra)
        m = infra["domains"]["pro"]["machines"]["pro-openclaw"]
        assert m["description"] == "Custom OpenClaw"

    def test_no_creation_when_false(self):  # Matrix: OC-005
        """openclaw: false does not create a machine."""
        infra = _base_infra()
        infra["domains"]["pro"]["openclaw"] = False
        errors = validate(infra, check_host_subnets=False)
        assert not errors
        enrich_infra(infra)
        assert "pro-openclaw" not in infra["domains"]["pro"]["machines"]

    def test_no_creation_when_absent(self):  # Matrix: OC-005
        """Absent openclaw does not create a machine."""
        infra = _base_infra()
        errors = validate(infra, check_host_subnets=False)
        assert not errors
        enrich_infra(infra)
        assert "pro-openclaw" not in infra["domains"]["pro"]["machines"]

    def test_disabled_domain_skipped(self):  # Matrix: OC-005
        """openclaw: true on disabled domain does not create machine."""
        infra = _base_infra()
        infra["domains"]["pro"]["openclaw"] = True
        infra["domains"]["pro"]["enabled"] = False
        errors = validate(infra, check_host_subnets=False)
        assert not errors
        enrich_infra(infra)
        assert "pro-openclaw" not in infra["domains"]["pro"]["machines"]

    def test_multiple_domains(self):  # Matrix: OC-006
        """Multiple domains with openclaw: true each get their own machine."""
        infra = _base_infra()
        infra["domains"]["pro"]["openclaw"] = True
        infra["domains"]["perso"] = {
            "trust_level": "trusted",
            "description": "Personal",
            "openclaw": True,
            "machines": {
                "perso-ws": {
                    "description": "Personal workspace",
                    "type": "lxc",
                },
            },
        }
        errors = validate(infra, check_host_subnets=False)
        assert not errors
        enrich_infra(infra)
        assert "pro-openclaw" in infra["domains"]["pro"]["machines"]
        assert "perso-openclaw" in infra["domains"]["perso"]["machines"]

    def test_no_ip_collision_multi_domain(self):  # Matrix: OC-006
        """Auto-created machines in different domains get different IPs."""
        infra = _base_infra()
        infra["domains"]["pro"]["openclaw"] = True
        infra["domains"]["perso"] = {
            "trust_level": "trusted",
            "description": "Personal",
            "openclaw": True,
            "machines": {
                "perso-ws": {
                    "description": "Personal workspace",
                    "type": "lxc",
                },
            },
        }
        errors = validate(infra, check_host_subnets=False)
        assert not errors
        enrich_infra(infra)
        pro_ip = infra["domains"]["pro"]["machines"]["pro-openclaw"]["ip"]
        perso_ip = infra["domains"]["perso"]["machines"]["perso-openclaw"]["ip"]
        assert pro_ip != perso_ip


# -- Generation ---------------------------------------------------------------


class TestOpenclawGeneration:
    """Test generated Ansible files for openclaw domains."""

    def test_domain_openclaw_in_group_vars(self, tmp_path):  # Matrix: OC-007
        """domain_openclaw: true appears in group_vars."""
        infra = _base_infra()
        infra["domains"]["pro"]["openclaw"] = True
        errors = validate(infra, check_host_subnets=False)
        assert not errors
        enrich_infra(infra)
        generate(infra, tmp_path)
        gv = yaml.safe_load((tmp_path / "group_vars" / "pro.yml").read_text())
        assert gv.get("domain_openclaw") is True

    def test_domain_openclaw_absent_when_false(self, tmp_path):  # Matrix: OC-007
        """domain_openclaw not in group_vars when openclaw: false."""
        infra = _base_infra()
        errors = validate(infra, check_host_subnets=False)
        assert not errors
        enrich_infra(infra)
        generate(infra, tmp_path)
        gv = yaml.safe_load((tmp_path / "group_vars" / "pro.yml").read_text())
        assert "domain_openclaw" not in gv

    def test_openclaw_machine_host_vars(self, tmp_path):  # Matrix: OC-007
        """Auto-created openclaw machine has host_vars with correct roles."""
        infra = _base_infra()
        infra["domains"]["pro"]["openclaw"] = True
        errors = validate(infra, check_host_subnets=False)
        assert not errors
        enrich_infra(infra)
        generate(infra, tmp_path)
        hv_path = tmp_path / "host_vars" / "pro-openclaw.yml"
        assert hv_path.exists()
        hv = yaml.safe_load(hv_path.read_text())
        assert "openclaw_server" in hv["instance_roles"]

    def test_openclaw_machine_in_inventory(self, tmp_path):  # Matrix: OC-007
        """Auto-created openclaw machine appears in inventory."""
        infra = _base_infra()
        infra["domains"]["pro"]["openclaw"] = True
        errors = validate(infra, check_host_subnets=False)
        assert not errors
        enrich_infra(infra)
        generate(infra, tmp_path)
        inv_path = tmp_path / "inventory" / "pro.yml"
        inv = yaml.safe_load(inv_path.read_text())
        hosts = inv["all"]["children"]["pro"]["hosts"]
        assert "pro-openclaw" in hosts

    def test_no_warnings_for_openclaw(self):
        """openclaw: true produces no warnings."""
        infra = _base_infra()
        infra["domains"]["pro"]["openclaw"] = True
        errors = validate(infra, check_host_subnets=False)
        assert not errors
        enrich_infra(infra)
        warnings = get_warnings(infra)
        assert not any("openclaw" in w.lower() for w in warnings)


# -- Role structure -----------------------------------------------------------


class TestOpenclawRoleDomainAware:
    """Verify openclaw_server role files are domain-aware."""

    def test_defaults_has_domain_var(self):
        """Defaults include openclaw_server_domain."""
        content = (ROLE_DIR / "defaults" / "main.yml").read_text()
        assert "openclaw_server_domain" in content

    def test_defaults_has_instance_name_var(self):
        """Defaults include openclaw_server_instance_name."""
        content = (ROLE_DIR / "defaults" / "main.yml").read_text()
        assert "openclaw_server_instance_name" in content

    def test_service_template_domain_aware(self):
        """Service template references openclaw_server_domain."""
        content = (ROLE_DIR / "templates" / "openclaw.service.j2").read_text()
        assert "openclaw_server_domain" in content

    def test_identity_template_domain_aware(self):
        """IDENTITY.md.j2 references openclaw_server_domain."""
        content = (ROLE_DIR / "templates" / "IDENTITY.md.j2").read_text()
        assert "openclaw_server_domain" in content

    def test_agents_template_domain_aware(self):
        """AGENTS.md.j2 references openclaw_server_domain."""
        content = (ROLE_DIR / "templates" / "AGENTS.md.j2").read_text()
        assert "openclaw_server_domain" in content

    def test_tools_template_domain_aware(self):
        """TOOLS.md.j2 references openclaw_server_domain."""
        content = (ROLE_DIR / "templates" / "TOOLS.md.j2").read_text()
        assert "openclaw_server_domain" in content

    def test_user_template_domain_aware(self):
        """USER.md.j2 references openclaw_server_domain."""
        content = (ROLE_DIR / "templates" / "USER.md.j2").read_text()
        assert "openclaw_server_domain" in content

    def test_memory_template_domain_aware(self):
        """MEMORY.md.j2 references openclaw_server_domain."""
        content = (ROLE_DIR / "templates" / "MEMORY.md.j2").read_text()
        assert "openclaw_server_domain" in content

    def test_tasks_compute_service_name(self):
        """Tasks compute per-domain service name."""
        content = (ROLE_DIR / "tasks" / "main.yml").read_text()
        assert "_openclaw_service_name" in content

    def test_handler_uses_dynamic_service_name(self):
        """Handler references openclaw_server_domain for service name."""
        content = (ROLE_DIR / "handlers" / "main.yml").read_text()
        assert "openclaw_server_domain" in content
