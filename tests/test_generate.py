"""Tests for the PSOT generator (scripts/generate.py)."""

import generate as gen_mod
import pytest
import yaml
from generate import (
    MANAGED_BEGIN,
    MANAGED_END,
    detect_orphans,
    enrich_infra,
    generate,
    get_warnings,
    load_infra,
    validate,
)


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
            "anklume": {
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
        assert "anklume" in data["domains"]


# -- validate ------------------------------------------------------------------


class TestValidate:
    def test_valid_infra(self, sample_infra):  # Matrix: DL-001
        assert validate(sample_infra) == []

    def test_missing_required_key(self):
        assert len(validate({"project_name": "x"})) > 0

    def test_duplicate_subnet_id(self, sample_infra):  # Matrix: DL-002
        sample_infra["domains"]["work"]["subnet_id"] = 0
        errors = validate(sample_infra)
        assert any("subnet_id 0 already used" in e for e in errors)

    def test_duplicate_machine_name(self, sample_infra):  # Matrix: DL-003
        sample_infra["domains"]["work"]["machines"]["admin-ctrl"] = {"type": "lxc"}
        assert any("duplicate" in e for e in validate(sample_infra))

    def test_duplicate_ip(self, sample_infra):  # Matrix: DL-004
        sample_infra["domains"]["work"]["machines"]["dev-ws"]["ip"] = "10.100.0.10"
        assert any("IP 10.100.0.10 already used" in e for e in validate(sample_infra))

    def test_ip_wrong_subnet(self, sample_infra):  # Matrix: DL-005
        sample_infra["domains"]["anklume"]["machines"]["admin-ctrl"]["ip"] = "10.100.1.10"
        assert any("not in subnet" in e for e in validate(sample_infra))

    def test_invalid_domain_name(self, sample_infra):  # Matrix: DL-006
        sample_infra["domains"]["Bad_Name!"] = sample_infra["domains"].pop("anklume")
        assert any("invalid name" in e for e in validate(sample_infra))

    def test_subnet_id_out_of_range(self, sample_infra):  # Matrix: DL-007
        sample_infra["domains"]["anklume"]["subnet_id"] = 255
        assert any("0-254" in e for e in validate(sample_infra))

    def test_missing_profile_reference(self, sample_infra):  # Matrix: DL-008
        sample_infra["domains"]["anklume"]["machines"]["admin-ctrl"]["profiles"] = ["nonexistent"]
        assert any("profile 'nonexistent' not defined" in e for e in validate(sample_infra))

    def test_default_profile_always_allowed(self, sample_infra):  # Matrix: DL-009
        sample_infra["domains"]["anklume"]["machines"]["admin-ctrl"]["profiles"] = ["default"]
        assert validate(sample_infra) == []

    def test_empty_domains(self, sample_infra):  # Matrix: DL-010
        sample_infra["domains"] = {}
        assert validate(sample_infra) == []

    def test_ephemeral_validation_error(self, sample_infra):  # Matrix: EL-004
        sample_infra["domains"]["anklume"]["ephemeral"] = "yes"
        errors = validate(sample_infra)
        assert any("ephemeral must be a boolean" in e for e in errors)

    def test_ephemeral_machine_validation_error(self, sample_infra):  # Matrix: EL-005
        sample_infra["domains"]["anklume"]["machines"]["admin-ctrl"]["ephemeral"] = "yes"
        errors = validate(sample_infra)
        assert any("ephemeral must be a boolean" in e for e in errors)

    def test_trust_level_valid(self, sample_infra):
        """Valid trust_level values are accepted."""
        for trust_level in ("admin", "trusted", "semi-trusted", "untrusted", "disposable"):
            test_infra = sample_infra.copy()
            test_infra["domains"]["anklume"]["trust_level"] = trust_level
            errors = validate(test_infra)
            assert not any("trust_level" in e for e in errors)

    def test_trust_level_invalid(self, sample_infra):
        """Invalid trust_level value triggers error."""
        sample_infra["domains"]["anklume"]["trust_level"] = "bogus"
        errors = validate(sample_infra)
        assert any("trust_level must be one of" in e for e in errors)
        assert any("bogus" in e for e in errors)

    def test_trust_level_omitted(self, sample_infra):
        """Omitted trust_level is valid (it's optional)."""
        # sample_infra has no trust_level by default
        errors = validate(sample_infra)
        assert not any("trust_level" in e for e in errors)


# -- generate ------------------------------------------------------------------


class TestGenerate:
    def test_creates_all_files(self, sample_infra, tmp_path):  # Matrix: PG-001
        generate(sample_infra, tmp_path)
        for f in [
            "inventory/anklume.yml", "inventory/work.yml",
            "group_vars/all.yml", "group_vars/anklume.yml", "group_vars/work.yml",
            "host_vars/admin-ctrl.yml", "host_vars/dev-ws.yml",
        ]:
            assert (tmp_path / f).exists(), f"Missing: {f}"

    def test_inventory_contains_host_and_ip(self, sample_infra, tmp_path):  # Matrix: PG-010
        generate(sample_infra, tmp_path)
        content = (tmp_path / "inventory" / "anklume.yml").read_text()
        assert "admin-ctrl" in content
        assert "10.100.0.10" in content

    def test_group_vars_all(self, sample_infra, tmp_path):  # Matrix: PG-006
        generate(sample_infra, tmp_path)
        content = (tmp_path / "group_vars" / "all.yml").read_text()
        assert "project_name: test-infra" in content
        assert "base_subnet" in content
        assert "psot_default_connection: community.general.incus" in content
        assert "psot_default_user: root" in content

    def test_group_vars_domain_has_network(self, sample_infra, tmp_path):  # Matrix: PG-007
        generate(sample_infra, tmp_path)
        content = (tmp_path / "group_vars" / "anklume.yml").read_text()
        assert "net-anklume" in content
        assert "10.100.0.0/24" in content
        assert "10.100.0.254" in content

    def test_host_vars_content(self, sample_infra, tmp_path):  # Matrix: PG-008
        generate(sample_infra, tmp_path)
        content = (tmp_path / "host_vars" / "admin-ctrl.yml").read_text()
        assert "instance_type: lxc" in content
        assert "10.100.0.10" in content
        assert "base_system" in content
        assert "security.nesting" in content

    def test_managed_markers_present(self, sample_infra, tmp_path):  # Matrix: PG-005
        generate(sample_infra, tmp_path)
        for f in tmp_path.rglob("*.yml"):
            text = f.read_text()
            assert MANAGED_BEGIN in text, f"{f.name} missing MANAGED_BEGIN"
            assert MANAGED_END in text, f"{f.name} missing MANAGED_END"

    def test_idempotent(self, sample_infra, tmp_path):  # Matrix: PG-002
        generate(sample_infra, tmp_path)
        first = {str(f.relative_to(tmp_path)): f.read_text() for f in tmp_path.rglob("*.yml")}
        generate(sample_infra, tmp_path)
        second = {str(f.relative_to(tmp_path)): f.read_text() for f in tmp_path.rglob("*.yml")}
        assert first == second

    def test_preserves_user_content(self, sample_infra, tmp_path):  # Matrix: PG-003
        generate(sample_infra, tmp_path)
        gv = tmp_path / "group_vars" / "anklume.yml"
        gv.write_text(gv.read_text() + "\nmy_custom_var: hello\n")
        generate(sample_infra, tmp_path)
        content = gv.read_text()
        assert "my_custom_var: hello" in content
        assert MANAGED_BEGIN in content

    def test_dry_run_creates_no_files(self, sample_infra, tmp_path):  # Matrix: PG-004
        generate(sample_infra, tmp_path, dry_run=True)
        assert not list(tmp_path.rglob("*.yml"))

    def test_host_without_ip(self, sample_infra, tmp_path):  # Matrix: DL-011
        del sample_infra["domains"]["work"]["machines"]["dev-ws"]["ip"]
        generate(sample_infra, tmp_path)
        inv = (tmp_path / "inventory" / "work.yml").read_text()
        assert "dev-ws" in inv
        hv = (tmp_path / "host_vars" / "dev-ws.yml").read_text()
        assert "instance_ip" not in hv

    def test_domain_with_profiles(self, sample_infra, tmp_path):  # Matrix: DL-2-003
        sample_infra["domains"]["anklume"]["profiles"] = {
            "gpu-compute": {"devices": {"gpu": {"type": "gpu"}}},
        }
        sample_infra["domains"]["anklume"]["machines"]["admin-ctrl"]["profiles"] = ["default", "gpu-compute"]
        generate(sample_infra, tmp_path)
        gv = (tmp_path / "group_vars" / "anklume.yml").read_text()
        assert "gpu-compute" in gv

    def test_host_vars_with_devices(self, sample_infra, tmp_path):  # Matrix: DL-2-004
        """Machine with devices declaration produces instance_devices in host_vars."""
        sample_infra["domains"]["anklume"]["machines"]["admin-ctrl"]["devices"] = {
            "gpu": {"type": "gpu"},
        }
        sample_infra["domains"]["anklume"]["machines"]["admin-ctrl"]["config"] = {
            "nvidia.runtime": "true",
        }
        generate(sample_infra, tmp_path)
        content = (tmp_path / "host_vars" / "admin-ctrl.yml").read_text()
        assert "instance_devices" in content
        assert "gpu" in content
        assert "nvidia.runtime" in content

    def test_host_vars_without_devices(self, sample_infra, tmp_path):
        """Machine without devices declaration omits instance_devices from host_vars."""
        generate(sample_infra, tmp_path)
        content = (tmp_path / "host_vars" / "dev-ws.yml").read_text()
        assert "instance_devices" not in content

    def test_no_connection_vars_in_group_vars(self, sample_infra, tmp_path):  # Matrix: PG-009
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

    def test_trust_level_propagated(self, sample_infra, tmp_path):
        """Domain with trust_level generates domain_trust_level in group_vars."""
        sample_infra["domains"]["anklume"]["trust_level"] = "untrusted"
        generate(sample_infra, tmp_path)
        content = (tmp_path / "group_vars" / "anklume.yml").read_text()
        assert "domain_trust_level: untrusted" in content

    def test_trust_level_omitted_not_in_group_vars(self, sample_infra, tmp_path):
        """Domain without trust_level does not have domain_trust_level in group_vars."""
        # sample_infra has no trust_level by default
        generate(sample_infra, tmp_path)
        content = (tmp_path / "group_vars" / "anklume.yml").read_text()
        assert "domain_trust_level" not in content


# -- ephemeral -----------------------------------------------------------------


class TestEphemeral:
    def test_ephemeral_default_false(self, sample_infra, tmp_path):  # Matrix: EL-001
        """Domain without ephemeral -> host_vars contains instance_ephemeral: false."""
        generate(sample_infra, tmp_path)
        content = (tmp_path / "host_vars" / "admin-ctrl.yml").read_text()
        assert "instance_ephemeral: false" in content
        gv = (tmp_path / "group_vars" / "anklume.yml").read_text()
        assert "domain_ephemeral: false" in gv

    def test_ephemeral_domain_true(self, sample_infra, tmp_path):  # Matrix: EL-002
        """Domain with ephemeral: true -> machines inherit instance_ephemeral: true."""
        sample_infra["domains"]["anklume"]["ephemeral"] = True
        generate(sample_infra, tmp_path)
        content = (tmp_path / "host_vars" / "admin-ctrl.yml").read_text()
        assert "instance_ephemeral: true" in content
        gv = (tmp_path / "group_vars" / "anklume.yml").read_text()
        assert "domain_ephemeral: true" in gv

    def test_ephemeral_machine_override(self, sample_infra, tmp_path):  # Matrix: EL-003, DL-2-001
        """Domain ephemeral: true + machine ephemeral: false -> machine gets false."""
        sample_infra["domains"]["anklume"]["ephemeral"] = True
        sample_infra["domains"]["anklume"]["machines"]["admin-ctrl"]["ephemeral"] = False
        generate(sample_infra, tmp_path)
        content = (tmp_path / "host_vars" / "admin-ctrl.yml").read_text()
        assert "instance_ephemeral: false" in content

    def test_ephemeral_validation_error(self, sample_infra):  # Matrix: EL-004
        """ephemeral: 'yes' (string) -> validation error."""
        sample_infra["domains"]["anklume"]["ephemeral"] = "yes"
        errors = validate(sample_infra)
        assert any("ephemeral must be a boolean" in e for e in errors)


# -- VM support ----------------------------------------------------------------


class TestVMSupport:
    def test_vm_type_accepted(self, sample_infra):  # Matrix: VM-001
        """type: vm is a valid instance type."""
        sample_infra["domains"]["work"]["machines"]["dev-ws"]["type"] = "vm"
        assert validate(sample_infra) == []

    def test_lxc_type_accepted(self, sample_infra):  # Matrix: VM-002
        """type: lxc is the default and valid."""
        assert validate(sample_infra) == []

    def test_invalid_type_rejected(self, sample_infra):  # Matrix: VM-003
        """type: docker is not a valid instance type."""
        sample_infra["domains"]["work"]["machines"]["dev-ws"]["type"] = "docker"
        errors = validate(sample_infra)
        assert any("type must be 'lxc' or 'vm'" in e for e in errors)

    def test_vm_host_vars_type(self, sample_infra, tmp_path):  # Matrix: VM-004
        """VM machine produces instance_type: vm in host_vars."""
        sample_infra["domains"]["work"]["machines"]["dev-ws"]["type"] = "vm"
        generate(sample_infra, tmp_path)
        content = (tmp_path / "host_vars" / "dev-ws.yml").read_text()
        assert "instance_type: vm" in content

    def test_vm_and_lxc_coexist(self, sample_infra, tmp_path):  # Matrix: VM-2-001
        """VM and LXC instances can coexist in the same domain."""
        sample_infra["domains"]["work"]["machines"]["work-vm"] = {
            "description": "VM instance",
            "type": "vm",
            "ip": "10.100.1.20",
        }
        errors = validate(sample_infra)
        assert errors == []
        generate(sample_infra, tmp_path)
        lxc_hv = (tmp_path / "host_vars" / "dev-ws.yml").read_text()
        vm_hv = (tmp_path / "host_vars" / "work-vm.yml").read_text()
        assert "instance_type: lxc" in lxc_hv
        assert "instance_type: vm" in vm_hv

    def test_vm_with_config(self, sample_infra, tmp_path):  # Matrix: VM-006, DL-012
        """VM with resource config generates correct host_vars."""
        sample_infra["domains"]["work"]["machines"]["dev-ws"]["type"] = "vm"
        sample_infra["domains"]["work"]["machines"]["dev-ws"]["config"] = {
            "limits.cpu": "2",
            "limits.memory": "2GiB",
        }
        generate(sample_infra, tmp_path)
        content = (tmp_path / "host_vars" / "dev-ws.yml").read_text()
        assert "instance_type: vm" in content
        assert "limits.cpu" in content
        assert "limits.memory" in content

    def test_default_type_is_lxc(self, sample_infra, tmp_path):  # Matrix: VM-005
        """Machine without explicit type defaults to lxc."""
        del sample_infra["domains"]["work"]["machines"]["dev-ws"]["type"]
        errors = validate(sample_infra)
        assert errors == []
        generate(sample_infra, tmp_path)
        content = (tmp_path / "host_vars" / "dev-ws.yml").read_text()
        assert "instance_type: lxc" in content


# -- GPU policy (ADR-018) -----------------------------------------------------


class TestGPUPolicy:
    def _add_gpu_machine(self, infra, domain, name, ip, via_flag=True):
        """Helper: add a GPU-enabled machine to infra."""
        machines = infra["domains"][domain]["machines"]
        if via_flag:
            machines[name] = {"type": "lxc", "ip": ip, "gpu": True}
        else:
            # GPU via profile device
            infra["domains"][domain].setdefault("profiles", {})
            infra["domains"][domain]["profiles"]["gpu-profile"] = {
                "devices": {"gpu0": {"type": "gpu", "gputype": "physical"}}
            }
            machines[name] = {"type": "lxc", "ip": ip, "profiles": ["default", "gpu-profile"]}

    def test_single_gpu_exclusive_ok(self, sample_infra):  # Matrix: GP-001
        """One GPU instance in exclusive mode (default) is valid."""
        self._add_gpu_machine(sample_infra, "work", "gpu-ws", "10.100.1.20")
        assert validate(sample_infra) == []

    def test_multiple_gpu_exclusive_error(self, sample_infra):  # Matrix: GP-002
        """Multiple GPU instances in exclusive mode triggers error."""
        self._add_gpu_machine(sample_infra, "anklume", "gpu-a", "10.100.0.20")
        self._add_gpu_machine(sample_infra, "work", "gpu-b", "10.100.1.20")
        errors = validate(sample_infra)
        assert any("GPU policy is 'exclusive'" in e for e in errors)
        assert any("gpu-a" in e and "gpu-b" in e for e in errors)

    def test_multiple_gpu_shared_no_error(self, sample_infra):  # Matrix: GP-003
        """Multiple GPU instances with shared policy passes validation."""
        sample_infra["global"]["gpu_policy"] = "shared"
        self._add_gpu_machine(sample_infra, "anklume", "gpu-a", "10.100.0.20")
        self._add_gpu_machine(sample_infra, "work", "gpu-b", "10.100.1.20")
        assert validate(sample_infra) == []

    def test_shared_gpu_warning(self, sample_infra):  # Matrix: GP-004
        """Shared GPU policy emits warning when multiple instances share GPU."""
        sample_infra["global"]["gpu_policy"] = "shared"
        self._add_gpu_machine(sample_infra, "anklume", "gpu-a", "10.100.0.20")
        self._add_gpu_machine(sample_infra, "work", "gpu-b", "10.100.1.20")
        warnings = get_warnings(sample_infra)
        assert any("shared" in w.lower() for w in warnings)

    def test_no_gpu_no_warning(self, sample_infra):  # Matrix: GP-005
        """No GPU instances produces no warnings."""
        assert get_warnings(sample_infra) == []

    def test_single_gpu_no_warning(self, sample_infra):  # Matrix: GP-006
        """Single GPU instance produces no warning even in shared mode."""
        sample_infra["global"]["gpu_policy"] = "shared"
        self._add_gpu_machine(sample_infra, "work", "gpu-ws", "10.100.1.20")
        assert get_warnings(sample_infra) == []

    def test_gpu_via_profile_device_detected(self, sample_infra):  # Matrix: GP-007, GP-2-001
        """GPU access via profile device is detected by exclusive policy."""
        self._add_gpu_machine(sample_infra, "anklume", "gpu-a", "10.100.0.20", via_flag=True)
        self._add_gpu_machine(sample_infra, "work", "gpu-b", "10.100.1.20", via_flag=False)
        errors = validate(sample_infra)
        assert any("GPU policy is 'exclusive'" in e for e in errors)

    def test_invalid_gpu_policy(self, sample_infra):  # Matrix: GP-008
        """Invalid gpu_policy value triggers error."""
        sample_infra["global"]["gpu_policy"] = "permissive"
        errors = validate(sample_infra)
        assert any("gpu_policy must be 'exclusive' or 'shared'" in e for e in errors)

    def test_default_gpu_policy_is_exclusive(self, sample_infra):  # Matrix: GP-009
        """Without gpu_policy in global, default is exclusive."""
        self._add_gpu_machine(sample_infra, "anklume", "gpu-a", "10.100.0.20")
        self._add_gpu_machine(sample_infra, "work", "gpu-b", "10.100.1.20")
        # No gpu_policy set, should default to exclusive and error
        errors = validate(sample_infra)
        assert any("GPU policy is 'exclusive'" in e for e in errors)


# -- firewall mode (Phase 11) -------------------------------------------------


class TestFirewallMode:
    def test_default_host_mode_valid(self, sample_infra):  # Matrix: FM-001
        """No firewall_mode set defaults to 'host' (valid)."""
        assert validate(sample_infra) == []

    def test_host_mode_valid(self, sample_infra):  # Matrix: FM-002
        """Explicit firewall_mode: host is valid."""
        sample_infra["global"]["firewall_mode"] = "host"
        assert validate(sample_infra) == []

    def test_vm_mode_valid(self, sample_infra):  # Matrix: FM-003
        """firewall_mode: vm is valid."""
        sample_infra["global"]["firewall_mode"] = "vm"
        assert validate(sample_infra) == []

    def test_invalid_mode_rejected(self, sample_infra):  # Matrix: FM-004
        """Invalid firewall_mode triggers error."""
        sample_infra["global"]["firewall_mode"] = "container"
        errors = validate(sample_infra)
        assert any("firewall_mode must be 'host' or 'vm'" in e for e in errors)


# -- firewall VM auto-creation (enrich_infra) ---------------------------------


class TestFirewallVMAutoCreation:
    def test_firewall_mode_vm_auto_creates_sys_firewall(self, sample_infra):  # Matrix: FM-005
        """firewall_mode: vm auto-creates sys-firewall in anklume domain."""
        sample_infra["global"]["firewall_mode"] = "vm"
        enrich_infra(sample_infra)
        admin_machines = sample_infra["domains"]["anklume"]["machines"]
        assert "sys-firewall" in admin_machines

    def test_firewall_mode_vm_auto_created_has_correct_ip(self, sample_infra):  # Matrix: FM-006
        """Auto-created sys-firewall gets IP <base_subnet>.<anklume_subnet_id>.253."""
        sample_infra["global"]["firewall_mode"] = "vm"
        enrich_infra(sample_infra)
        sys_fw = sample_infra["domains"]["anklume"]["machines"]["sys-firewall"]
        assert sys_fw["ip"] == "10.100.0.253"

    def test_firewall_mode_vm_auto_created_roles(self, sample_infra):  # Matrix: FM-007
        """Auto-created sys-firewall has base_system and firewall_router roles."""
        sample_infra["global"]["firewall_mode"] = "vm"
        enrich_infra(sample_infra)
        sys_fw = sample_infra["domains"]["anklume"]["machines"]["sys-firewall"]
        assert sys_fw["roles"] == ["base_system", "firewall_router"]

    def test_firewall_mode_vm_no_anklume_domain_error(self, sample_infra):  # Matrix: FM-008
        """firewall_mode: vm without anklume domain exits with error."""
        sample_infra["global"]["firewall_mode"] = "vm"
        del sample_infra["domains"]["anklume"]
        with pytest.raises(SystemExit):
            enrich_infra(sample_infra)

    def test_firewall_mode_vm_user_override_not_overwritten(self, sample_infra):  # Matrix: FM-2-001
        """If user declares sys-firewall, enrich_infra does not overwrite it."""
        sample_infra["global"]["firewall_mode"] = "vm"
        sample_infra["domains"]["anklume"]["machines"]["sys-firewall"] = {
            "description": "My custom firewall",
            "type": "vm",
            "ip": "10.100.0.200",
            "roles": ["base_system"],
        }
        enrich_infra(sample_infra)
        sys_fw = sample_infra["domains"]["anklume"]["machines"]["sys-firewall"]
        # User's config should be preserved, not overwritten
        assert sys_fw["ip"] == "10.100.0.200"
        assert sys_fw["description"] == "My custom firewall"


# -- orphan protection ---------------------------------------------------------


class TestEphemeralOrphans:
    def test_orphan_protection(self, sample_infra, tmp_path):  # Matrix: PG-2-002, EL-2-002
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
    def test_detect_orphan_files(self, sample_infra, tmp_path):  # Matrix: PG-2-001
        generate(sample_infra, tmp_path)
        (tmp_path / "inventory" / "old-domain.yml").write_text("orphan")
        (tmp_path / "group_vars" / "old-domain.yml").write_text("orphan")
        (tmp_path / "host_vars" / "old-machine.yml").write_text("orphan")
        orphans = detect_orphans(sample_infra, tmp_path)
        assert len(orphans) == 3

    def test_no_false_positives(self, sample_infra, tmp_path):  # Matrix: PG-2-004
        generate(sample_infra, tmp_path)
        assert detect_orphans(sample_infra, tmp_path) == []

    def test_all_yml_not_orphan(self, sample_infra, tmp_path):  # Matrix: PG-2-003
        generate(sample_infra, tmp_path)
        orphans = detect_orphans(sample_infra, tmp_path)
        assert not any("all.yml" in str(o) for o in orphans)


# -- privileged LXC policy (ADR-020) ------------------------------------------


class TestPrivilegedPolicy:
    """Test security.privileged validation based on vm_nested context."""

    def _make_privileged(self, infra, machine="admin-ctrl"):
        """Set security.privileged: true on a machine."""
        for domain in infra["domains"].values():
            machines = domain.get("machines") or {}
            if machine in machines:
                machines[machine].setdefault("config", {})
                machines[machine]["config"]["security.privileged"] = "true"
                return
        raise KeyError(f"Machine {machine} not found")

    def test_privileged_lxc_rejected_when_vm_nested_false(self, sample_infra, monkeypatch):  # Matrix: PP-001
        """Privileged LXC is an error when vm_nested=false."""
        monkeypatch.setattr(gen_mod, "_read_vm_nested", lambda: False)
        monkeypatch.setattr(gen_mod, "_read_yolo", lambda: False)
        self._make_privileged(sample_infra)
        errors = validate(sample_infra)
        assert any("security.privileged=true on LXC is forbidden" in e for e in errors)

    def test_privileged_lxc_allowed_when_vm_nested_true(self, sample_infra, monkeypatch):  # Matrix: PP-002
        """Privileged LXC is allowed when vm_nested=true."""
        monkeypatch.setattr(gen_mod, "_read_vm_nested", lambda: True)
        monkeypatch.setattr(gen_mod, "_read_yolo", lambda: False)
        self._make_privileged(sample_infra)
        errors = validate(sample_infra)
        assert not any("privileged" in e.lower() for e in errors)

    def test_privileged_lxc_allowed_when_vm_nested_none(self, sample_infra, monkeypatch):  # Matrix: PP-003
        """When /etc/anklume/vm_nested does not exist, no enforcement."""
        monkeypatch.setattr(gen_mod, "_read_vm_nested", lambda: None)
        monkeypatch.setattr(gen_mod, "_read_yolo", lambda: False)
        self._make_privileged(sample_infra)
        errors = validate(sample_infra)
        assert not any("privileged" in e.lower() for e in errors)

    def test_privileged_vm_always_allowed(self, sample_infra, monkeypatch):  # Matrix: PP-004
        """VMs can always have security.privileged (it's kernel-isolated)."""
        monkeypatch.setattr(gen_mod, "_read_vm_nested", lambda: False)
        monkeypatch.setattr(gen_mod, "_read_yolo", lambda: False)
        sample_infra["domains"]["anklume"]["machines"]["admin-ctrl"]["type"] = "vm"
        self._make_privileged(sample_infra)
        errors = validate(sample_infra)
        assert not any("privileged" in e.lower() for e in errors)

    def test_yolo_bypasses_privileged_error(self, sample_infra, monkeypatch):  # Matrix: PP-006, PP-2-001
        """YOLO mode turns privileged error into warning."""
        monkeypatch.setattr(gen_mod, "_read_vm_nested", lambda: False)
        monkeypatch.setattr(gen_mod, "_read_yolo", lambda: True)
        self._make_privileged(sample_infra)
        errors = validate(sample_infra)
        assert not any("privileged" in e.lower() for e in errors)
        warnings = get_warnings(sample_infra)
        assert any("YOLO" in w for w in warnings)

    def test_non_privileged_lxc_no_error(self, sample_infra, monkeypatch):  # Matrix: PP-005
        """Non-privileged LXC is always fine, even with vm_nested=false."""
        monkeypatch.setattr(gen_mod, "_read_vm_nested", lambda: False)
        monkeypatch.setattr(gen_mod, "_read_yolo", lambda: False)
        errors = validate(sample_infra)
        assert not any("privileged" in e.lower() for e in errors)


# -- network policies (ADR-021) -----------------------------------------------


class TestNetworkPolicies:
    """Test network_policies validation and generation."""

    def _add_policies(self, infra, policies):
        infra["network_policies"] = policies

    def test_valid_domain_to_domain_policy(self, sample_infra):  # Matrix: NP-001
        """Policy between two known domains is valid."""
        self._add_policies(sample_infra, [
            {"from": "anklume", "to": "work", "ports": [22], "protocol": "tcp"},
        ])
        errors = validate(sample_infra)
        assert not any("network_policies" in e for e in errors)

    def test_valid_machine_to_domain_policy(self, sample_infra):  # Matrix: NP-002
        """Policy from a machine to a domain is valid."""
        self._add_policies(sample_infra, [
            {"from": "admin-ctrl", "to": "work", "ports": [443]},
        ])
        errors = validate(sample_infra)
        assert not any("network_policies" in e for e in errors)

    def test_valid_host_keyword(self, sample_infra):  # Matrix: NP-003
        """'host' is a valid from/to reference."""
        self._add_policies(sample_infra, [
            {"from": "host", "to": "anklume", "ports": [22], "protocol": "tcp"},
        ])
        errors = validate(sample_infra)
        assert not any("network_policies" in e for e in errors)

    def test_valid_ports_all(self, sample_infra):  # Matrix: NP-004
        """ports: all is valid."""
        self._add_policies(sample_infra, [
            {"from": "anklume", "to": "work", "ports": "all"},
        ])
        errors = validate(sample_infra)
        assert not any("network_policies" in e for e in errors)

    def test_unknown_from_rejected(self, sample_infra):  # Matrix: NP-005
        """Unknown 'from' reference triggers error."""
        self._add_policies(sample_infra, [
            {"from": "nonexistent", "to": "anklume", "ports": [22]},
        ])
        errors = validate(sample_infra)
        assert any("from: nonexistent" in e for e in errors)

    def test_unknown_to_rejected(self, sample_infra):  # Matrix: NP-006
        """Unknown 'to' reference triggers error."""
        self._add_policies(sample_infra, [
            {"from": "anklume", "to": "nonexistent", "ports": [22]},
        ])
        errors = validate(sample_infra)
        assert any("to: nonexistent" in e for e in errors)

    def test_missing_from_field(self, sample_infra):  # Matrix: NP-007
        """Missing 'from' field triggers error."""
        self._add_policies(sample_infra, [
            {"to": "anklume", "ports": [22]},
        ])
        errors = validate(sample_infra)
        assert any("missing 'from'" in e for e in errors)

    def test_missing_to_field(self, sample_infra):  # Matrix: NP-008
        """Missing 'to' field triggers error."""
        self._add_policies(sample_infra, [
            {"from": "anklume", "ports": [22]},
        ])
        errors = validate(sample_infra)
        assert any("missing 'to'" in e for e in errors)

    def test_invalid_port_number(self, sample_infra):  # Matrix: NP-009
        """Port out of range triggers error."""
        self._add_policies(sample_infra, [
            {"from": "anklume", "to": "work", "ports": [99999]},
        ])
        errors = validate(sample_infra)
        assert any("invalid port" in e for e in errors)

    def test_invalid_port_type(self, sample_infra):  # Matrix: NP-010
        """Non-list non-'all' ports triggers error."""
        self._add_policies(sample_infra, [
            {"from": "anklume", "to": "work", "ports": "tcp"},
        ])
        errors = validate(sample_infra)
        assert any("ports must be a list or 'all'" in e for e in errors)

    def test_invalid_protocol(self, sample_infra):  # Matrix: NP-011
        """Invalid protocol triggers error."""
        self._add_policies(sample_infra, [
            {"from": "anklume", "to": "work", "ports": [22], "protocol": "icmp"},
        ])
        errors = validate(sample_infra)
        assert any("protocol must be 'tcp' or 'udp'" in e for e in errors)

    def test_policies_in_group_vars_all(self, sample_infra, tmp_path):  # Matrix: NP-2-002
        """Network policies appear in group_vars/all.yml."""
        self._add_policies(sample_infra, [
            {"description": "Admin SSH", "from": "anklume", "to": "work",
             "ports": [22], "protocol": "tcp"},
        ])
        generate(sample_infra, tmp_path)
        content = (tmp_path / "group_vars" / "all.yml").read_text()
        assert "network_policies" in content
        assert "Admin SSH" in content

    def test_no_policies_no_key_in_all(self, sample_infra, tmp_path):  # Matrix: NP-2-003
        """Without network_policies, the key is absent from group_vars/all.yml."""
        generate(sample_infra, tmp_path)
        content = (tmp_path / "group_vars" / "all.yml").read_text()
        assert "network_policies" not in content

    def test_bidirectional_valid(self, sample_infra):  # Matrix: NP-2-001
        """bidirectional: true is accepted."""
        self._add_policies(sample_infra, [
            {"from": "anklume", "to": "work", "ports": "all", "bidirectional": True},
        ])
        errors = validate(sample_infra)
        assert not any("network_policies" in e for e in errors)

    def test_empty_policies_valid(self, sample_infra):  # Matrix: NP-012
        """Empty network_policies list is valid."""
        self._add_policies(sample_infra, [])
        errors = validate(sample_infra)
        assert not any("network_policies" in e for e in errors)


# -- infra/ directory support (ADR-030) ----------------------------------------


class TestInfraDirectory:
    """Test loading infra from a directory structure."""

    def _create_infra_dir(self, tmp_path, sample_infra):
        """Create infra/ directory structure from sample_infra."""
        infra_dir = tmp_path / "infra"
        infra_dir.mkdir()
        domains_dir = infra_dir / "domains"
        domains_dir.mkdir()

        # base.yml
        base = {
            "project_name": sample_infra["project_name"],
            "global": sample_infra["global"],
        }
        (infra_dir / "base.yml").write_text(yaml.dump(base, sort_keys=False))

        # domains/*.yml
        for dname, dconfig in sample_infra.get("domains", {}).items():
            (domains_dir / f"{dname}.yml").write_text(
                yaml.dump({dname: dconfig}, sort_keys=False)
            )

        # policies.yml (if any)
        if "network_policies" in sample_infra:
            (infra_dir / "policies.yml").write_text(
                yaml.dump({"network_policies": sample_infra["network_policies"]}, sort_keys=False)
            )

        return infra_dir

    def test_load_from_directory(self, sample_infra, tmp_path):  # Matrix: ID-001
        """Loading from infra/ directory produces same structure as single file."""
        infra_dir = self._create_infra_dir(tmp_path, sample_infra)
        result = load_infra(infra_dir)
        assert result["project_name"] == sample_infra["project_name"]
        assert "anklume" in result["domains"]
        assert "work" in result["domains"]

    def test_directory_generates_same_output(self, sample_infra, tmp_path):  # Matrix: ID-002
        """Directory mode and file mode produce identical generated files."""
        # Generate from single file
        out_file = tmp_path / "out_file"
        out_file.mkdir()
        generate(sample_infra, out_file)

        # Generate from directory
        infra_dir = self._create_infra_dir(tmp_path, sample_infra)
        dir_infra = load_infra(infra_dir)
        out_dir = tmp_path / "out_dir"
        out_dir.mkdir()
        generate(dir_infra, out_dir)

        # Compare outputs
        file_outputs = {
            str(f.relative_to(out_file)): f.read_text()
            for f in out_file.rglob("*.yml")
        }
        dir_outputs = {
            str(f.relative_to(out_dir)): f.read_text()
            for f in out_dir.rglob("*.yml")
        }
        assert file_outputs == dir_outputs

    def test_directory_with_policies(self, sample_infra, tmp_path):  # Matrix: ID-003
        """policies.yml is merged from infra/ directory."""
        sample_infra["network_policies"] = [
            {"from": "anklume", "to": "work", "ports": [22], "protocol": "tcp"},
        ]
        infra_dir = self._create_infra_dir(tmp_path, sample_infra)
        result = load_infra(infra_dir)
        assert "network_policies" in result
        assert len(result["network_policies"]) == 1

    def test_directory_missing_base_yml_exits(self, tmp_path):  # Matrix: ID-004
        """Missing base.yml triggers exit."""
        infra_dir = tmp_path / "infra"
        infra_dir.mkdir()
        with pytest.raises(SystemExit):
            load_infra(infra_dir)

    def test_load_autodetects_file(self, sample_infra, tmp_path):  # Matrix: ID-005
        """load_infra('infra.yml') works when file exists."""
        p = tmp_path / "infra.yml"
        p.write_text(yaml.dump(sample_infra, sort_keys=False))
        result = load_infra(p)
        assert result["project_name"] == "test-infra"

    def test_load_autodetects_dir(self, sample_infra, tmp_path):  # Matrix: ID-006
        """load_infra('infra') works when directory exists."""
        infra_dir = self._create_infra_dir(tmp_path, sample_infra)
        # Load using the directory path directly
        result = load_infra(infra_dir)
        assert result["project_name"] == "test-infra"

    def test_domains_sorted_alphabetically(self, sample_infra, tmp_path):  # Matrix: ID-007
        """Domain files are loaded in alphabetical order."""
        infra_dir = self._create_infra_dir(tmp_path, sample_infra)
        result = load_infra(infra_dir)
        # Both anklume and work should be present regardless of file order
        assert set(result["domains"]) == {"anklume", "work"}

    def test_empty_domains_dir(self, sample_infra, tmp_path):  # Matrix: ID-008
        """Empty domains/ directory yields no domains."""
        infra_dir = tmp_path / "infra"
        infra_dir.mkdir()
        (infra_dir / "domains").mkdir()
        base = {"project_name": "test", "global": sample_infra["global"]}
        (infra_dir / "base.yml").write_text(yaml.dump(base, sort_keys=False))
        result = load_infra(infra_dir)
        assert result.get("domains", {}) == {}


# -- AI access policy (Phase 18a) -------------------------------------------


class TestAIAccessPolicy:
    """Test AI access policy validation (Phase 18a)."""

    def _make_ai_infra(self, sample_infra, policy="exclusive", default="work"):
        """Add ai-tools domain and AI access policy to infra."""
        sample_infra["domains"]["ai-tools"] = {
            "description": "AI services",
            "subnet_id": 10,
            "machines": {
                "ai-ollama": {"type": "lxc", "ip": "10.100.10.10"},
            },
        }
        sample_infra["global"]["ai_access_policy"] = policy
        if default:
            sample_infra["global"]["ai_access_default"] = default

    def test_valid_exclusive_config(self, sample_infra):  # Matrix: AA-001
        """Exclusive AI access with valid default domain passes validation."""
        self._make_ai_infra(sample_infra)
        errors = validate(sample_infra)
        assert not any("ai_access" in e for e in errors)

    def test_missing_default_with_exclusive(self, sample_infra):  # Matrix: AA-002
        """Exclusive mode without ai_access_default is an error."""
        self._make_ai_infra(sample_infra, default=None)
        errors = validate(sample_infra)
        assert any("ai_access_default is required" in e for e in errors)

    def test_default_references_unknown_domain(self, sample_infra):  # Matrix: AA-003
        """ai_access_default referencing nonexistent domain is an error."""
        self._make_ai_infra(sample_infra, default="nonexistent")
        errors = validate(sample_infra)
        assert any("not a known domain" in e for e in errors)

    def test_default_cannot_be_ai_tools(self, sample_infra):  # Matrix: AA-004
        """ai_access_default cannot be 'ai-tools' itself."""
        self._make_ai_infra(sample_infra, default="ai-tools")
        errors = validate(sample_infra)
        assert any("cannot be 'ai-tools'" in e for e in errors)

    def test_multiple_ai_tools_policies_error(self, sample_infra):  # Matrix: AA-005
        """More than one network_policy targeting ai-tools is an error in exclusive mode."""
        self._make_ai_infra(sample_infra)
        sample_infra["network_policies"] = [
            {"from": "work", "to": "ai-tools", "ports": "all"},
            {"from": "anklume", "to": "ai-tools", "ports": [8080]},
        ]
        errors = validate(sample_infra)
        assert any("2 network_policies target ai-tools" in e for e in errors)

    def test_auto_creation_of_policy(self, sample_infra):  # Matrix: AA-2-001
        """Exclusive mode auto-creates a network policy if none targets ai-tools."""
        self._make_ai_infra(sample_infra)
        enrich_infra(sample_infra)
        policies = sample_infra.get("network_policies", [])
        assert any(p.get("to") == "ai-tools" for p in policies)

    def test_auto_creation_skipped_when_policy_exists(self, sample_infra):  # Matrix: AA-2-002
        """Auto-creation is skipped when a policy already targets ai-tools."""
        self._make_ai_infra(sample_infra)
        sample_infra["network_policies"] = [
            {"from": "work", "to": "ai-tools", "ports": "all"},
        ]
        enrich_infra(sample_infra)
        ai_policies = [p for p in sample_infra["network_policies"] if p.get("to") == "ai-tools"]
        assert len(ai_policies) == 1

    def test_open_mode_unchanged(self, sample_infra):  # Matrix: AA-006
        """Open mode (default) has no AI-specific validation."""
        errors = validate(sample_infra)
        assert not any("ai_access" in e for e in errors)

    def test_no_ai_tools_domain_error(self, sample_infra):  # Matrix: AA-007
        """Exclusive mode without ai-tools domain is an error."""
        sample_infra["global"]["ai_access_policy"] = "exclusive"
        sample_infra["global"]["ai_access_default"] = "work"
        errors = validate(sample_infra)
        assert any("no 'ai-tools' domain" in e for e in errors)

    def test_invalid_ai_access_policy_value(self, sample_infra):  # Matrix: AA-008
        """Invalid ai_access_policy value triggers error."""
        sample_infra["global"]["ai_access_policy"] = "restricted"
        errors = validate(sample_infra)
        assert any("ai_access_policy must be 'exclusive' or 'open'" in e for e in errors)

    def test_single_policy_targeting_ai_tools_ok(self, sample_infra):  # Matrix: AA-009
        """Exactly one network_policy targeting ai-tools is allowed in exclusive mode."""
        self._make_ai_infra(sample_infra)
        sample_infra["network_policies"] = [
            {"from": "work", "to": "ai-tools", "ports": "all"},
        ]
        errors = validate(sample_infra)
        assert not any("network_policies target ai-tools" in e for e in errors)


# -- image management ----------------------------------------------------------


class TestImageManagement:
    """Test image extraction and generation."""

    def test_extract_default_image(self, sample_infra):  # Matrix: IM-001
        """Default os_image appears in extracted image list."""
        from generate import extract_all_images
        images = extract_all_images(sample_infra)
        assert "images:debian/13" in images

    def test_extract_custom_image(self, sample_infra):  # Matrix: IM-002
        """Machine with custom os_image is included in image list."""
        from generate import extract_all_images
        sample_infra["domains"]["work"]["machines"]["dev-ws"]["os_image"] = "images:ubuntu/24.04"
        images = extract_all_images(sample_infra)
        assert "images:ubuntu/24.04" in images

    def test_extract_deduplicated(self, sample_infra):  # Matrix: IM-003
        """Multiple machines with same image produce single entry."""
        from generate import extract_all_images
        images = extract_all_images(sample_infra)
        assert images.count("images:debian/13") == 1

    def test_extract_no_images(self):  # Matrix: IM-004
        """Empty infra with no default_os_image returns empty list."""
        from generate import extract_all_images
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {"d": {"subnet_id": 0, "machines": {"m": {"type": "lxc"}}}},
        }
        images = extract_all_images(infra)
        assert images == []

    def test_extract_mixed_images(self, sample_infra):  # Matrix: IM-2-001
        """Default + custom images both appear, sorted."""
        from generate import extract_all_images
        sample_infra["domains"]["work"]["machines"]["dev-ws"]["os_image"] = "images:alpine/3.20"
        images = extract_all_images(sample_infra)
        assert "images:alpine/3.20" in images
        assert "images:debian/13" in images
        assert images == sorted(images)

    def test_images_in_all_yml(self, sample_infra, tmp_path):  # Matrix: IM-2-002
        """incus_all_images appears in group_vars/all.yml when images exist."""
        generate(sample_infra, tmp_path)
        content = (tmp_path / "group_vars" / "all.yml").read_text()
        assert "incus_all_images" in content
        assert "images:debian/13" in content

    def test_no_images_key_when_empty(self, tmp_path):  # Matrix: IM-004 (generation)
        """incus_all_images absent from all.yml when no images."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {"d": {"subnet_id": 0, "machines": {"m": {"type": "lxc"}}}},
        }
        generate(infra, tmp_path)
        content = (tmp_path / "group_vars" / "all.yml").read_text()
        assert "incus_all_images" not in content

    def test_images_vm_and_lxc_different(self, sample_infra):  # Matrix: IM-3-001
        """VM and LXC with different os_image produce all unique images."""
        from generate import extract_all_images
        sample_infra["domains"]["work"]["machines"]["dev-ws"]["os_image"] = "images:ubuntu/24.04"
        sample_infra["domains"]["anklume"]["machines"]["admin-ctrl"]["type"] = "vm"
        sample_infra["domains"]["anklume"]["machines"]["admin-ctrl"]["os_image"] = "images:debian/13/cloud"
        images = extract_all_images(sample_infra)
        assert len(images) == 2
        assert "images:ubuntu/24.04" in images
        assert "images:debian/13/cloud" in images


# -- depth 2 interactions -----------------------------------------------------


class TestDepth2Interactions:
    """Cross-capability pairwise interaction tests."""

    def test_ephemeral_domain_inheritance(self, sample_infra, tmp_path):  # Matrix: DL-2-002
        """Machine without explicit ephemeral inherits domain ephemeral: true."""
        sample_infra["domains"]["anklume"]["ephemeral"] = True
        # admin-ctrl has no explicit ephemeral -> inherits True
        generate(sample_infra, tmp_path)
        content = (tmp_path / "host_vars" / "admin-ctrl.yml").read_text()
        assert "instance_ephemeral: true" in content

    def test_vm_with_profiles(self, sample_infra, tmp_path):  # Matrix: VM-2-002
        """VM with domain-level profiles generates correct host_vars."""
        sample_infra["domains"]["work"]["profiles"] = {
            "vm-resources": {
                "config": {"limits.cpu": "4", "limits.memory": "4GiB"},
            },
        }
        sample_infra["domains"]["work"]["machines"]["dev-ws"]["type"] = "vm"
        sample_infra["domains"]["work"]["machines"]["dev-ws"]["profiles"] = ["default", "vm-resources"]
        errors = validate(sample_infra)
        assert errors == []
        generate(sample_infra, tmp_path)
        content = (tmp_path / "host_vars" / "dev-ws.yml").read_text()
        assert "instance_type: vm" in content
        assert "vm-resources" in content

    def test_intra_domain_policy(self, sample_infra):  # Matrix: NP-2-004
        """Policy between a domain and a machine within it is valid."""
        sample_infra["network_policies"] = [
            {"from": "anklume", "to": "admin-ctrl", "ports": [22], "protocol": "tcp"},
        ]
        errors = validate(sample_infra)
        assert not any("network_policies" in e for e in errors)

    def test_privileged_vm_always_allowed(self, sample_infra, monkeypatch):  # Matrix: PP-2-002
        """Privileged VM is allowed even when vm_nested=false."""
        monkeypatch.setattr(gen_mod, "_read_vm_nested", lambda: False)
        monkeypatch.setattr(gen_mod, "_read_yolo", lambda: False)
        sample_infra["domains"]["anklume"]["machines"]["admin-ctrl"]["type"] = "vm"
        sample_infra["domains"]["anklume"]["machines"]["admin-ctrl"].setdefault("config", {})
        sample_infra["domains"]["anklume"]["machines"]["admin-ctrl"]["config"]["security.privileged"] = "true"
        errors = validate(sample_infra)
        assert not any("privileged" in e.lower() for e in errors)

    def test_firewall_vm_with_network_policies(self, sample_infra):  # Matrix: FM-2-002
        """firewall_mode: vm and network_policies validate independently."""
        sample_infra["global"]["firewall_mode"] = "vm"
        sample_infra["network_policies"] = [
            {"from": "anklume", "to": "work", "ports": [22], "protocol": "tcp"},
        ]
        errors = validate(sample_infra)
        assert errors == []

    def test_gpu_shared_with_policies(self, sample_infra):  # Matrix: GP-2-002
        """GPU policy and network policies validate independently."""
        sample_infra["global"]["gpu_policy"] = "shared"
        sample_infra["domains"]["anklume"]["machines"]["gpu-a"] = {
            "type": "lxc", "ip": "10.100.0.20", "gpu": True,
        }
        sample_infra["domains"]["work"]["machines"]["gpu-b"] = {
            "type": "lxc", "ip": "10.100.1.20", "gpu": True,
        }
        sample_infra["network_policies"] = [
            {"from": "anklume", "to": "work", "ports": "all"},
        ]
        errors = validate(sample_infra)
        assert errors == []
        warnings = get_warnings(sample_infra)
        assert any("shared" in w.lower() for w in warnings)

    def test_shared_gpu_warning_with_policies(self, sample_infra):  # Matrix: GP-2-003
        """Shared GPU warning and network_policies validate correctly together."""
        sample_infra["global"]["gpu_policy"] = "shared"
        sample_infra["domains"]["anklume"]["machines"]["gpu-a"] = {
            "type": "lxc", "ip": "10.100.0.20", "gpu": True,
        }
        sample_infra["domains"]["work"]["machines"]["gpu-b"] = {
            "type": "lxc", "ip": "10.100.1.20", "gpu": True,
        }
        sample_infra["network_policies"] = [
            {"from": "anklume", "to": "work", "ports": [8080], "protocol": "tcp"},
        ]
        errors = validate(sample_infra)
        assert errors == []
        warnings = get_warnings(sample_infra)
        assert any("shared" in w.lower() for w in warnings)

    def test_two_domains_same_machine_pattern(self, sample_infra, tmp_path):  # Matrix: DL-2-005
        """Two domains generate correct files without collision."""
        sample_infra["domains"]["work"]["machines"]["work-extra"] = {
            "type": "lxc", "ip": "10.100.1.20",
        }
        errors = validate(sample_infra)
        assert errors == []
        generate(sample_infra, tmp_path)
        assert (tmp_path / "host_vars" / "admin-ctrl.yml").exists()
        assert (tmp_path / "host_vars" / "dev-ws.yml").exists()
        assert (tmp_path / "host_vars" / "work-extra.yml").exists()
        # Verify IPs are in correct subnets
        admin_inv = (tmp_path / "inventory" / "anklume.yml").read_text()
        assert "10.100.0.10" in admin_inv
        work_inv = (tmp_path / "inventory" / "work.yml").read_text()
        assert "10.100.1.10" in work_inv
        assert "10.100.1.20" in work_inv

    def test_directory_with_policies_and_domains(self, sample_infra, tmp_path):  # Matrix: ID-2-001
        """Directory format correctly merges domains and policies."""
        sample_infra["network_policies"] = [
            {"from": "anklume", "to": "work", "ports": [22], "protocol": "tcp"},
        ]
        infra_dir = tmp_path / "infra"
        infra_dir.mkdir()
        (infra_dir / "domains").mkdir()
        base = {"project_name": sample_infra["project_name"], "global": sample_infra["global"]}
        (infra_dir / "base.yml").write_text(yaml.dump(base, sort_keys=False))
        for dname, dconfig in sample_infra["domains"].items():
            (infra_dir / "domains" / f"{dname}.yml").write_text(
                yaml.dump({dname: dconfig}, sort_keys=False)
            )
        (infra_dir / "policies.yml").write_text(
            yaml.dump({"network_policies": sample_infra["network_policies"]}, sort_keys=False)
        )
        result = load_infra(infra_dir)
        assert "anklume" in result["domains"]
        assert "work" in result["domains"]
        assert len(result["network_policies"]) == 1

    def test_directory_with_firewall_vm(self, sample_infra, tmp_path):  # Matrix: ID-2-002
        """Directory format works with firewall_mode: vm auto-creation."""
        sample_infra["global"]["firewall_mode"] = "vm"
        infra_dir = tmp_path / "infra"
        infra_dir.mkdir()
        (infra_dir / "domains").mkdir()
        base = {"project_name": sample_infra["project_name"], "global": sample_infra["global"]}
        (infra_dir / "base.yml").write_text(yaml.dump(base, sort_keys=False))
        for dname, dconfig in sample_infra["domains"].items():
            (infra_dir / "domains" / f"{dname}.yml").write_text(
                yaml.dump({dname: dconfig}, sort_keys=False)
            )
        result = load_infra(infra_dir)
        errors = validate(result)
        assert errors == []
        enrich_infra(result)
        assert "sys-firewall" in result["domains"]["anklume"]["machines"]

    def test_ephemeral_orphan_unprotected(self, sample_infra, tmp_path):  # Matrix: EL-2-001
        """Orphan from ephemeral domain is unprotected."""
        generate(sample_infra, tmp_path)
        orphan = tmp_path / "host_vars" / "temp-machine.yml"
        orphan.write_text("instance_ephemeral: true\ninstance_name: temp-machine\n")
        orphans = detect_orphans(sample_infra, tmp_path)
        orphan_dict = {o[0].stem: o[1] for o in orphans}
        assert orphan_dict.get("temp-machine") is False  # not protected


# -- depth 3 interactions -----------------------------------------------------


class TestDepth3Interactions:
    """Three-way interaction tests (complex scenarios)."""

    def test_vm_gpu_firewall_vm(self, sample_infra):  # Matrix: DL-3-001, VM-3-001, FM-3-001
        """Domain + VM + GPU + firewall_mode=vm all coexist correctly."""
        sample_infra["global"]["firewall_mode"] = "vm"
        sample_infra["domains"]["work"]["machines"]["dev-ws"]["type"] = "vm"
        sample_infra["domains"]["work"]["machines"]["dev-ws"]["gpu"] = True
        errors = validate(sample_infra)
        assert errors == []
        enrich_infra(sample_infra)
        assert "sys-firewall" in sample_infra["domains"]["anklume"]["machines"]

    def test_three_domains_profiles_ephemeral_policies(self, sample_infra, tmp_path):  # Matrix: DL-3-002
        """3 domains, profiles, mixed ephemeral, network_policies all work together."""
        sample_infra["domains"]["perso"] = {
            "description": "Personal",
            "subnet_id": 2,
            "ephemeral": True,
            "machines": {
                "perso-desk": {"type": "lxc", "ip": "10.100.2.10"},
            },
        }
        sample_infra["domains"]["anklume"]["profiles"] = {
            "nesting": {"config": {"security.nesting": "true"}},
        }
        sample_infra["domains"]["anklume"]["machines"]["admin-ctrl"]["profiles"] = ["default", "nesting"]
        sample_infra["network_policies"] = [
            {"from": "anklume", "to": "work", "ports": [22], "protocol": "tcp"},
            {"from": "perso", "to": "work", "ports": "all"},
        ]
        errors = validate(sample_infra)
        assert errors == []
        generate(sample_infra, tmp_path)
        # Check ephemeral inheritance
        perso_hv = (tmp_path / "host_vars" / "perso-desk.yml").read_text()
        assert "instance_ephemeral: true" in perso_hv
        admin_hv = (tmp_path / "host_vars" / "admin-ctrl.yml").read_text()
        assert "instance_ephemeral: false" in admin_hv
        # Check policies in all.yml
        all_yml = (tmp_path / "group_vars" / "all.yml").read_text()
        assert "network_policies" in all_yml
        # Check 3 domains generated
        assert (tmp_path / "inventory" / "perso.yml").exists()

    def test_gpu_shared_ephemeral_override(self, sample_infra, tmp_path):  # Matrix: GP-3-001
        """GPU shared + ephemeral override work together."""
        sample_infra["global"]["gpu_policy"] = "shared"
        sample_infra["domains"]["anklume"]["ephemeral"] = True
        sample_infra["domains"]["anklume"]["machines"]["admin-ctrl"]["ephemeral"] = False
        sample_infra["domains"]["anklume"]["machines"]["admin-ctrl"]["gpu"] = True
        sample_infra["domains"]["work"]["machines"]["gpu-ws"] = {
            "type": "lxc", "ip": "10.100.1.20", "gpu": True,
        }
        errors = validate(sample_infra)
        assert errors == []
        warnings = get_warnings(sample_infra)
        assert any("shared" in w.lower() for w in warnings)
        generate(sample_infra, tmp_path)
        content = (tmp_path / "host_vars" / "admin-ctrl.yml").read_text()
        assert "instance_ephemeral: false" in content

    def test_privileged_gpu_exclusive_vm_nested_false(self, sample_infra, monkeypatch):  # Matrix: PP-3-001
        """Privileged LXC + GPU exclusive + vm_nested=false -> privileged error."""
        monkeypatch.setattr(gen_mod, "_read_vm_nested", lambda: False)
        monkeypatch.setattr(gen_mod, "_read_yolo", lambda: False)
        sample_infra["domains"]["anklume"]["machines"]["admin-ctrl"]["config"] = {
            "security.privileged": "true",
        }
        sample_infra["domains"]["anklume"]["machines"]["admin-ctrl"]["gpu"] = True
        errors = validate(sample_infra)
        assert any("security.privileged=true on LXC is forbidden" in e for e in errors)
        # GPU should be fine (exclusive, only 1 instance)
        assert not any("GPU policy" in e for e in errors)

    def test_policies_firewall_vm_gpu_shared(self, sample_infra):  # Matrix: NP-3-001
        """Multiple policies + firewall_mode: vm + GPU shared all coexist."""
        sample_infra["global"]["firewall_mode"] = "vm"
        sample_infra["global"]["gpu_policy"] = "shared"
        sample_infra["domains"]["anklume"]["machines"]["gpu-a"] = {
            "type": "lxc", "ip": "10.100.0.20", "gpu": True,
        }
        sample_infra["domains"]["work"]["machines"]["gpu-b"] = {
            "type": "lxc", "ip": "10.100.1.20", "gpu": True,
        }
        sample_infra["network_policies"] = [
            {"from": "anklume", "to": "work", "ports": [22], "protocol": "tcp"},
            {"from": "work", "to": "anklume", "ports": [443], "protocol": "tcp"},
        ]
        errors = validate(sample_infra)
        assert errors == []
        enrich_infra(sample_infra)
        assert "sys-firewall" in sample_infra["domains"]["anklume"]["machines"]

    def test_ephemeral_gpu_policies(self, sample_infra, tmp_path):  # Matrix: EL-3-001
        """Mixed ephemeral + GPU + network_policies all independent."""
        sample_infra["domains"]["anklume"]["ephemeral"] = True
        sample_infra["domains"]["anklume"]["machines"]["admin-ctrl"]["gpu"] = True
        sample_infra["network_policies"] = [
            {"from": "anklume", "to": "work", "ports": "all"},
        ]
        errors = validate(sample_infra)
        assert errors == []
        generate(sample_infra, tmp_path)
        content = (tmp_path / "host_vars" / "admin-ctrl.yml").read_text()
        assert "instance_ephemeral: true" in content

    def test_directory_policies_gpu_firewall(self, sample_infra, tmp_path):  # Matrix: ID-3-001
        """Directory format + policies + GPU + firewall all work identically to single file."""
        sample_infra["global"]["firewall_mode"] = "vm"
        sample_infra["domains"]["anklume"]["machines"]["admin-ctrl"]["gpu"] = True
        sample_infra["network_policies"] = [
            {"from": "anklume", "to": "work", "ports": [22], "protocol": "tcp"},
        ]

        # Generate from single-file
        out_file = tmp_path / "out_file"
        out_file.mkdir()
        enrich_infra(sample_infra)
        generate(sample_infra, out_file)

        # Reset enrichment for directory test
        if "sys-firewall" in sample_infra["domains"]["anklume"]["machines"]:
            del sample_infra["domains"]["anklume"]["machines"]["sys-firewall"]

        # Create directory format
        infra_dir = tmp_path / "infra"
        infra_dir.mkdir()
        (infra_dir / "domains").mkdir()
        base = {"project_name": sample_infra["project_name"], "global": sample_infra["global"]}
        (infra_dir / "base.yml").write_text(yaml.dump(base, sort_keys=False))
        for dname, dconfig in sample_infra["domains"].items():
            (infra_dir / "domains" / f"{dname}.yml").write_text(
                yaml.dump({dname: dconfig}, sort_keys=False)
            )
        (infra_dir / "policies.yml").write_text(
            yaml.dump({"network_policies": sample_infra["network_policies"]}, sort_keys=False)
        )

        dir_infra = load_infra(infra_dir)
        enrich_infra(dir_infra)
        out_dir = tmp_path / "out_dir"
        out_dir.mkdir()
        generate(dir_infra, out_dir)

        # Compare (both should have sys-firewall and all files)
        file_keys = {str(f.relative_to(out_file)) for f in out_file.rglob("*.yml")}
        dir_keys = {str(f.relative_to(out_dir)) for f in out_dir.rglob("*.yml")}
        assert file_keys == dir_keys

    def test_ai_exclusive_gpu_firewall_vm(self, sample_infra):  # Matrix: AA-3-001
        """Exclusive AI + GPU exclusive + firewall_mode=vm all coexist."""
        sample_infra["global"]["firewall_mode"] = "vm"
        sample_infra["global"]["ai_access_policy"] = "exclusive"
        sample_infra["global"]["ai_access_default"] = "work"
        sample_infra["domains"]["ai-tools"] = {
            "description": "AI services",
            "subnet_id": 10,
            "machines": {
                "ai-ollama": {"type": "lxc", "ip": "10.100.10.10", "gpu": True},
            },
        }
        errors = validate(sample_infra)
        assert errors == []
        enrich_infra(sample_infra)
        # sys-firewall auto-created
        assert "sys-firewall" in sample_infra["domains"]["anklume"]["machines"]
        # AI policy auto-created
        policies = sample_infra.get("network_policies", [])
        assert any(p.get("to") == "ai-tools" for p in policies)

    def test_round_trip_generation(self, sample_infra, tmp_path):  # Matrix: PG-3-001
        """Generate -> add user content -> add domain -> regenerate preserves content."""
        generate(sample_infra, tmp_path)
        # Add user content outside managed section
        gv = tmp_path / "group_vars" / "anklume.yml"
        gv.write_text(gv.read_text() + "\ncustom_admin_var: preserved\n")
        hv = tmp_path / "host_vars" / "admin-ctrl.yml"
        hv.write_text(hv.read_text() + "\ncustom_host_var: also_preserved\n")
        # Add a new domain
        sample_infra["domains"]["lab"] = {
            "description": "Lab",
            "subnet_id": 5,
            "machines": {
                "lab-pc": {"type": "lxc", "ip": "10.100.5.10"},
            },
        }
        generate(sample_infra, tmp_path)
        # User content preserved
        assert "custom_admin_var: preserved" in gv.read_text()
        assert "custom_host_var: also_preserved" in hv.read_text()
        # New domain created
        assert (tmp_path / "inventory" / "lab.yml").exists()
        assert (tmp_path / "host_vars" / "lab-pc.yml").exists()

    def test_orphan_protection_with_clean(self, sample_infra, tmp_path):  # Matrix: PG-3-002
        """Protected orphans kept, ephemeral orphans cleaned."""
        generate(sample_infra, tmp_path)
        # Protected orphan
        (tmp_path / "host_vars" / "old-protected.yml").write_text(
            "instance_ephemeral: false\ninstance_name: old-protected\n"
        )
        # Ephemeral orphan
        (tmp_path / "host_vars" / "old-ephemeral.yml").write_text(
            "instance_ephemeral: true\ninstance_name: old-ephemeral\n"
        )
        orphans = detect_orphans(sample_infra, tmp_path)
        assert len(orphans) == 2
        orphan_dict = {o[0].stem: o[1] for o in orphans}
        assert orphan_dict["old-protected"] is True
        assert orphan_dict["old-ephemeral"] is False


# -- edge cases and robustness ------------------------------------------------


class TestEdgeCases:
    """Additional edge cases beyond the matrix."""

    def test_large_infra_10_domains(self, sample_infra, tmp_path):
        """10+ domains with machines generate correctly."""
        for i in range(2, 12):
            sample_infra["domains"][f"domain-{i}"] = {
                "description": f"Domain {i}",
                "subnet_id": i,
                "machines": {
                    f"machine-{i}": {"type": "lxc", "ip": f"10.100.{i}.10"},
                },
            }
        errors = validate(sample_infra)
        assert errors == []
        generate(sample_infra, tmp_path)
        assert len(list((tmp_path / "inventory").glob("*.yml"))) == 12
        assert len(list((tmp_path / "host_vars").glob("*.yml"))) == 12

    def test_base_subnet_172(self, sample_infra, tmp_path):
        """Non-standard base_subnet (172.16) works correctly."""
        sample_infra["global"]["base_subnet"] = "172.16"
        sample_infra["domains"]["anklume"]["machines"]["admin-ctrl"]["ip"] = "172.16.0.10"
        sample_infra["domains"]["work"]["machines"]["dev-ws"]["ip"] = "172.16.1.10"
        errors = validate(sample_infra)
        assert errors == []
        generate(sample_infra, tmp_path)
        content = (tmp_path / "group_vars" / "anklume.yml").read_text()
        assert "172.16.0.0/24" in content

    def test_machine_with_storage_volumes(self, sample_infra, tmp_path):
        """Machine with storage_volumes generates instance_storage_volumes in host_vars."""
        sample_infra["domains"]["anklume"]["machines"]["admin-ctrl"]["storage_volumes"] = {
            "data": {"pool": "default", "path": "/data", "size": "10GiB"},
        }
        generate(sample_infra, tmp_path)
        content = (tmp_path / "host_vars" / "admin-ctrl.yml").read_text()
        assert "instance_storage_volumes" in content
        assert "data" in content

    def test_machine_with_roles_list(self, sample_infra, tmp_path):
        """Machine roles list appears in host_vars."""
        sample_infra["domains"]["anklume"]["machines"]["admin-ctrl"]["roles"] = [
            "base_system", "ollama_server", "stt_server",
        ]
        generate(sample_infra, tmp_path)
        content = (tmp_path / "host_vars" / "admin-ctrl.yml").read_text()
        assert "ollama_server" in content
        assert "stt_server" in content

    def test_empty_machines_dict(self, sample_infra, tmp_path):
        """Domain with empty machines dict generates no host_vars."""
        sample_infra["domains"]["anklume"]["machines"] = {}
        errors = validate(sample_infra)
        assert errors == []
        generate(sample_infra, tmp_path)
        assert not list((tmp_path / "host_vars").glob("admin-*.yml"))

    def test_gateway_convention(self, sample_infra, tmp_path):
        """Gateway is always .254 per subnet convention."""
        generate(sample_infra, tmp_path)
        for dname, domain in sample_infra["domains"].items():
            content = (tmp_path / "group_vars" / f"{dname}.yml").read_text()
            sid = domain["subnet_id"]
            expected_gw = f"10.100.{sid}.254"
            assert expected_gw in content

    def test_error_message_identifies_machines(self, sample_infra):
        """Duplicate IP error identifies both conflicting machines."""
        sample_infra["domains"]["work"]["machines"]["dev-ws"]["ip"] = "10.100.0.10"
        errors = validate(sample_infra)
        ip_errors = [e for e in errors if "IP 10.100.0.10" in e]
        assert len(ip_errors) > 0
        assert "admin-ctrl" in ip_errors[0]


# -- resource policy (ballooning/shares) --------------------------------------


class TestResourcePolicy:
    """Test resource_policy enrichment and validation."""

    HOST_16CPU_64G = {"cpu": 16, "memory_bytes": 64 * 1024**3}

    def _make_infra(self, policy=None, machines=None):
        """Create infra with resource_policy and optional machines."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "work": {
                    "subnet_id": 1,
                    "machines": machines or {
                        "m1": {"type": "lxc", "ip": "10.100.1.10"},
                        "m2": {"type": "lxc", "ip": "10.100.1.11"},
                        "m3": {"type": "lxc", "ip": "10.100.1.12"},
                    },
                },
            },
        }
        if policy is not None:
            infra["global"]["resource_policy"] = policy
        return infra

    def test_skip_when_absent(self, monkeypatch):
        """No resource_policy -> no enrichment."""
        monkeypatch.setattr(gen_mod, "_detect_host_resources", lambda: self.HOST_16CPU_64G)
        infra = self._make_infra()
        enrich_infra(infra)
        config = infra["domains"]["work"]["machines"]["m1"].get("config")
        assert config is None

    def test_proportional_equal_weights(self, monkeypatch):
        """3 machines with weight 1 each get equal shares."""
        monkeypatch.setattr(gen_mod, "_detect_host_resources", lambda: self.HOST_16CPU_64G)
        infra = self._make_infra(policy={})
        enrich_infra(infra)
        machines = infra["domains"]["work"]["machines"]
        m1_config = machines["m1"]["config"]
        m2_config = machines["m2"]["config"]
        m3_config = machines["m3"]["config"]
        # All 3 should get the same allocation
        assert m1_config["limits.memory"] == m2_config["limits.memory"]
        assert m1_config["limits.memory"] == m3_config["limits.memory"]
        # CPU allowance: 80% of 16 = 12.8 CPUs / 3 ≈ 4.27 -> 26% each
        assert "limits.cpu.allowance" in m1_config

    def test_proportional_different_weights(self, monkeypatch):
        """Machine with weight 3 gets 3x the share of weight 1."""
        monkeypatch.setattr(gen_mod, "_detect_host_resources", lambda: self.HOST_16CPU_64G)
        machines = {
            "heavy": {"type": "lxc", "ip": "10.100.1.10", "weight": 3},
            "light1": {"type": "lxc", "ip": "10.100.1.11"},
            "light2": {"type": "lxc", "ip": "10.100.1.12"},
        }
        infra = self._make_infra(policy={}, machines=machines)
        enrich_infra(infra)
        from generate import _parse_memory_value
        heavy_mem = _parse_memory_value(
            infra["domains"]["work"]["machines"]["heavy"]["config"]["limits.memory"]
        )
        light_mem = _parse_memory_value(
            infra["domains"]["work"]["machines"]["light1"]["config"]["limits.memory"]
        )
        assert heavy_mem > light_mem
        ratio = heavy_mem / light_mem
        assert 2.5 < ratio < 3.5

    def test_equal_mode(self, monkeypatch):
        """Mode equal gives all machines the same share regardless of weight."""
        monkeypatch.setattr(gen_mod, "_detect_host_resources", lambda: self.HOST_16CPU_64G)
        machines = {
            "heavy": {"type": "lxc", "ip": "10.100.1.10", "weight": 5},
            "light": {"type": "lxc", "ip": "10.100.1.11"},
        }
        infra = self._make_infra(policy={"mode": "equal"}, machines=machines)
        enrich_infra(infra)
        heavy_mem = infra["domains"]["work"]["machines"]["heavy"]["config"]["limits.memory"]
        light_mem = infra["domains"]["work"]["machines"]["light"]["config"]["limits.memory"]
        assert heavy_mem == light_mem

    def test_explicit_override_respected(self, monkeypatch):
        """Machine with explicit limits.cpu is not overwritten."""
        monkeypatch.setattr(gen_mod, "_detect_host_resources", lambda: self.HOST_16CPU_64G)
        machines = {
            "explicit": {
                "type": "lxc", "ip": "10.100.1.10",
                "config": {"limits.cpu": "4"},
            },
            "auto": {"type": "lxc", "ip": "10.100.1.11"},
        }
        infra = self._make_infra(policy={}, machines=machines)
        enrich_infra(infra)
        # Explicit CPU preserved
        assert infra["domains"]["work"]["machines"]["explicit"]["config"]["limits.cpu"] == "4"
        # Memory auto-allocated for explicit machine
        assert "limits.memory" in infra["domains"]["work"]["machines"]["explicit"]["config"]
        # Auto machine gets both
        auto_config = infra["domains"]["work"]["machines"]["auto"]["config"]
        assert "limits.cpu.allowance" in auto_config
        assert "limits.memory" in auto_config

    def test_cpu_mode_count(self, monkeypatch):
        """cpu_mode: count sets limits.cpu as vCPU count."""
        monkeypatch.setattr(gen_mod, "_detect_host_resources", lambda: self.HOST_16CPU_64G)
        infra = self._make_infra(
            policy={"cpu_mode": "count"},
            machines={"m1": {"type": "lxc", "ip": "10.100.1.10"}},
        )
        enrich_infra(infra)
        config = infra["domains"]["work"]["machines"]["m1"]["config"]
        assert "limits.cpu" in config
        assert "limits.cpu.allowance" not in config
        # 80% of 16 = 12.8, floor = 12
        assert config["limits.cpu"] == "12"

    def test_cpu_mode_allowance(self, monkeypatch):
        """cpu_mode: allowance sets limits.cpu.allowance as percentage."""
        monkeypatch.setattr(gen_mod, "_detect_host_resources", lambda: self.HOST_16CPU_64G)
        infra = self._make_infra(
            policy={"cpu_mode": "allowance"},
            machines={"m1": {"type": "lxc", "ip": "10.100.1.10"}},
        )
        enrich_infra(infra)
        config = infra["domains"]["work"]["machines"]["m1"]["config"]
        assert "limits.cpu.allowance" in config
        assert "limits.cpu" not in config
        assert config["limits.cpu.allowance"] == "80%"

    def test_memory_enforce_soft(self, monkeypatch):
        """memory_enforce: soft adds limits.memory.enforce: soft."""
        monkeypatch.setattr(gen_mod, "_detect_host_resources", lambda: self.HOST_16CPU_64G)
        infra = self._make_infra(policy={"memory_enforce": "soft"})
        enrich_infra(infra)
        config = infra["domains"]["work"]["machines"]["m1"]["config"]
        assert config.get("limits.memory.enforce") == "soft"

    def test_memory_enforce_hard(self, monkeypatch):
        """memory_enforce: hard does not add limits.memory.enforce."""
        monkeypatch.setattr(gen_mod, "_detect_host_resources", lambda: self.HOST_16CPU_64G)
        infra = self._make_infra(policy={"memory_enforce": "hard"})
        enrich_infra(infra)
        config = infra["domains"]["work"]["machines"]["m1"]["config"]
        assert "limits.memory.enforce" not in config

    def test_host_reserve_percentage(self, monkeypatch):
        """Custom host_reserve percentage changes available pool."""
        monkeypatch.setattr(gen_mod, "_detect_host_resources", lambda: self.HOST_16CPU_64G)
        infra = self._make_infra(
            policy={"host_reserve": {"cpu": "50%", "memory": "50%"}, "cpu_mode": "count"},
            machines={"m1": {"type": "lxc", "ip": "10.100.1.10"}},
        )
        enrich_infra(infra)
        config = infra["domains"]["work"]["machines"]["m1"]["config"]
        # 50% of 16 reserved = 8 available, single machine gets 8
        assert config["limits.cpu"] == "8"

    def test_overcommit_false_error(self, monkeypatch):
        """overcommit: false exits when total exceeds available."""
        monkeypatch.setattr(gen_mod, "_detect_host_resources", lambda: self.HOST_16CPU_64G)
        machines = {
            "explicit": {
                "type": "lxc", "ip": "10.100.1.10",
                "config": {"limits.cpu": "20", "limits.memory": "100GiB"},
            },
            "auto": {"type": "lxc", "ip": "10.100.1.11"},
        }
        infra = self._make_infra(
            policy={"overcommit": False, "cpu_mode": "count"}, machines=machines
        )
        with pytest.raises(SystemExit):
            enrich_infra(infra)

    def test_overcommit_true_no_error(self, monkeypatch, capsys):
        """overcommit: true allows exceeding available (prints warning)."""
        monkeypatch.setattr(gen_mod, "_detect_host_resources", lambda: self.HOST_16CPU_64G)
        machines = {
            "explicit": {
                "type": "lxc", "ip": "10.100.1.10",
                "config": {"limits.cpu": "20", "limits.memory": "100GiB"},
            },
            "auto": {"type": "lxc", "ip": "10.100.1.11"},
        }
        infra = self._make_infra(
            policy={"overcommit": True, "cpu_mode": "count"}, machines=machines
        )
        enrich_infra(infra)  # should not raise
        stderr = capsys.readouterr().err
        assert "overcommit" in stderr.lower() or "WARNING" in stderr

    def test_policy_true_uses_defaults(self, monkeypatch):
        """resource_policy: true treated as empty dict (all defaults)."""
        monkeypatch.setattr(gen_mod, "_detect_host_resources", lambda: self.HOST_16CPU_64G)
        infra = self._make_infra(
            policy=True,
            machines={"m1": {"type": "lxc", "ip": "10.100.1.10"}},
        )
        enrich_infra(infra)
        config = infra["domains"]["work"]["machines"]["m1"]["config"]
        assert "limits.cpu.allowance" in config
        assert "limits.memory" in config

    def test_validate_invalid_mode(self):
        """Invalid resource_policy.mode triggers validation error."""
        infra = self._make_infra(policy={"mode": "random"})
        errors = validate(infra)
        assert any("resource_policy.mode" in e for e in errors)

    def test_validate_invalid_cpu_mode(self):
        """Invalid resource_policy.cpu_mode triggers validation error."""
        infra = self._make_infra(policy={"cpu_mode": "shares"})
        errors = validate(infra)
        assert any("resource_policy.cpu_mode" in e for e in errors)

    def test_validate_invalid_memory_enforce(self):
        """Invalid resource_policy.memory_enforce triggers validation error."""
        infra = self._make_infra(policy={"memory_enforce": "rigid"})
        errors = validate(infra)
        assert any("resource_policy.memory_enforce" in e for e in errors)

    def test_validate_invalid_weight(self):
        """Non-positive weight triggers validation error."""
        infra = self._make_infra(machines={
            "m1": {"type": "lxc", "ip": "10.100.1.10", "weight": 0},
        })
        errors = validate(infra)
        assert any("weight must be a positive integer" in e for e in errors)

    def test_validate_weight_string(self):
        """String weight triggers validation error."""
        infra = self._make_infra(machines={
            "m1": {"type": "lxc", "ip": "10.100.1.10", "weight": "high"},
        })
        errors = validate(infra)
        assert any("weight must be a positive integer" in e for e in errors)

    def test_host_detection_failure_skips(self, monkeypatch, capsys):
        """If host detection fails, enrichment is skipped with warning."""
        monkeypatch.setattr(gen_mod, "_detect_host_resources", lambda: None)
        infra = self._make_infra(policy={})
        enrich_infra(infra)
        config = infra["domains"]["work"]["machines"]["m1"].get("config")
        assert config is None or "limits.memory" not in config
        stderr = capsys.readouterr().err
        assert "detect host resources" in stderr.lower()

    def test_memory_enforce_soft_on_explicit(self, monkeypatch):
        """memory_enforce: soft applies to machines with explicit limits.memory."""
        monkeypatch.setattr(gen_mod, "_detect_host_resources", lambda: self.HOST_16CPU_64G)
        machines = {
            "explicit": {
                "type": "lxc", "ip": "10.100.1.10",
                "config": {"limits.memory": "8GiB"},
            },
        }
        infra = self._make_infra(policy={"memory_enforce": "soft"}, machines=machines)
        enrich_infra(infra)
        config = infra["domains"]["work"]["machines"]["explicit"]["config"]
        assert config["limits.memory"] == "8GiB"
        assert config["limits.memory.enforce"] == "soft"

    def test_generated_host_vars_contain_limits(self, monkeypatch, tmp_path):
        """After enrichment, generated host_vars contain allocated limits."""
        monkeypatch.setattr(gen_mod, "_detect_host_resources", lambda: self.HOST_16CPU_64G)
        infra = self._make_infra(
            policy={"cpu_mode": "count"},
            machines={"m1": {"type": "lxc", "ip": "10.100.1.10"}},
        )
        enrich_infra(infra)
        generate(infra, tmp_path)
        content = (tmp_path / "host_vars" / "m1.yml").read_text()
        assert "limits.cpu" in content
        assert "limits.memory" in content


# -- boot autostart -----------------------------------------------------------


class TestBootAutostart:
    """Test boot_autostart and boot_priority validation and generation."""

    def test_boot_autostart_propagated(self, sample_infra, tmp_path):
        """boot_autostart: true generates instance_boot_autostart in host_vars."""
        sample_infra["domains"]["anklume"]["machines"]["admin-ctrl"]["boot_autostart"] = True
        generate(sample_infra, tmp_path)
        content = (tmp_path / "host_vars" / "admin-ctrl.yml").read_text()
        assert "instance_boot_autostart: true" in content

    def test_boot_autostart_false_propagated(self, sample_infra, tmp_path):
        """boot_autostart: false generates instance_boot_autostart: false."""
        sample_infra["domains"]["anklume"]["machines"]["admin-ctrl"]["boot_autostart"] = False
        generate(sample_infra, tmp_path)
        content = (tmp_path / "host_vars" / "admin-ctrl.yml").read_text()
        assert "instance_boot_autostart: false" in content

    def test_boot_autostart_omitted(self, sample_infra, tmp_path):
        """Omitted boot_autostart does not appear in host_vars."""
        generate(sample_infra, tmp_path)
        content = (tmp_path / "host_vars" / "admin-ctrl.yml").read_text()
        assert "instance_boot_autostart" not in content

    def test_boot_autostart_invalid_type(self, sample_infra):
        """Non-boolean boot_autostart triggers validation error."""
        sample_infra["domains"]["anklume"]["machines"]["admin-ctrl"]["boot_autostart"] = "yes"
        errors = validate(sample_infra)
        assert any("boot_autostart must be a boolean" in e for e in errors)

    def test_boot_priority_propagated(self, sample_infra, tmp_path):
        """boot_priority generates instance_boot_priority in host_vars."""
        sample_infra["domains"]["anklume"]["machines"]["admin-ctrl"]["boot_priority"] = 10
        generate(sample_infra, tmp_path)
        content = (tmp_path / "host_vars" / "admin-ctrl.yml").read_text()
        assert "instance_boot_priority: 10" in content

    def test_boot_priority_zero_valid(self, sample_infra):
        """boot_priority: 0 is valid."""
        sample_infra["domains"]["anklume"]["machines"]["admin-ctrl"]["boot_priority"] = 0
        errors = validate(sample_infra)
        assert not any("boot_priority" in e for e in errors)

    def test_boot_priority_100_valid(self, sample_infra):
        """boot_priority: 100 is valid."""
        sample_infra["domains"]["anklume"]["machines"]["admin-ctrl"]["boot_priority"] = 100
        errors = validate(sample_infra)
        assert not any("boot_priority" in e for e in errors)

    def test_boot_priority_out_of_range(self, sample_infra):
        """boot_priority: 101 triggers validation error."""
        sample_infra["domains"]["anklume"]["machines"]["admin-ctrl"]["boot_priority"] = 101
        errors = validate(sample_infra)
        assert any("boot_priority must be an integer 0-100" in e for e in errors)

    def test_boot_priority_negative(self, sample_infra):
        """boot_priority: -1 triggers validation error."""
        sample_infra["domains"]["anklume"]["machines"]["admin-ctrl"]["boot_priority"] = -1
        errors = validate(sample_infra)
        assert any("boot_priority must be an integer 0-100" in e for e in errors)

    def test_boot_priority_string(self, sample_infra):
        """boot_priority: 'high' triggers validation error."""
        sample_infra["domains"]["anklume"]["machines"]["admin-ctrl"]["boot_priority"] = "high"
        errors = validate(sample_infra)
        assert any("boot_priority must be an integer 0-100" in e for e in errors)


# -- snapshots schedule -------------------------------------------------------


class TestSnapshotsSchedule:
    """Test snapshots_schedule and snapshots_expiry validation and generation."""

    def test_schedule_propagated(self, sample_infra, tmp_path):
        """snapshots_schedule generates instance_snapshots_schedule in host_vars."""
        sample_infra["domains"]["anklume"]["machines"]["admin-ctrl"]["snapshots_schedule"] = "0 2 * * *"
        generate(sample_infra, tmp_path)
        content = (tmp_path / "host_vars" / "admin-ctrl.yml").read_text()
        assert "instance_snapshots_schedule" in content
        assert "0 2 * * *" in content

    def test_schedule_omitted(self, sample_infra, tmp_path):
        """Omitted snapshots_schedule does not appear in host_vars."""
        generate(sample_infra, tmp_path)
        content = (tmp_path / "host_vars" / "admin-ctrl.yml").read_text()
        assert "instance_snapshots_schedule" not in content

    def test_schedule_invalid_format(self, sample_infra):
        """Invalid cron expression triggers validation error."""
        sample_infra["domains"]["anklume"]["machines"]["admin-ctrl"]["snapshots_schedule"] = "every day"
        errors = validate(sample_infra)
        assert any("snapshots_schedule must be a cron expression" in e for e in errors)

    def test_schedule_too_few_fields(self, sample_infra):
        """Cron with <5 fields triggers validation error."""
        sample_infra["domains"]["anklume"]["machines"]["admin-ctrl"]["snapshots_schedule"] = "0 2 *"
        errors = validate(sample_infra)
        assert any("snapshots_schedule must be a cron expression" in e for e in errors)

    def test_expiry_propagated(self, sample_infra, tmp_path):
        """snapshots_expiry generates instance_snapshots_expiry in host_vars."""
        sample_infra["domains"]["anklume"]["machines"]["admin-ctrl"]["snapshots_expiry"] = "30d"
        generate(sample_infra, tmp_path)
        content = (tmp_path / "host_vars" / "admin-ctrl.yml").read_text()
        assert "instance_snapshots_expiry" in content
        assert "30d" in content

    def test_expiry_hours_valid(self, sample_infra):
        """snapshots_expiry: '24h' is valid."""
        sample_infra["domains"]["anklume"]["machines"]["admin-ctrl"]["snapshots_expiry"] = "24h"
        errors = validate(sample_infra)
        assert not any("snapshots_expiry" in e for e in errors)

    def test_expiry_minutes_valid(self, sample_infra):
        """snapshots_expiry: '60m' is valid."""
        sample_infra["domains"]["anklume"]["machines"]["admin-ctrl"]["snapshots_expiry"] = "60m"
        errors = validate(sample_infra)
        assert not any("snapshots_expiry" in e for e in errors)

    def test_expiry_invalid_format(self, sample_infra):
        """Invalid expiry format triggers validation error."""
        sample_infra["domains"]["anklume"]["machines"]["admin-ctrl"]["snapshots_expiry"] = "30 days"
        errors = validate(sample_infra)
        assert any("snapshots_expiry must be a duration" in e for e in errors)

    def test_expiry_no_unit(self, sample_infra):
        """Expiry without unit triggers validation error."""
        sample_infra["domains"]["anklume"]["machines"]["admin-ctrl"]["snapshots_expiry"] = "30"
        errors = validate(sample_infra)
        assert any("snapshots_expiry must be a duration" in e for e in errors)

    def test_schedule_and_expiry_together(self, sample_infra, tmp_path):
        """Both schedule and expiry can be set together."""
        m = sample_infra["domains"]["anklume"]["machines"]["admin-ctrl"]
        m["snapshots_schedule"] = "0 3 * * 0"
        m["snapshots_expiry"] = "7d"
        errors = validate(sample_infra)
        assert not any("snapshots" in e for e in errors)
        generate(sample_infra, tmp_path)
        content = (tmp_path / "host_vars" / "admin-ctrl.yml").read_text()
        assert "instance_snapshots_schedule" in content
        assert "instance_snapshots_expiry" in content


class TestNestingPrefix:
    """Tests for global.nesting_prefix feature (enabled by default)."""

    @pytest.fixture()
    def sample_infra(self):
        return {
            "project_name": "test",
            "global": {"base_subnet": "10.200", "default_os_image": "images:debian/13"},
            "domains": {
                "anklume": {
                    "subnet_id": 0,
                    "machines": {
                        "anklume-instance": {"type": "lxc", "ip": "10.200.0.10"},
                    },
                },
                "pro": {
                    "subnet_id": 2,
                    "machines": {
                        "pro-dev": {"type": "lxc", "ip": "10.200.2.10"},
                    },
                },
            },
        }

    def test_prefix_enabled_by_default(self, sample_infra, tmp_path, monkeypatch):
        """Without explicit nesting_prefix, Incus names are prefixed (default: true)."""
        monkeypatch.setattr("generate._read_absolute_level", lambda: 1)
        generate(sample_infra, tmp_path)
        gv = (tmp_path / "group_vars" / "pro.yml").read_text()
        assert "incus_project: 001-pro" in gv
        assert "name: 001-net-pro" in gv
        hv = (tmp_path / "host_vars" / "pro-dev.yml").read_text()
        assert "instance_name: 001-pro-dev" in hv

    def test_prefix_false_disables(self, sample_infra, tmp_path):
        """nesting_prefix: false disables prefixing."""
        sample_infra["global"]["nesting_prefix"] = False
        generate(sample_infra, tmp_path)
        gv = (tmp_path / "group_vars" / "pro.yml").read_text()
        assert "incus_project: pro" in gv
        assert "name: net-pro" in gv

    def test_prefix_enabled(self, sample_infra, tmp_path, monkeypatch):
        """nesting_prefix: true prefixes Incus names with nesting level."""
        sample_infra["global"]["nesting_prefix"] = True
        monkeypatch.setattr(
            "generate._read_absolute_level", lambda: 1
        )
        generate(sample_infra, tmp_path)
        gv = (tmp_path / "group_vars" / "pro.yml").read_text()
        assert "incus_project: 001-pro" in gv
        assert "name: 001-net-pro" in gv
        hv = (tmp_path / "host_vars" / "pro-dev.yml").read_text()
        assert "instance_name: 001-pro-dev" in hv

    def test_prefix_level_zero(self, sample_infra, tmp_path, monkeypatch):
        """Level 0 produces 000- prefix."""
        sample_infra["global"]["nesting_prefix"] = True
        monkeypatch.setattr("generate._read_absolute_level", lambda: 0)
        generate(sample_infra, tmp_path)
        gv = (tmp_path / "group_vars" / "pro.yml").read_text()
        assert "incus_project: 000-pro" in gv
        assert "name: 000-net-pro" in gv

    def test_prefix_level_two(self, sample_infra, tmp_path, monkeypatch):
        """Level 2 produces 002- prefix."""
        sample_infra["global"]["nesting_prefix"] = True
        monkeypatch.setattr("generate._read_absolute_level", lambda: 2)
        generate(sample_infra, tmp_path)
        hv = (tmp_path / "host_vars" / "pro-dev.yml").read_text()
        assert "instance_name: 002-pro-dev" in hv

    def test_prefix_default_level_when_file_absent(self, sample_infra, tmp_path, monkeypatch):
        """When absolute_level file is absent, default level is 1."""
        sample_infra["global"]["nesting_prefix"] = True
        monkeypatch.setattr("generate._read_absolute_level", lambda: None)
        generate(sample_infra, tmp_path)
        gv = (tmp_path / "group_vars" / "pro.yml").read_text()
        assert "incus_project: 001-pro" in gv

    def test_prefix_does_not_change_file_paths(self, sample_infra, tmp_path, monkeypatch):
        """File paths use unprefixed domain/machine names."""
        sample_infra["global"]["nesting_prefix"] = True
        monkeypatch.setattr("generate._read_absolute_level", lambda: 1)
        generate(sample_infra, tmp_path)
        # File paths remain unprefixed
        assert (tmp_path / "inventory" / "pro.yml").exists()
        assert (tmp_path / "group_vars" / "pro.yml").exists()
        assert (tmp_path / "host_vars" / "pro-dev.yml").exists()
        # No prefixed file paths created
        assert not (tmp_path / "inventory" / "001-pro.yml").exists()
        assert not (tmp_path / "group_vars" / "001-pro.yml").exists()

    def test_prefix_does_not_change_domain_name(self, sample_infra, tmp_path, monkeypatch):
        """domain_name in group_vars stays unprefixed (user-facing)."""
        sample_infra["global"]["nesting_prefix"] = True
        monkeypatch.setattr("generate._read_absolute_level", lambda: 1)
        generate(sample_infra, tmp_path)
        gv = (tmp_path / "group_vars" / "pro.yml").read_text()
        assert "domain_name: pro" in gv

    def test_prefix_validation_non_boolean(self, sample_infra):
        """Non-boolean nesting_prefix triggers validation error."""
        sample_infra["global"]["nesting_prefix"] = "yes"
        errors = validate(sample_infra)
        assert any("nesting_prefix must be a boolean" in e for e in errors)

    def test_prefix_validation_boolean_ok(self, sample_infra):
        """Boolean nesting_prefix passes validation."""
        sample_infra["global"]["nesting_prefix"] = True
        errors = validate(sample_infra)
        assert not any("nesting_prefix" in e for e in errors)
        sample_infra["global"]["nesting_prefix"] = False
        errors = validate(sample_infra)
        assert not any("nesting_prefix" in e for e in errors)
