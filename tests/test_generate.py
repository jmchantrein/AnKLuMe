"""Tests for the PSOT generator (scripts/generate.py)."""

import pytest
import yaml
from generate import MANAGED_BEGIN, MANAGED_END, detect_orphans, generate, load_infra, validate


@pytest.fixture()
def sample_infra():
    """Minimal valid infra.yml as a dict."""
    return {
        "project_name": "test-infra",
        "global": {
            "base_subnet": "10.100",
            "default_os_image": "images:debian/13",
            "default_connection": "community.general.incus",
            "default_user": "root",
        },
        "domains": {
            "admin": {
                "description": "Administration",
                "subnet_id": 0,
                "machines": {
                    "admin-ctrl": {
                        "description": "Controller",
                        "type": "lxc",
                        "ip": "10.100.0.10",
                        "config": {"security.nesting": "true"},
                        "roles": ["base_system"],
                    },
                },
            },
            "work": {
                "description": "Work environment",
                "subnet_id": 1,
                "machines": {
                    "dev-ws": {
                        "description": "Dev workspace",
                        "type": "lxc",
                        "ip": "10.100.1.10",
                    },
                },
            },
        },
    }


@pytest.fixture()
def infra_file(tmp_path, sample_infra):
    """Write sample infra to a YAML file and return its path."""
    p = tmp_path / "infra.yml"
    p.write_text(yaml.dump(sample_infra, sort_keys=False))
    return p


# -- load_infra ---------------------------------------------------------------


class TestLoadInfra:
    def test_load_returns_dict(self, infra_file):
        data = load_infra(infra_file)
        assert data["project_name"] == "test-infra"
        assert "admin" in data["domains"]


# -- validate ------------------------------------------------------------------


class TestValidate:
    def test_valid_infra(self, sample_infra):
        assert validate(sample_infra) == []

    def test_missing_required_key(self):
        assert len(validate({"project_name": "x"})) > 0

    def test_duplicate_subnet_id(self, sample_infra):
        sample_infra["domains"]["work"]["subnet_id"] = 0
        errors = validate(sample_infra)
        assert any("subnet_id 0 already used" in e for e in errors)

    def test_duplicate_machine_name(self, sample_infra):
        sample_infra["domains"]["work"]["machines"]["admin-ctrl"] = {"type": "lxc"}
        assert any("duplicate" in e for e in validate(sample_infra))

    def test_duplicate_ip(self, sample_infra):
        sample_infra["domains"]["work"]["machines"]["dev-ws"]["ip"] = "10.100.0.10"
        assert any("IP 10.100.0.10 already used" in e for e in validate(sample_infra))

    def test_ip_wrong_subnet(self, sample_infra):
        sample_infra["domains"]["admin"]["machines"]["admin-ctrl"]["ip"] = "10.100.1.10"
        assert any("not in subnet" in e for e in validate(sample_infra))

    def test_invalid_domain_name(self, sample_infra):
        sample_infra["domains"]["Bad_Name!"] = sample_infra["domains"].pop("admin")
        assert any("invalid name" in e for e in validate(sample_infra))

    def test_subnet_id_out_of_range(self, sample_infra):
        sample_infra["domains"]["admin"]["subnet_id"] = 255
        assert any("0-254" in e for e in validate(sample_infra))

    def test_missing_profile_reference(self, sample_infra):
        sample_infra["domains"]["admin"]["machines"]["admin-ctrl"]["profiles"] = ["nonexistent"]
        assert any("profile 'nonexistent' not defined" in e for e in validate(sample_infra))

    def test_default_profile_always_allowed(self, sample_infra):
        sample_infra["domains"]["admin"]["machines"]["admin-ctrl"]["profiles"] = ["default"]
        assert validate(sample_infra) == []

    def test_empty_domains(self, sample_infra):
        sample_infra["domains"] = {}
        assert validate(sample_infra) == []

    def test_ephemeral_validation_error(self, sample_infra):
        sample_infra["domains"]["admin"]["ephemeral"] = "yes"
        errors = validate(sample_infra)
        assert any("ephemeral must be a boolean" in e for e in errors)

    def test_ephemeral_machine_validation_error(self, sample_infra):
        sample_infra["domains"]["admin"]["machines"]["admin-ctrl"]["ephemeral"] = "yes"
        errors = validate(sample_infra)
        assert any("ephemeral must be a boolean" in e for e in errors)


# -- generate ------------------------------------------------------------------


class TestGenerate:
    def test_creates_all_files(self, sample_infra, tmp_path):
        generate(sample_infra, tmp_path)
        for f in [
            "inventory/admin.yml", "inventory/work.yml",
            "group_vars/all.yml", "group_vars/admin.yml", "group_vars/work.yml",
            "host_vars/admin-ctrl.yml", "host_vars/dev-ws.yml",
        ]:
            assert (tmp_path / f).exists(), f"Missing: {f}"

    def test_inventory_contains_host_and_ip(self, sample_infra, tmp_path):
        generate(sample_infra, tmp_path)
        content = (tmp_path / "inventory" / "admin.yml").read_text()
        assert "admin-ctrl" in content
        assert "10.100.0.10" in content

    def test_group_vars_all(self, sample_infra, tmp_path):
        generate(sample_infra, tmp_path)
        content = (tmp_path / "group_vars" / "all.yml").read_text()
        assert "project_name: test-infra" in content
        assert "base_subnet" in content
        assert "psot_default_connection: community.general.incus" in content
        assert "psot_default_user: root" in content

    def test_group_vars_domain_has_network(self, sample_infra, tmp_path):
        generate(sample_infra, tmp_path)
        content = (tmp_path / "group_vars" / "admin.yml").read_text()
        assert "net-admin" in content
        assert "10.100.0.0/24" in content
        assert "10.100.0.254" in content

    def test_host_vars_content(self, sample_infra, tmp_path):
        generate(sample_infra, tmp_path)
        content = (tmp_path / "host_vars" / "admin-ctrl.yml").read_text()
        assert "instance_type: lxc" in content
        assert "10.100.0.10" in content
        assert "base_system" in content
        assert "security.nesting" in content

    def test_managed_markers_present(self, sample_infra, tmp_path):
        generate(sample_infra, tmp_path)
        for f in tmp_path.rglob("*.yml"):
            text = f.read_text()
            assert MANAGED_BEGIN in text, f"{f.name} missing MANAGED_BEGIN"
            assert MANAGED_END in text, f"{f.name} missing MANAGED_END"

    def test_idempotent(self, sample_infra, tmp_path):
        generate(sample_infra, tmp_path)
        first = {str(f.relative_to(tmp_path)): f.read_text() for f in tmp_path.rglob("*.yml")}
        generate(sample_infra, tmp_path)
        second = {str(f.relative_to(tmp_path)): f.read_text() for f in tmp_path.rglob("*.yml")}
        assert first == second

    def test_preserves_user_content(self, sample_infra, tmp_path):
        generate(sample_infra, tmp_path)
        gv = tmp_path / "group_vars" / "admin.yml"
        gv.write_text(gv.read_text() + "\nmy_custom_var: hello\n")
        generate(sample_infra, tmp_path)
        content = gv.read_text()
        assert "my_custom_var: hello" in content
        assert MANAGED_BEGIN in content

    def test_dry_run_creates_no_files(self, sample_infra, tmp_path):
        generate(sample_infra, tmp_path, dry_run=True)
        assert not list(tmp_path.rglob("*.yml"))

    def test_host_without_ip(self, sample_infra, tmp_path):
        del sample_infra["domains"]["work"]["machines"]["dev-ws"]["ip"]
        generate(sample_infra, tmp_path)
        inv = (tmp_path / "inventory" / "work.yml").read_text()
        assert "dev-ws" in inv
        hv = (tmp_path / "host_vars" / "dev-ws.yml").read_text()
        assert "instance_ip" not in hv

    def test_domain_with_profiles(self, sample_infra, tmp_path):
        sample_infra["domains"]["admin"]["profiles"] = {
            "gpu-compute": {"devices": {"gpu": {"type": "gpu"}}},
        }
        sample_infra["domains"]["admin"]["machines"]["admin-ctrl"]["profiles"] = ["default", "gpu-compute"]
        generate(sample_infra, tmp_path)
        gv = (tmp_path / "group_vars" / "admin.yml").read_text()
        assert "gpu-compute" in gv

    def test_no_connection_vars_in_group_vars(self, sample_infra, tmp_path):
        """ansible_connection and ansible_user must NOT appear in any group_vars file.

        Connection is a playbook concern, not an inventory concern. Inventory
        variables override play-level keywords (Ansible precedence), which
        would break infrastructure roles that need connection: local.
        """
        generate(sample_infra, tmp_path)
        for f in (tmp_path / "group_vars").glob("*.yml"):
            content = f.read_text()
            assert "ansible_connection" not in content, f"{f.name} contains ansible_connection"
            assert "ansible_user" not in content, f"{f.name} contains ansible_user"


# -- ephemeral -----------------------------------------------------------------


class TestEphemeral:
    def test_ephemeral_default_false(self, sample_infra, tmp_path):
        """Domain without ephemeral -> host_vars contains instance_ephemeral: false."""
        generate(sample_infra, tmp_path)
        content = (tmp_path / "host_vars" / "admin-ctrl.yml").read_text()
        assert "instance_ephemeral: false" in content
        gv = (tmp_path / "group_vars" / "admin.yml").read_text()
        assert "domain_ephemeral: false" in gv

    def test_ephemeral_domain_true(self, sample_infra, tmp_path):
        """Domain with ephemeral: true -> machines inherit instance_ephemeral: true."""
        sample_infra["domains"]["admin"]["ephemeral"] = True
        generate(sample_infra, tmp_path)
        content = (tmp_path / "host_vars" / "admin-ctrl.yml").read_text()
        assert "instance_ephemeral: true" in content
        gv = (tmp_path / "group_vars" / "admin.yml").read_text()
        assert "domain_ephemeral: true" in gv

    def test_ephemeral_machine_override(self, sample_infra, tmp_path):
        """Domain ephemeral: true + machine ephemeral: false -> machine gets false."""
        sample_infra["domains"]["admin"]["ephemeral"] = True
        sample_infra["domains"]["admin"]["machines"]["admin-ctrl"]["ephemeral"] = False
        generate(sample_infra, tmp_path)
        content = (tmp_path / "host_vars" / "admin-ctrl.yml").read_text()
        assert "instance_ephemeral: false" in content

    def test_ephemeral_validation_error(self, sample_infra):
        """ephemeral: 'yes' (string) -> validation error."""
        sample_infra["domains"]["admin"]["ephemeral"] = "yes"
        errors = validate(sample_infra)
        assert any("ephemeral must be a boolean" in e for e in errors)

    def test_orphan_protection(self, sample_infra, tmp_path):
        """Protected orphan is reported but not deleted by --clean-orphans."""
        generate(sample_infra, tmp_path)
        # Create an orphan file that has ephemeral: false (protected)
        orphan_hv = tmp_path / "host_vars" / "old-machine.yml"
        orphan_hv.write_text("instance_ephemeral: false\ninstance_name: old-machine\n")
        # Create an unprotected orphan
        orphan_eph = tmp_path / "host_vars" / "temp-machine.yml"
        orphan_eph.write_text("instance_ephemeral: true\ninstance_name: temp-machine\n")

        orphans = detect_orphans(sample_infra, tmp_path)
        assert len(orphans) == 2

        # Verify protection flags
        orphan_dict = {o[0].stem: o[1] for o in orphans}
        assert orphan_dict["old-machine"] is True  # protected
        assert orphan_dict["temp-machine"] is False  # not protected


# -- detect_orphans ------------------------------------------------------------


class TestOrphans:
    def test_detect_orphan_files(self, sample_infra, tmp_path):
        generate(sample_infra, tmp_path)
        (tmp_path / "inventory" / "old-domain.yml").write_text("orphan")
        (tmp_path / "group_vars" / "old-domain.yml").write_text("orphan")
        (tmp_path / "host_vars" / "old-machine.yml").write_text("orphan")
        orphans = detect_orphans(sample_infra, tmp_path)
        assert len(orphans) == 3

    def test_no_false_positives(self, sample_infra, tmp_path):
        generate(sample_infra, tmp_path)
        assert detect_orphans(sample_infra, tmp_path) == []

    def test_all_yml_not_orphan(self, sample_infra, tmp_path):
        generate(sample_infra, tmp_path)
        orphans = detect_orphans(sample_infra, tmp_path)
        assert not any("all.yml" in str(o) for o in orphans)
