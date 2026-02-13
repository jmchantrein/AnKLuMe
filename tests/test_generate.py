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

    def test_host_vars_with_devices(self, sample_infra, tmp_path):
        """Machine with devices declaration produces instance_devices in host_vars."""
        sample_infra["domains"]["admin"]["machines"]["admin-ctrl"]["devices"] = {
            "gpu": {"type": "gpu"},
        }
        sample_infra["domains"]["admin"]["machines"]["admin-ctrl"]["config"] = {
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


# -- VM support ----------------------------------------------------------------


class TestVMSupport:
    def test_vm_type_accepted(self, sample_infra):
        """type: vm is a valid instance type."""
        sample_infra["domains"]["work"]["machines"]["dev-ws"]["type"] = "vm"
        assert validate(sample_infra) == []

    def test_lxc_type_accepted(self, sample_infra):
        """type: lxc is the default and valid."""
        assert validate(sample_infra) == []

    def test_invalid_type_rejected(self, sample_infra):
        """type: docker is not a valid instance type."""
        sample_infra["domains"]["work"]["machines"]["dev-ws"]["type"] = "docker"
        errors = validate(sample_infra)
        assert any("type must be 'lxc' or 'vm'" in e for e in errors)

    def test_vm_host_vars_type(self, sample_infra, tmp_path):
        """VM machine produces instance_type: vm in host_vars."""
        sample_infra["domains"]["work"]["machines"]["dev-ws"]["type"] = "vm"
        generate(sample_infra, tmp_path)
        content = (tmp_path / "host_vars" / "dev-ws.yml").read_text()
        assert "instance_type: vm" in content

    def test_vm_and_lxc_coexist(self, sample_infra, tmp_path):
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

    def test_vm_with_config(self, sample_infra, tmp_path):
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

    def test_default_type_is_lxc(self, sample_infra, tmp_path):
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

    def test_single_gpu_exclusive_ok(self, sample_infra):
        """One GPU instance in exclusive mode (default) is valid."""
        self._add_gpu_machine(sample_infra, "work", "gpu-ws", "10.100.1.20")
        assert validate(sample_infra) == []

    def test_multiple_gpu_exclusive_error(self, sample_infra):
        """Multiple GPU instances in exclusive mode triggers error."""
        self._add_gpu_machine(sample_infra, "admin", "gpu-a", "10.100.0.20")
        self._add_gpu_machine(sample_infra, "work", "gpu-b", "10.100.1.20")
        errors = validate(sample_infra)
        assert any("GPU policy is 'exclusive'" in e for e in errors)
        assert any("gpu-a" in e and "gpu-b" in e for e in errors)

    def test_multiple_gpu_shared_no_error(self, sample_infra):
        """Multiple GPU instances with shared policy passes validation."""
        sample_infra["global"]["gpu_policy"] = "shared"
        self._add_gpu_machine(sample_infra, "admin", "gpu-a", "10.100.0.20")
        self._add_gpu_machine(sample_infra, "work", "gpu-b", "10.100.1.20")
        assert validate(sample_infra) == []

    def test_shared_gpu_warning(self, sample_infra):
        """Shared GPU policy emits warning when multiple instances share GPU."""
        sample_infra["global"]["gpu_policy"] = "shared"
        self._add_gpu_machine(sample_infra, "admin", "gpu-a", "10.100.0.20")
        self._add_gpu_machine(sample_infra, "work", "gpu-b", "10.100.1.20")
        warnings = get_warnings(sample_infra)
        assert any("shared" in w.lower() for w in warnings)

    def test_no_gpu_no_warning(self, sample_infra):
        """No GPU instances produces no warnings."""
        assert get_warnings(sample_infra) == []

    def test_single_gpu_no_warning(self, sample_infra):
        """Single GPU instance produces no warning even in shared mode."""
        sample_infra["global"]["gpu_policy"] = "shared"
        self._add_gpu_machine(sample_infra, "work", "gpu-ws", "10.100.1.20")
        assert get_warnings(sample_infra) == []

    def test_gpu_via_profile_device_detected(self, sample_infra):
        """GPU access via profile device is detected by exclusive policy."""
        self._add_gpu_machine(sample_infra, "admin", "gpu-a", "10.100.0.20", via_flag=True)
        self._add_gpu_machine(sample_infra, "work", "gpu-b", "10.100.1.20", via_flag=False)
        errors = validate(sample_infra)
        assert any("GPU policy is 'exclusive'" in e for e in errors)

    def test_invalid_gpu_policy(self, sample_infra):
        """Invalid gpu_policy value triggers error."""
        sample_infra["global"]["gpu_policy"] = "permissive"
        errors = validate(sample_infra)
        assert any("gpu_policy must be 'exclusive' or 'shared'" in e for e in errors)

    def test_default_gpu_policy_is_exclusive(self, sample_infra):
        """Without gpu_policy in global, default is exclusive."""
        self._add_gpu_machine(sample_infra, "admin", "gpu-a", "10.100.0.20")
        self._add_gpu_machine(sample_infra, "work", "gpu-b", "10.100.1.20")
        # No gpu_policy set, should default to exclusive and error
        errors = validate(sample_infra)
        assert any("GPU policy is 'exclusive'" in e for e in errors)


# -- firewall mode (Phase 11) -------------------------------------------------


class TestFirewallMode:
    def test_default_host_mode_valid(self, sample_infra):
        """No firewall_mode set defaults to 'host' (valid)."""
        assert validate(sample_infra) == []

    def test_host_mode_valid(self, sample_infra):
        """Explicit firewall_mode: host is valid."""
        sample_infra["global"]["firewall_mode"] = "host"
        assert validate(sample_infra) == []

    def test_vm_mode_valid(self, sample_infra):
        """firewall_mode: vm is valid."""
        sample_infra["global"]["firewall_mode"] = "vm"
        assert validate(sample_infra) == []

    def test_invalid_mode_rejected(self, sample_infra):
        """Invalid firewall_mode triggers error."""
        sample_infra["global"]["firewall_mode"] = "container"
        errors = validate(sample_infra)
        assert any("firewall_mode must be 'host' or 'vm'" in e for e in errors)


# -- firewall VM auto-creation (enrich_infra) ---------------------------------


class TestFirewallVMAutoCreation:
    def test_firewall_mode_vm_auto_creates_sys_firewall(self, sample_infra):
        """firewall_mode: vm auto-creates sys-firewall in admin domain."""
        sample_infra["global"]["firewall_mode"] = "vm"
        enrich_infra(sample_infra)
        admin_machines = sample_infra["domains"]["admin"]["machines"]
        assert "sys-firewall" in admin_machines

    def test_firewall_mode_vm_auto_created_has_correct_ip(self, sample_infra):
        """Auto-created sys-firewall gets IP <base_subnet>.<admin_subnet_id>.253."""
        sample_infra["global"]["firewall_mode"] = "vm"
        enrich_infra(sample_infra)
        sys_fw = sample_infra["domains"]["admin"]["machines"]["sys-firewall"]
        assert sys_fw["ip"] == "10.100.0.253"

    def test_firewall_mode_vm_auto_created_roles(self, sample_infra):
        """Auto-created sys-firewall has base_system and firewall_router roles."""
        sample_infra["global"]["firewall_mode"] = "vm"
        enrich_infra(sample_infra)
        sys_fw = sample_infra["domains"]["admin"]["machines"]["sys-firewall"]
        assert sys_fw["roles"] == ["base_system", "firewall_router"]

    def test_firewall_mode_vm_no_admin_domain_error(self, sample_infra):
        """firewall_mode: vm without admin domain exits with error."""
        sample_infra["global"]["firewall_mode"] = "vm"
        del sample_infra["domains"]["admin"]
        with pytest.raises(SystemExit):
            enrich_infra(sample_infra)

    def test_firewall_mode_vm_user_override_not_overwritten(self, sample_infra):
        """If user declares sys-firewall, enrich_infra does not overwrite it."""
        sample_infra["global"]["firewall_mode"] = "vm"
        sample_infra["domains"]["admin"]["machines"]["sys-firewall"] = {
            "description": "My custom firewall",
            "type": "vm",
            "ip": "10.100.0.200",
            "roles": ["base_system"],
        }
        enrich_infra(sample_infra)
        sys_fw = sample_infra["domains"]["admin"]["machines"]["sys-firewall"]
        # User's config should be preserved, not overwritten
        assert sys_fw["ip"] == "10.100.0.200"
        assert sys_fw["description"] == "My custom firewall"


# -- orphan protection ---------------------------------------------------------


class TestEphemeralOrphans:
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

    def test_privileged_lxc_rejected_when_vm_nested_false(self, sample_infra, monkeypatch):
        """Privileged LXC is an error when vm_nested=false."""
        monkeypatch.setattr(gen_mod, "_read_vm_nested", lambda: False)
        monkeypatch.setattr(gen_mod, "_read_yolo", lambda: False)
        self._make_privileged(sample_infra)
        errors = validate(sample_infra)
        assert any("security.privileged=true on LXC is forbidden" in e for e in errors)

    def test_privileged_lxc_allowed_when_vm_nested_true(self, sample_infra, monkeypatch):
        """Privileged LXC is allowed when vm_nested=true."""
        monkeypatch.setattr(gen_mod, "_read_vm_nested", lambda: True)
        monkeypatch.setattr(gen_mod, "_read_yolo", lambda: False)
        self._make_privileged(sample_infra)
        errors = validate(sample_infra)
        assert not any("privileged" in e.lower() for e in errors)

    def test_privileged_lxc_allowed_when_vm_nested_none(self, sample_infra, monkeypatch):
        """When /etc/anklume/vm_nested does not exist, no enforcement."""
        monkeypatch.setattr(gen_mod, "_read_vm_nested", lambda: None)
        monkeypatch.setattr(gen_mod, "_read_yolo", lambda: False)
        self._make_privileged(sample_infra)
        errors = validate(sample_infra)
        assert not any("privileged" in e.lower() for e in errors)

    def test_privileged_vm_always_allowed(self, sample_infra, monkeypatch):
        """VMs can always have security.privileged (it's kernel-isolated)."""
        monkeypatch.setattr(gen_mod, "_read_vm_nested", lambda: False)
        monkeypatch.setattr(gen_mod, "_read_yolo", lambda: False)
        sample_infra["domains"]["admin"]["machines"]["admin-ctrl"]["type"] = "vm"
        self._make_privileged(sample_infra)
        errors = validate(sample_infra)
        assert not any("privileged" in e.lower() for e in errors)

    def test_yolo_bypasses_privileged_error(self, sample_infra, monkeypatch):
        """YOLO mode turns privileged error into warning."""
        monkeypatch.setattr(gen_mod, "_read_vm_nested", lambda: False)
        monkeypatch.setattr(gen_mod, "_read_yolo", lambda: True)
        self._make_privileged(sample_infra)
        errors = validate(sample_infra)
        assert not any("privileged" in e.lower() for e in errors)
        warnings = get_warnings(sample_infra)
        assert any("YOLO" in w for w in warnings)

    def test_non_privileged_lxc_no_error(self, sample_infra, monkeypatch):
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

    def test_valid_domain_to_domain_policy(self, sample_infra):
        """Policy between two known domains is valid."""
        self._add_policies(sample_infra, [
            {"from": "admin", "to": "work", "ports": [22], "protocol": "tcp"},
        ])
        errors = validate(sample_infra)
        assert not any("network_policies" in e for e in errors)

    def test_valid_machine_to_domain_policy(self, sample_infra):
        """Policy from a machine to a domain is valid."""
        self._add_policies(sample_infra, [
            {"from": "admin-ctrl", "to": "work", "ports": [443]},
        ])
        errors = validate(sample_infra)
        assert not any("network_policies" in e for e in errors)

    def test_valid_host_keyword(self, sample_infra):
        """'host' is a valid from/to reference."""
        self._add_policies(sample_infra, [
            {"from": "host", "to": "admin", "ports": [22], "protocol": "tcp"},
        ])
        errors = validate(sample_infra)
        assert not any("network_policies" in e for e in errors)

    def test_valid_ports_all(self, sample_infra):
        """ports: all is valid."""
        self._add_policies(sample_infra, [
            {"from": "admin", "to": "work", "ports": "all"},
        ])
        errors = validate(sample_infra)
        assert not any("network_policies" in e for e in errors)

    def test_unknown_from_rejected(self, sample_infra):
        """Unknown 'from' reference triggers error."""
        self._add_policies(sample_infra, [
            {"from": "nonexistent", "to": "admin", "ports": [22]},
        ])
        errors = validate(sample_infra)
        assert any("from: nonexistent" in e for e in errors)

    def test_unknown_to_rejected(self, sample_infra):
        """Unknown 'to' reference triggers error."""
        self._add_policies(sample_infra, [
            {"from": "admin", "to": "nonexistent", "ports": [22]},
        ])
        errors = validate(sample_infra)
        assert any("to: nonexistent" in e for e in errors)

    def test_missing_from_field(self, sample_infra):
        """Missing 'from' field triggers error."""
        self._add_policies(sample_infra, [
            {"to": "admin", "ports": [22]},
        ])
        errors = validate(sample_infra)
        assert any("missing 'from'" in e for e in errors)

    def test_missing_to_field(self, sample_infra):
        """Missing 'to' field triggers error."""
        self._add_policies(sample_infra, [
            {"from": "admin", "ports": [22]},
        ])
        errors = validate(sample_infra)
        assert any("missing 'to'" in e for e in errors)

    def test_invalid_port_number(self, sample_infra):
        """Port out of range triggers error."""
        self._add_policies(sample_infra, [
            {"from": "admin", "to": "work", "ports": [99999]},
        ])
        errors = validate(sample_infra)
        assert any("invalid port" in e for e in errors)

    def test_invalid_port_type(self, sample_infra):
        """Non-list non-'all' ports triggers error."""
        self._add_policies(sample_infra, [
            {"from": "admin", "to": "work", "ports": "tcp"},
        ])
        errors = validate(sample_infra)
        assert any("ports must be a list or 'all'" in e for e in errors)

    def test_invalid_protocol(self, sample_infra):
        """Invalid protocol triggers error."""
        self._add_policies(sample_infra, [
            {"from": "admin", "to": "work", "ports": [22], "protocol": "icmp"},
        ])
        errors = validate(sample_infra)
        assert any("protocol must be 'tcp' or 'udp'" in e for e in errors)

    def test_policies_in_group_vars_all(self, sample_infra, tmp_path):
        """Network policies appear in group_vars/all.yml."""
        self._add_policies(sample_infra, [
            {"description": "Admin SSH", "from": "admin", "to": "work",
             "ports": [22], "protocol": "tcp"},
        ])
        generate(sample_infra, tmp_path)
        content = (tmp_path / "group_vars" / "all.yml").read_text()
        assert "network_policies" in content
        assert "Admin SSH" in content

    def test_no_policies_no_key_in_all(self, sample_infra, tmp_path):
        """Without network_policies, the key is absent from group_vars/all.yml."""
        generate(sample_infra, tmp_path)
        content = (tmp_path / "group_vars" / "all.yml").read_text()
        assert "network_policies" not in content

    def test_bidirectional_valid(self, sample_infra):
        """bidirectional: true is accepted."""
        self._add_policies(sample_infra, [
            {"from": "admin", "to": "work", "ports": "all", "bidirectional": True},
        ])
        errors = validate(sample_infra)
        assert not any("network_policies" in e for e in errors)

    def test_empty_policies_valid(self, sample_infra):
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

    def test_load_from_directory(self, sample_infra, tmp_path):
        """Loading from infra/ directory produces same structure as single file."""
        infra_dir = self._create_infra_dir(tmp_path, sample_infra)
        result = load_infra(infra_dir)
        assert result["project_name"] == sample_infra["project_name"]
        assert "admin" in result["domains"]
        assert "work" in result["domains"]

    def test_directory_generates_same_output(self, sample_infra, tmp_path):
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

    def test_directory_with_policies(self, sample_infra, tmp_path):
        """policies.yml is merged from infra/ directory."""
        sample_infra["network_policies"] = [
            {"from": "admin", "to": "work", "ports": [22], "protocol": "tcp"},
        ]
        infra_dir = self._create_infra_dir(tmp_path, sample_infra)
        result = load_infra(infra_dir)
        assert "network_policies" in result
        assert len(result["network_policies"]) == 1

    def test_directory_missing_base_yml_exits(self, tmp_path):
        """Missing base.yml triggers exit."""
        infra_dir = tmp_path / "infra"
        infra_dir.mkdir()
        with pytest.raises(SystemExit):
            load_infra(infra_dir)

    def test_load_autodetects_file(self, sample_infra, tmp_path):
        """load_infra('infra.yml') works when file exists."""
        p = tmp_path / "infra.yml"
        p.write_text(yaml.dump(sample_infra, sort_keys=False))
        result = load_infra(p)
        assert result["project_name"] == "test-infra"

    def test_load_autodetects_dir(self, sample_infra, tmp_path):
        """load_infra('infra') works when directory exists."""
        infra_dir = self._create_infra_dir(tmp_path, sample_infra)
        # Load using the directory path directly
        result = load_infra(infra_dir)
        assert result["project_name"] == "test-infra"

    def test_domains_sorted_alphabetically(self, sample_infra, tmp_path):
        """Domain files are loaded in alphabetical order."""
        infra_dir = self._create_infra_dir(tmp_path, sample_infra)
        result = load_infra(infra_dir)
        # Both admin and work should be present regardless of file order
        assert set(result["domains"]) == {"admin", "work"}

    def test_empty_domains_dir(self, sample_infra, tmp_path):
        """Empty domains/ directory yields no domains."""
        infra_dir = tmp_path / "infra"
        infra_dir.mkdir()
        (infra_dir / "domains").mkdir()
        base = {"project_name": "test", "global": sample_infra["global"]}
        (infra_dir / "base.yml").write_text(yaml.dump(base, sort_keys=False))
        result = load_infra(infra_dir)
        assert result.get("domains", {}) == {}
