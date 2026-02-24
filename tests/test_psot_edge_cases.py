"""Tests for PSOT generator edge cases — boundary conditions and special inputs.

Exercises scripts/generate.py functions through unusual YAML structures,
boundary values, and special content. Does NOT use Jinja2 templates.
"""

import sys
import tempfile
from pathlib import Path

import yaml

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from generate import (  # noqa: E402
    MANAGED_BEGIN,
    MANAGED_END,
    _managed_block,
    _write_managed,
    _yaml,
    detect_orphans,
    enrich_infra,
    extract_all_images,
    generate,
    validate,
)


def _minimal_infra(**overrides):
    """Build a minimal valid infra dict with optional overrides."""
    infra = {
        "project_name": "edge-test",
        "global": {"base_subnet": "10.100", "default_os_image": "images:debian/13"},
        "domains": {
            "test": {
                "subnet_id": 1,
                "machines": {
                    "test-m1": {"type": "lxc", "ip": "10.100.1.10"},
                },
            },
        },
    }
    infra.update(overrides)
    return infra


# ── Unusual YAML values in descriptions ──────────────────────


class TestPSOTUnusualYAMLValues:
    """Test the generator with unusual descriptions and string values."""

    def test_description_with_colon(self):
        """Descriptions containing colons don't break YAML output."""
        infra = _minimal_infra()
        infra["domains"]["test"]["description"] = "My domain: the best one"
        errors = validate(infra)
        assert errors == []
        with tempfile.TemporaryDirectory() as d:
            files = generate(infra, d, dry_run=True)
            assert len(files) > 0

    def test_description_with_hash(self):
        """Descriptions containing hash characters don't break YAML."""
        infra = _minimal_infra()
        infra["domains"]["test"]["description"] = "Domain #1 is great"
        errors = validate(infra)
        assert errors == []
        with tempfile.TemporaryDirectory() as d:
            files = generate(infra, d, dry_run=True)
            assert len(files) > 0

    def test_description_with_quotes(self):
        """Descriptions with quotes are handled correctly."""
        infra = _minimal_infra()
        infra["domains"]["test"]["description"] = 'Domain "quoted" description'
        errors = validate(infra)
        assert errors == []
        with tempfile.TemporaryDirectory() as d:
            files = generate(infra, d, dry_run=True)
            assert len(files) > 0

    def test_description_with_unicode(self):
        """Unicode descriptions (French) are preserved."""
        infra = _minimal_infra()
        infra["domains"]["test"]["description"] = "Domaine professionnel avec accents aeio"
        errors = validate(infra)
        assert errors == []
        with tempfile.TemporaryDirectory() as d:
            files = generate(infra, d, dry_run=True)
            # Simply verify generation succeeds
            assert len(files) > 0

    def test_empty_description(self):
        """Empty description is valid."""
        infra = _minimal_infra()
        infra["domains"]["test"]["description"] = ""
        errors = validate(infra)
        assert errors == []

    def test_description_with_newline_in_machine(self):
        """Machine description with embedded newlines is valid."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"]["test-m1"]["description"] = "line1\nline2"
        errors = validate(infra)
        assert errors == []

    def test_config_with_boolean_string(self):
        """Config values like 'true' as string are valid."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"]["test-m1"]["config"] = {
            "security.nesting": "true",
            "security.privileged": "false",
        }
        errors = validate(infra)
        assert errors == []

    def test_config_with_numeric_string(self):
        """Config values like '2' as string are valid."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"]["test-m1"]["config"] = {
            "limits.cpu": "2",
            "limits.memory": "4GiB",
        }
        errors = validate(infra)
        assert errors == []

    def test_roles_as_empty_list(self):
        """Machine with empty roles list is valid."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"]["test-m1"]["roles"] = []
        errors = validate(infra)
        assert errors == []


# ── Deeply nested profile configurations ─────────────────────


class TestPSOTDeeplyNestedConfigs:
    """Test profiles with complex nested config and device structures."""

    def test_profile_with_config_and_devices(self):
        """Profiles with both config and devices are valid."""
        infra = _minimal_infra()
        infra["domains"]["test"]["profiles"] = {
            "complex": {
                "config": {"limits.cpu": "4", "limits.memory": "8GiB"},
                "devices": {
                    "gpu": {"type": "gpu", "gputype": "physical"},
                    "disk": {"type": "disk", "path": "/data", "source": "/mnt/data"},
                },
            },
        }
        infra["domains"]["test"]["machines"]["test-m1"]["profiles"] = ["default", "complex"]
        errors = validate(infra)
        assert errors == []

    def test_multiple_profiles_per_domain(self):
        """Domain with many profiles is valid."""
        infra = _minimal_infra()
        infra["domains"]["test"]["profiles"] = {
            f"profile-{i}": {"config": {f"user.label{i}": f"val{i}"}}
            for i in range(5)
        }
        errors = validate(infra)
        assert errors == []

    def test_machine_references_multiple_profiles(self):
        """Machine referencing multiple domain profiles is valid."""
        infra = _minimal_infra()
        infra["domains"]["test"]["profiles"] = {
            "nesting": {"config": {"security.nesting": "true"}},
            "resources": {"config": {"limits.cpu": "2"}},
        }
        infra["domains"]["test"]["machines"]["test-m1"]["profiles"] = [
            "default", "nesting", "resources",
        ]
        errors = validate(infra)
        assert errors == []

    def test_storage_volumes_in_machine(self):
        """Machine with storage_volumes passes validation."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"]["test-m1"]["storage_volumes"] = {
            "data": {"pool": "default", "size": "10GiB"},
        }
        errors = validate(infra)
        assert errors == []


# ── Subnet boundary values ───────────────────────────────────


class TestPSOTSubnetBoundary:
    """Test subnet_id at boundaries (0, 254) and generation."""

    def test_subnet_id_zero(self):
        """subnet_id=0 is valid."""
        infra = _minimal_infra()
        infra["domains"]["test"]["subnet_id"] = 0
        infra["domains"]["test"]["machines"]["test-m1"]["ip"] = "10.100.0.10"
        errors = validate(infra)
        assert errors == []

    def test_subnet_id_254(self):
        """subnet_id=254 is valid."""
        infra = _minimal_infra()
        infra["domains"]["test"]["subnet_id"] = 254
        infra["domains"]["test"]["machines"]["test-m1"]["ip"] = "10.100.254.10"
        errors = validate(infra)
        assert errors == []

    def test_subnet_id_negative_rejected(self):
        """subnet_id=-1 is rejected."""
        infra = _minimal_infra()
        infra["domains"]["test"]["subnet_id"] = -1
        errors = validate(infra)
        assert any("subnet_id must be 0-254" in e for e in errors)

    def test_subnet_id_255_rejected(self):
        """subnet_id=255 is rejected."""
        infra = _minimal_infra()
        infra["domains"]["test"]["subnet_id"] = 255
        errors = validate(infra)
        assert any("subnet_id must be 0-254" in e for e in errors)

    def test_many_subnets_no_collision(self):
        """Many domains with unique subnet_ids validate successfully."""
        infra = _minimal_infra()
        infra["domains"] = {}
        for i in range(10):
            infra["domains"][f"dom{i}"] = {
                "subnet_id": i * 25,
                "machines": {
                    f"m{i}": {"type": "lxc", "ip": f"10.100.{i*25}.10"},
                },
            }
        errors = validate(infra)
        assert errors == []


# ── Large-scale infrastructure ───────────────────────────────


class TestPSOTLargeScale:
    """Test with many domains and machines."""

    def test_twenty_domains(self):
        """20 domains with unique subnet_ids pass validation."""
        infra = _minimal_infra()
        infra["domains"] = {}
        for i in range(20):
            infra["domains"][f"zone{i}"] = {
                "subnet_id": i,
                "machines": {
                    f"zone{i}-host": {"type": "lxc", "ip": f"10.100.{i}.10"},
                },
            }
        errors = validate(infra)
        assert errors == []

    def test_ten_machines_per_domain(self):
        """Domain with 10 machines passes validation."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"] = {
            f"test-m{i}": {"type": "lxc", "ip": f"10.100.1.{10+i}"}
            for i in range(10)
        }
        errors = validate(infra)
        assert errors == []

    def test_mixed_lxc_and_vm(self):
        """Domain with both LXC and VM machines passes validation."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"] = {
            "test-lxc": {"type": "lxc", "ip": "10.100.1.10"},
            "test-vm": {
                "type": "vm",
                "ip": "10.100.1.20",
                "config": {"limits.cpu": "2", "limits.memory": "2GiB"},
            },
        }
        errors = validate(infra)
        assert errors == []


# ── Managed section preservation ─────────────────────────────


class TestPSOTManagedPreservation:
    """Test _write_managed with various existing file content."""

    def test_multiline_user_content_preserved(self):
        """User content before and after managed section is preserved."""
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "test.yml"
            existing = (
                "---\n"
                "# User header\n"
                f"{MANAGED_BEGIN}\n"
                "# Do not edit this section\n"
                "old: data\n"
                f"{MANAGED_END}\n"
                "\n"
                "# User variable 1\n"
                "custom_var: hello\n"
                "# User variable 2\n"
                "other_var: world\n"
            )
            p.write_text(existing)
            _write_managed(p, {"new": "data"})
            result = p.read_text()
            assert "custom_var: hello" in result
            assert "other_var: world" in result
            assert "User header" in result
            assert "new: data" in result
            assert "old: data" not in result

    def test_unicode_in_managed_content(self):
        """Unicode content in managed section is preserved correctly."""
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "test.yml"
            _write_managed(p, {"description": "Domaine francais"})
            result = p.read_text()
            assert "Domaine francais" in result

    def test_empty_dict_generates_valid_managed(self):
        """Empty dict generates a valid managed section."""
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "test.yml"
            _write_managed(p, {})
            result = p.read_text()
            assert MANAGED_BEGIN in result
            assert MANAGED_END in result
            assert "{}" in result or result.count("\n") >= 2

    def test_no_duplication_on_double_write(self):
        """Writing twice doesn't duplicate the managed section."""
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "test.yml"
            _write_managed(p, {"v": 1})
            _write_managed(p, {"v": 2})
            result = p.read_text()
            assert result.count(MANAGED_BEGIN) == 1
            assert result.count(MANAGED_END) == 1
            assert "v: 2" in result

    def test_write_to_nonexistent_subdirectory(self):
        """Writing to a path with missing parent dirs creates them."""
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "sub" / "deep" / "test.yml"
            _write_managed(p, {"key": "value"})
            assert p.exists()
            assert "key: value" in p.read_text()


# ── Profile inheritance edge cases ───────────────────────────


class TestPSOTProfileInheritance:
    """Test profile reference validation and inheritance."""

    def test_config_only_profile(self):
        """Profile with config but no devices is valid."""
        infra = _minimal_infra()
        infra["domains"]["test"]["profiles"] = {
            "limits": {"config": {"limits.cpu": "4"}},
        }
        infra["domains"]["test"]["machines"]["test-m1"]["profiles"] = ["default", "limits"]
        errors = validate(infra)
        assert errors == []

    def test_device_only_profile(self):
        """Profile with devices but no config is valid."""
        infra = _minimal_infra()
        infra["domains"]["test"]["profiles"] = {
            "gpu-prof": {"devices": {"gpu": {"type": "gpu", "gputype": "physical"}}},
        }
        infra["domains"]["test"]["machines"]["test-m1"]["profiles"] = ["default", "gpu-prof"]
        infra["domains"]["test"]["machines"]["test-m1"]["gpu"] = True
        errors = validate(infra)
        assert errors == []

    def test_empty_profile(self):
        """Empty profile definition is valid (no config, no devices)."""
        infra = _minimal_infra()
        infra["domains"]["test"]["profiles"] = {"empty-prof": {}}
        infra["domains"]["test"]["machines"]["test-m1"]["profiles"] = ["default", "empty-prof"]
        errors = validate(infra)
        assert errors == []

    def test_no_profiles_on_machine(self):
        """Machine without profiles key is valid."""
        infra = _minimal_infra()
        assert "profiles" not in infra["domains"]["test"]["machines"]["test-m1"]
        errors = validate(infra)
        assert errors == []

    def test_default_profile_always_valid(self):
        """Referencing 'default' profile never causes an error."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"]["test-m1"]["profiles"] = ["default"]
        errors = validate(infra)
        assert errors == []

    def test_unknown_profile_rejected(self):
        """Referencing an undefined profile produces an error."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"]["test-m1"]["profiles"] = ["default", "nonexistent"]
        errors = validate(infra)
        assert any("profile 'nonexistent' not defined" in e for e in errors)

    def test_gpu_detected_through_profile_device(self):
        """GPU detection works through profile device scanning."""
        infra = _minimal_infra()
        infra["domains"]["test"]["profiles"] = {
            "nvidia": {"devices": {"gpu": {"type": "gpu"}}},
        }
        infra["domains"]["test"]["machines"]["test-m1"]["profiles"] = ["default", "nvidia"]
        # With exclusive GPU policy, one GPU instance is fine
        errors = validate(infra)
        assert errors == []


# ── Empty sections and minimal structures ────────────────────


class TestPSOTEmptySections:
    """Test with missing, null, or empty sections."""

    def test_domain_with_no_machines_key(self):
        """Domain without 'machines' key passes validation."""
        infra = _minimal_infra()
        del infra["domains"]["test"]["machines"]
        errors = validate(infra)
        assert errors == []

    def test_domain_with_null_machines(self):
        """Domain with machines: null passes validation."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"] = None
        errors = validate(infra)
        assert errors == []

    def test_domain_with_null_profiles(self):
        """Domain with profiles: null passes validation."""
        infra = _minimal_infra()
        infra["domains"]["test"]["profiles"] = None
        errors = validate(infra)
        assert errors == []

    def test_minimal_machine_no_optional_fields(self):
        """Machine with only type and ip is valid."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"]["test-m1"] = {
            "type": "lxc",
            "ip": "10.100.1.10",
        }
        errors = validate(infra)
        assert errors == []

    def test_empty_network_policies(self):
        """Empty network_policies list is valid."""
        infra = _minimal_infra()
        infra["network_policies"] = []
        errors = validate(infra)
        assert errors == []

    def test_minimal_global_section(self):
        """Global with just base_subnet is valid."""
        infra = _minimal_infra()
        infra["global"] = {"base_subnet": "10.100"}
        errors = validate(infra)
        assert errors == []


# ── Special domain and machine names ─────────────────────────


class TestPSOTSpecialNames:
    """Test domain and machine names at edge cases."""

    def test_numeric_domain_name(self):
        """Domain name starting with number is valid if alphanumeric."""
        infra = _minimal_infra()
        infra["domains"]["1lab"] = {
            "subnet_id": 50,
            "machines": {"lab-m1": {"type": "lxc", "ip": "10.100.50.10"}},
        }
        errors = validate(infra)
        # '1lab' starts with a digit which is valid per regex ^[a-z0-9][a-z0-9-]*$
        assert not any("1lab" in e and "invalid name" in e for e in errors)

    def test_domain_name_with_many_hyphens(self):
        """Domain name with multiple hyphens is valid."""
        infra = _minimal_infra()
        infra["domains"]["my-long-domain-name"] = {
            "subnet_id": 60,
            "machines": {
                "my-long-domain-name-m1": {"type": "lxc", "ip": "10.100.60.10"},
            },
        }
        errors = validate(infra)
        name_errors = [e for e in errors if "my-long-domain-name" in e and "invalid name" in e]
        assert len(name_errors) == 0

    def test_ai_tools_domain_name(self):
        """Domain named 'ai-tools' is valid."""
        infra = _minimal_infra()
        infra["domains"]["ai-tools"] = {
            "subnet_id": 10,
            "machines": {
                "gpu-server": {"type": "lxc", "ip": "10.100.10.10"},
            },
        }
        errors = validate(infra)
        name_errors = [e for e in errors if "ai-tools" in e and "invalid name" in e]
        assert len(name_errors) == 0

    def test_single_letter_domain(self):
        """Single-letter domain name is valid."""
        infra = _minimal_infra()
        infra["domains"]["x"] = {
            "subnet_id": 70,
            "machines": {"x-m1": {"type": "lxc", "ip": "10.100.70.10"}},
        }
        errors = validate(infra)
        name_errors = [e for e in errors if "'x'" in e and "invalid name" in e]
        assert len(name_errors) == 0

    def test_uppercase_domain_rejected(self):
        """Domain with uppercase letters is rejected."""
        infra = _minimal_infra()
        infra["domains"]["MyDomain"] = {
            "subnet_id": 80,
            "machines": {"my-m1": {"type": "lxc", "ip": "10.100.80.10"}},
        }
        errors = validate(infra)
        assert any("MyDomain" in e and "invalid name" in e for e in errors)

    def test_domain_starting_with_hyphen_rejected(self):
        """Domain starting with hyphen is rejected."""
        infra = _minimal_infra()
        infra["domains"]["-bad"] = {
            "subnet_id": 90,
            "machines": {"bad-m1": {"type": "lxc", "ip": "10.100.90.10"}},
        }
        errors = validate(infra)
        assert any("-bad" in e and "invalid name" in e for e in errors)

    def test_domain_with_underscore_rejected(self):
        """Domain with underscore is rejected."""
        infra = _minimal_infra()
        infra["domains"]["my_domain"] = {
            "subnet_id": 91,
            "machines": {"my-m1": {"type": "lxc", "ip": "10.100.91.10"}},
        }
        errors = validate(infra)
        assert any("my_domain" in e and "invalid name" in e for e in errors)

    def test_long_machine_name(self):
        """Long machine name is valid (no length limit in spec)."""
        infra = _minimal_infra()
        long_name = "a" * 63  # DNS label limit
        infra["domains"]["test"]["machines"][long_name] = {
            "type": "lxc", "ip": "10.100.1.20",
        }
        errors = validate(infra)
        # Should be valid (no length validation in generate.py)
        assert not any(long_name in e for e in errors)


# ── Image extraction edge cases ──────────────────────────────


class TestPSOTImageEdgeCases:
    """Test extract_all_images with various configurations."""

    def test_different_images_per_machine(self):
        """Different os_image per machine are all extracted."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"]["test-m1"]["os_image"] = "images:ubuntu/24.04"
        infra["domains"]["test"]["machines"]["test-m2"] = {
            "type": "lxc",
            "ip": "10.100.1.20",
            "os_image": "images:alpine/3.20",
        }
        images = extract_all_images(infra)
        assert "images:ubuntu/24.04" in images
        assert "images:alpine/3.20" in images

    def test_machine_without_image_uses_global(self):
        """Machine without os_image inherits global default."""
        infra = _minimal_infra()
        images = extract_all_images(infra)
        assert "images:debian/13" in images

    def test_no_default_image_no_machine_image(self):
        """No images collected when neither global nor machine has one."""
        infra = _minimal_infra()
        del infra["global"]["default_os_image"]
        # Machine doesn't have os_image either
        images = extract_all_images(infra)
        assert images == []


# ── PSOT: custom base subnet ────────────────────────────────


class TestPSOTCustomBaseSubnet:
    """Test generation with non-standard base_subnet values."""

    def test_192_168_base_subnet(self):
        """192.168 base subnet validates and generates correctly."""
        infra = _minimal_infra()
        infra["global"]["base_subnet"] = "192.168"
        infra["domains"]["test"]["machines"]["test-m1"]["ip"] = "192.168.1.10"
        errors = validate(infra)
        assert errors == []

    def test_172_16_base_subnet(self):
        """172.16 base subnet validates correctly."""
        infra = _minimal_infra()
        infra["global"]["base_subnet"] = "172.16"
        infra["domains"]["test"]["machines"]["test-m1"]["ip"] = "172.16.1.10"
        errors = validate(infra)
        assert errors == []

    def test_ip_wrong_subnet_with_custom_base(self):
        """IP not matching custom base subnet is rejected."""
        infra = _minimal_infra()
        infra["global"]["base_subnet"] = "192.168"
        # IP uses 10.100 but base is 192.168
        infra["domains"]["test"]["machines"]["test-m1"]["ip"] = "10.100.1.10"
        errors = validate(infra)
        assert any("not in subnet" in e for e in errors)


# ── PSOT: network policies in output ─────────────────────────


class TestPSOTNetworkPoliciesOutput:
    """Test that network policies appear in generated group_vars/all.yml."""

    def test_policies_in_all_yml(self):
        """Network policies are written to group_vars/all.yml."""
        infra = _minimal_infra()
        infra["network_policies"] = [{
            "description": "Test policy",
            "from": "test",
            "to": "test",
            "ports": [80],
            "protocol": "tcp",
        }]
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            all_yml = Path(d) / "group_vars" / "all.yml"
            content = all_yml.read_text()
            assert "network_policies" in content

    def test_no_policies_no_key_in_all_yml(self):
        """Without network policies, the key is absent from all.yml."""
        infra = _minimal_infra()
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            all_yml = Path(d) / "group_vars" / "all.yml"
            content = all_yml.read_text()
            assert "network_policies" not in content


# ── PSOT: inventory structure ────────────────────────────────


class TestPSOTInventoryStructure:
    """Test the structure of generated inventory files."""

    def test_host_without_ip_has_null_entry(self):
        """Host without IP generates a null entry in inventory."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"]["test-m1"] = {"type": "lxc"}
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            inv = Path(d) / "inventory" / "test.yml"
            content = inv.read_text()
            data = yaml.safe_load(content)
            host_entry = data["all"]["children"]["test"]["hosts"]["test-m1"]
            assert host_entry is None

    def test_host_with_ip_has_ansible_host(self):
        """Host with IP has ansible_host in inventory."""
        infra = _minimal_infra()
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            inv = Path(d) / "inventory" / "test.yml"
            data = yaml.safe_load(inv.read_text())
            assert data["all"]["children"]["test"]["hosts"]["test-m1"]["ansible_host"] == "10.100.1.10"

    def test_domain_appears_as_group(self):
        """Domain name is used as inventory group name."""
        infra = _minimal_infra()
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            inv = Path(d) / "inventory" / "test.yml"
            data = yaml.safe_load(inv.read_text())
            assert "test" in data["all"]["children"]


# ── PSOT: ephemeral edge cases ───────────────────────────────


class TestPSOTEphemeralEdgeCases:
    """Test ephemeral inheritance and override edge cases."""

    def test_all_machines_inherit_domain_true(self):
        """Machines inherit ephemeral=true from domain."""
        infra = _minimal_infra()
        infra["domains"]["test"]["ephemeral"] = True
        errors = validate(infra)
        assert errors == []
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            hv = Path(d) / "host_vars" / "test-m1.yml"
            data = yaml.safe_load(hv.read_text())
            assert data["instance_ephemeral"] is True

    def test_machine_overrides_domain_false(self):
        """Machine ephemeral=false overrides domain ephemeral=true."""
        infra = _minimal_infra()
        infra["domains"]["test"]["ephemeral"] = True
        infra["domains"]["test"]["machines"]["test-m1"]["ephemeral"] = False
        errors = validate(infra)
        assert errors == []
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            hv = Path(d) / "host_vars" / "test-m1.yml"
            data = yaml.safe_load(hv.read_text())
            assert data["instance_ephemeral"] is False

    def test_machine_overrides_domain_true(self):
        """Machine ephemeral=true overrides domain ephemeral=false (default)."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"]["test-m1"]["ephemeral"] = True
        errors = validate(infra)
        assert errors == []
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            hv = Path(d) / "host_vars" / "test-m1.yml"
            data = yaml.safe_load(hv.read_text())
            assert data["instance_ephemeral"] is True

    def test_ephemeral_in_group_vars(self):
        """Domain ephemeral flag appears in group_vars."""
        infra = _minimal_infra()
        infra["domains"]["test"]["ephemeral"] = True
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            gv = Path(d) / "group_vars" / "test.yml"
            data = yaml.safe_load(gv.read_text())
            assert data["domain_ephemeral"] is True


# ── PSOT: generate output file paths ────────────────────────


class TestPSOTGenerateOutputPaths:
    """Test that generate() creates the correct set of files."""

    def test_single_domain_creates_expected_files(self):
        """Single domain creates inventory, group_vars, host_vars."""
        infra = _minimal_infra()
        with tempfile.TemporaryDirectory() as d:
            files = generate(infra, d)
            # Should have: all.yml + inventory/test.yml + group_vars/test.yml + host_vars/test-m1.yml
            assert len(files) == 4
            paths = [str(f) for f in files]
            assert any("all.yml" in p for p in paths)
            assert any("inventory" in p and "test.yml" in p for p in paths)
            assert any("group_vars" in p and "test.yml" in p for p in paths)
            assert any("host_vars" in p and "test-m1.yml" in p for p in paths)

    def test_two_domains_create_expected_files(self):
        """Two domains create files for both."""
        infra = _minimal_infra()
        infra["domains"]["other"] = {
            "subnet_id": 2,
            "machines": {
                "other-m1": {"type": "lxc", "ip": "10.100.2.10"},
            },
        }
        with tempfile.TemporaryDirectory() as d:
            files = generate(infra, d)
            # all.yml + 2 inventory + 2 group_vars + 2 host_vars = 7
            assert len(files) == 7

    def test_domain_with_two_machines_creates_two_host_vars(self):
        """Domain with two machines creates two host_vars files."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"]["test-m2"] = {
            "type": "lxc", "ip": "10.100.1.20",
        }
        with tempfile.TemporaryDirectory() as d:
            files = generate(infra, d)
            host_vars = [f for f in files if "host_vars" in str(f)]
            assert len(host_vars) == 2


# ── PSOT: host_vars content validation ──────────────────────


class TestPSOTHostVarsContent:
    """Test the content of generated host_vars files."""

    def test_instance_type_lxc(self):
        """LXC type is written to host_vars."""
        infra = _minimal_infra()
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            hv = Path(d) / "host_vars" / "test-m1.yml"
            data = yaml.safe_load(hv.read_text())
            assert data["instance_type"] == "lxc"

    def test_instance_type_vm(self):
        """VM type is written to host_vars."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"]["test-m1"]["type"] = "vm"
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            hv = Path(d) / "host_vars" / "test-m1.yml"
            data = yaml.safe_load(hv.read_text())
            assert data["instance_type"] == "vm"

    def test_instance_domain(self):
        """Instance domain is written to host_vars."""
        infra = _minimal_infra()
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            hv = Path(d) / "host_vars" / "test-m1.yml"
            data = yaml.safe_load(hv.read_text())
            assert data["instance_domain"] == "test"

    def test_instance_ip(self):
        """Instance IP is written to host_vars."""
        infra = _minimal_infra()
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            hv = Path(d) / "host_vars" / "test-m1.yml"
            data = yaml.safe_load(hv.read_text())
            assert data["instance_ip"] == "10.100.1.10"

    def test_instance_os_image_from_global(self):
        """Instance os_image falls back to global default."""
        infra = _minimal_infra()
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            hv = Path(d) / "host_vars" / "test-m1.yml"
            data = yaml.safe_load(hv.read_text())
            assert data["instance_os_image"] == "images:debian/13"

    def test_instance_os_image_override(self):
        """Machine os_image overrides global default."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"]["test-m1"]["os_image"] = "images:ubuntu/24.04"
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            hv = Path(d) / "host_vars" / "test-m1.yml"
            data = yaml.safe_load(hv.read_text())
            assert data["instance_os_image"] == "images:ubuntu/24.04"

    def test_gpu_flag_in_host_vars(self):
        """GPU flag is written to host_vars."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"]["test-m1"]["gpu"] = True
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            hv = Path(d) / "host_vars" / "test-m1.yml"
            data = yaml.safe_load(hv.read_text())
            assert data["instance_gpu"] is True

    def test_config_in_host_vars(self):
        """Instance config is written to host_vars."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"]["test-m1"]["config"] = {
            "limits.cpu": "4", "limits.memory": "8GiB",
        }
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            hv = Path(d) / "host_vars" / "test-m1.yml"
            data = yaml.safe_load(hv.read_text())
            assert data["instance_config"]["limits.cpu"] == "4"
            assert data["instance_config"]["limits.memory"] == "8GiB"

    def test_roles_in_host_vars(self):
        """Instance roles are written to host_vars."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"]["test-m1"]["roles"] = ["base_system", "ollama_server"]
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            hv = Path(d) / "host_vars" / "test-m1.yml"
            data = yaml.safe_load(hv.read_text())
            assert data["instance_roles"] == ["base_system", "ollama_server"]


# ── PSOT: group_vars content validation ─────────────────────


class TestPSOTGroupVarsContent:
    """Test the content of generated group_vars files."""

    def test_domain_name_in_group_vars(self):
        """Domain name is written to group_vars."""
        infra = _minimal_infra()
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            gv = Path(d) / "group_vars" / "test.yml"
            data = yaml.safe_load(gv.read_text())
            assert data["domain_name"] == "test"

    def test_network_info_in_group_vars(self):
        """Network bridge info is written to group_vars."""
        infra = _minimal_infra()
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            gv = Path(d) / "group_vars" / "test.yml"
            data = yaml.safe_load(gv.read_text())
            assert data["incus_network"]["name"] == "net-test"
            assert data["incus_network"]["subnet"] == "10.100.1.0/24"
            assert data["incus_network"]["gateway"] == "10.100.1.254"

    def test_subnet_id_in_group_vars(self):
        """subnet_id is written to group_vars."""
        infra = _minimal_infra()
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            gv = Path(d) / "group_vars" / "test.yml"
            data = yaml.safe_load(gv.read_text())
            assert data["subnet_id"] == 1

    def test_profiles_in_group_vars(self):
        """Domain profiles are written to group_vars."""
        infra = _minimal_infra()
        infra["domains"]["test"]["profiles"] = {
            "nesting": {"config": {"security.nesting": "true"}},
        }
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            gv = Path(d) / "group_vars" / "test.yml"
            data = yaml.safe_load(gv.read_text())
            assert "incus_profiles" in data
            assert "nesting" in data["incus_profiles"]

    def test_project_name_in_all_yml(self):
        """project_name is written to group_vars/all.yml."""
        infra = _minimal_infra()
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            all_yml = Path(d) / "group_vars" / "all.yml"
            data = yaml.safe_load(all_yml.read_text())
            assert data["project_name"] == "edge-test"


# ── PSOT: orphan detection edge cases ───────────────────────


class TestPSOTOrphanDetection:
    """Test orphan detection with various file configurations."""

    def test_no_orphans_when_files_match(self):
        """No orphans when generated files match infra."""
        infra = _minimal_infra()
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            orphans = detect_orphans(infra, d)
            assert len(orphans) == 0

    def test_extra_inventory_file_is_orphan(self):
        """Extra inventory file not in infra is detected as orphan."""
        infra = _minimal_infra()
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            # Add an extra file
            extra = Path(d) / "inventory" / "deleted-domain.yml"
            extra.write_text("---\n# orphan\n")
            orphans = detect_orphans(infra, d)
            assert len(orphans) == 1
            assert "deleted-domain" in str(orphans[0][0])

    def test_extra_host_vars_file_is_orphan(self):
        """Extra host_vars file not in infra is detected as orphan."""
        infra = _minimal_infra()
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            extra = Path(d) / "host_vars" / "removed-machine.yml"
            extra.write_text("---\ninstance_ephemeral: true\n")
            orphans = detect_orphans(infra, d)
            assert len(orphans) >= 1
            assert any("removed-machine" in str(o[0]) for o in orphans)

    def test_orphan_with_ephemeral_false_is_protected(self):
        """Orphan file with instance_ephemeral: false is marked protected."""
        infra = _minimal_infra()
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            extra = Path(d) / "host_vars" / "protected-machine.yml"
            extra.write_text("---\ninstance_ephemeral: false\n")
            orphans = detect_orphans(infra, d)
            protected_orphans = [o for o in orphans if "protected-machine" in str(o[0])]
            assert len(protected_orphans) == 1
            assert protected_orphans[0][1] is True  # is_protected

    def test_orphan_with_ephemeral_true_not_protected(self):
        """Orphan file with instance_ephemeral: true is not protected."""
        infra = _minimal_infra()
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            extra = Path(d) / "host_vars" / "temp-machine.yml"
            extra.write_text("---\ninstance_ephemeral: true\n")
            orphans = detect_orphans(infra, d)
            temp_orphans = [o for o in orphans if "temp-machine" in str(o[0])]
            assert len(temp_orphans) == 1
            assert temp_orphans[0][1] is False  # not protected


# ── PSOT: enrich_infra edge cases ───────────────────────────


class TestPSOTEnrichEdgeCases:
    """Test enrich_infra with various configurations."""

    def test_enrich_firewall_vm_creates_sys_firewall(self):
        """enrich_infra creates sys-firewall when firewall_mode=vm."""
        infra = _minimal_infra()
        infra["global"]["firewall_mode"] = "vm"
        infra["domains"]["anklume"] = {
            "subnet_id": 0,
            "machines": {
                "anklume-ctrl": {"type": "lxc", "ip": "10.100.0.10"},
            },
        }
        enrich_infra(infra)
        assert "sys-firewall" in infra["domains"]["anklume"]["machines"]
        fw = infra["domains"]["anklume"]["machines"]["sys-firewall"]
        assert fw["type"] == "vm"
        assert fw["ip"] == "10.100.0.253"

    def test_enrich_does_not_overwrite_user_sys_firewall(self):
        """enrich_infra does not overwrite user-defined sys-firewall."""
        infra = _minimal_infra()
        infra["global"]["firewall_mode"] = "vm"
        infra["domains"]["anklume"] = {
            "subnet_id": 0,
            "machines": {
                "anklume-ctrl": {"type": "lxc", "ip": "10.100.0.10"},
                "sys-firewall": {
                    "type": "vm",
                    "ip": "10.100.0.200",
                    "config": {"limits.cpu": "8"},
                },
            },
        }
        enrich_infra(infra)
        fw = infra["domains"]["anklume"]["machines"]["sys-firewall"]
        assert fw["ip"] == "10.100.0.200"  # User's IP preserved
        assert fw["config"]["limits.cpu"] == "8"  # User's config preserved

    def test_enrich_ai_access_creates_policy(self):
        """enrich_infra creates AI access policy in exclusive mode."""
        infra = _minimal_infra()
        infra["global"]["ai_access_policy"] = "exclusive"
        infra["global"]["ai_access_default"] = "test"
        infra["domains"]["ai-tools"] = {
            "subnet_id": 10,
            "machines": {
                "gpu-server": {"type": "lxc", "ip": "10.100.10.10"},
            },
        }
        enrich_infra(infra)
        policies = infra.get("network_policies", [])
        assert len(policies) == 1
        assert policies[0]["to"] == "ai-tools"
        assert policies[0]["from"] == "test"

    def test_enrich_ai_access_does_not_duplicate(self):
        """enrich_infra does not add a second AI policy if one exists."""
        infra = _minimal_infra()
        infra["global"]["ai_access_policy"] = "exclusive"
        infra["global"]["ai_access_default"] = "test"
        infra["domains"]["ai-tools"] = {
            "subnet_id": 10,
            "machines": {"gpu-server": {"type": "lxc", "ip": "10.100.10.10"}},
        }
        infra["network_policies"] = [{
            "description": "Existing",
            "from": "test",
            "to": "ai-tools",
            "ports": "all",
            "bidirectional": True,
        }]
        enrich_infra(infra)
        ai_policies = [p for p in infra["network_policies"] if p.get("to") == "ai-tools"]
        assert len(ai_policies) == 1

    def test_enrich_host_mode_does_nothing(self):
        """enrich_infra does nothing when firewall_mode=host."""
        infra = _minimal_infra()
        infra["global"]["firewall_mode"] = "host"
        original_machines = dict(infra["domains"]["test"]["machines"])
        enrich_infra(infra)
        assert infra["domains"]["test"]["machines"] == original_machines

    def test_enrich_open_ai_policy_does_nothing(self):
        """enrich_infra does nothing when ai_access_policy=open."""
        infra = _minimal_infra()
        infra["global"]["ai_access_policy"] = "open"
        enrich_infra(infra)
        assert "network_policies" not in infra


# ── PSOT: validation error messages ─────────────────────────


class TestPSOTValidationErrors:
    """Test that validation produces correct and clear error messages."""

    def test_missing_project_name(self):
        """Missing project_name produces clear error."""
        infra = _minimal_infra()
        del infra["project_name"]
        errors = validate(infra)
        assert any("project_name" in e for e in errors)

    def test_missing_global(self):
        """Missing global section produces clear error."""
        infra = _minimal_infra()
        del infra["global"]
        errors = validate(infra)
        assert any("global" in e for e in errors)

    def test_missing_domains(self):
        """Missing domains section produces clear error."""
        infra = _minimal_infra()
        del infra["domains"]
        errors = validate(infra)
        assert any("domains" in e for e in errors)

    def test_duplicate_machine_name(self):
        """Duplicate machine name across domains produces error."""
        infra = _minimal_infra()
        infra["domains"]["other"] = {
            "subnet_id": 2,
            "machines": {
                "test-m1": {"type": "lxc", "ip": "10.100.2.10"},  # Same name as in test domain
            },
        }
        errors = validate(infra)
        assert any("duplicate" in e.lower() for e in errors)

    def test_duplicate_ip(self):
        """Duplicate IP across domains produces error."""
        infra = _minimal_infra()
        infra["domains"]["other"] = {
            "subnet_id": 2,
            "machines": {
                "other-m1": {"type": "lxc", "ip": "10.100.1.10"},  # Same IP as test-m1
            },
        }
        errors = validate(infra)
        assert any("IP" in e and "already used" in e for e in errors)

    def test_duplicate_subnet_id(self):
        """Duplicate subnet_id produces error."""
        infra = _minimal_infra()
        infra["domains"]["other"] = {
            "subnet_id": 1,  # Same as test domain
            "machines": {
                "other-m1": {"type": "lxc", "ip": "10.100.1.20"},
            },
        }
        errors = validate(infra)
        assert any("subnet_id 1 already used" in e for e in errors)

    def test_invalid_type(self):
        """Invalid machine type produces error."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"]["test-m1"]["type"] = "docker"
        errors = validate(infra)
        assert any("type must be 'lxc' or 'vm'" in e for e in errors)

    def test_invalid_gpu_policy(self):
        """Invalid gpu_policy produces error."""
        infra = _minimal_infra()
        infra["global"]["gpu_policy"] = "invalid"
        errors = validate(infra)
        assert any("gpu_policy must be" in e for e in errors)

    def test_invalid_firewall_mode(self):
        """Invalid firewall_mode produces error."""
        infra = _minimal_infra()
        infra["global"]["firewall_mode"] = "docker"
        errors = validate(infra)
        assert any("firewall_mode must be" in e for e in errors)

    def test_ephemeral_non_boolean_domain(self):
        """Non-boolean domain ephemeral produces error."""
        infra = _minimal_infra()
        infra["domains"]["test"]["ephemeral"] = "yes"
        errors = validate(infra)
        assert any("ephemeral must be a boolean" in e for e in errors)

    def test_ephemeral_non_boolean_machine(self):
        """Non-boolean machine ephemeral produces error."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"]["test-m1"]["ephemeral"] = "no"
        errors = validate(infra)
        assert any("ephemeral must be a boolean" in e for e in errors)


# ── PSOT: network policy validation ─────────────────────────


class TestPSOTNetworkPolicyValidation:
    """Test network policy validation edge cases."""

    def test_valid_policy_no_error(self):
        """Valid network policy produces no error."""
        infra = _minimal_infra()
        infra["network_policies"] = [{
            "description": "Valid",
            "from": "test",
            "to": "test",
            "ports": [80],
            "protocol": "tcp",
        }]
        errors = validate(infra)
        assert errors == []

    def test_policy_from_host_valid(self):
        """Policy with from=host is valid."""
        infra = _minimal_infra()
        infra["network_policies"] = [{
            "from": "host",
            "to": "test",
            "ports": [80],
            "protocol": "tcp",
        }]
        errors = validate(infra)
        assert errors == []

    def test_policy_unknown_from_rejected(self):
        """Policy with unknown 'from' domain is rejected."""
        infra = _minimal_infra()
        infra["network_policies"] = [{
            "from": "nonexistent",
            "to": "test",
            "ports": [80],
            "protocol": "tcp",
        }]
        errors = validate(infra)
        assert any("nonexistent" in e for e in errors)

    def test_policy_unknown_to_rejected(self):
        """Policy with unknown 'to' domain is rejected."""
        infra = _minimal_infra()
        infra["network_policies"] = [{
            "from": "test",
            "to": "nonexistent",
            "ports": [80],
            "protocol": "tcp",
        }]
        errors = validate(infra)
        assert any("nonexistent" in e for e in errors)

    def test_policy_invalid_port_zero(self):
        """Port 0 in policy is rejected."""
        infra = _minimal_infra()
        infra["network_policies"] = [{
            "from": "test",
            "to": "test",
            "ports": [0],
            "protocol": "tcp",
        }]
        errors = validate(infra)
        assert any("invalid port" in e for e in errors)

    def test_policy_invalid_port_too_high(self):
        """Port 65536 in policy is rejected."""
        infra = _minimal_infra()
        infra["network_policies"] = [{
            "from": "test",
            "to": "test",
            "ports": [65536],
            "protocol": "tcp",
        }]
        errors = validate(infra)
        assert any("invalid port" in e for e in errors)

    def test_policy_invalid_protocol(self):
        """Invalid protocol in policy is rejected."""
        infra = _minimal_infra()
        infra["network_policies"] = [{
            "from": "test",
            "to": "test",
            "ports": [80],
            "protocol": "icmp",
        }]
        errors = validate(infra)
        assert any("protocol must be 'tcp' or 'udp'" in e for e in errors)

    def test_policy_ports_all_is_valid(self):
        """Policy with ports='all' is valid."""
        infra = _minimal_infra()
        infra["network_policies"] = [{
            "from": "test",
            "to": "test",
            "ports": "all",
        }]
        errors = validate(infra)
        assert errors == []

    def test_policy_from_machine_name_valid(self):
        """Policy with from=machine_name is valid."""
        infra = _minimal_infra()
        infra["network_policies"] = [{
            "from": "test-m1",
            "to": "test",
            "ports": [80],
            "protocol": "tcp",
        }]
        errors = validate(infra)
        assert errors == []


# ── PSOT: AI access policy validation ───────────────────────


class TestPSOTAiAccessValidation:
    """Test AI access policy validation edge cases."""

    def test_exclusive_without_default_rejected(self):
        """exclusive without ai_access_default is rejected."""
        infra = _minimal_infra()
        infra["global"]["ai_access_policy"] = "exclusive"
        infra["domains"]["ai-tools"] = {
            "subnet_id": 10,
            "machines": {"ai-m": {"type": "lxc", "ip": "10.100.10.10"}},
        }
        errors = validate(infra)
        assert any("ai_access_default is required" in e for e in errors)

    def test_exclusive_default_is_ai_tools_rejected(self):
        """exclusive with ai_access_default=ai-tools is rejected."""
        infra = _minimal_infra()
        infra["global"]["ai_access_policy"] = "exclusive"
        infra["global"]["ai_access_default"] = "ai-tools"
        infra["domains"]["ai-tools"] = {
            "subnet_id": 10,
            "machines": {"ai-m": {"type": "lxc", "ip": "10.100.10.10"}},
        }
        errors = validate(infra)
        assert any("cannot be 'ai-tools'" in e for e in errors)

    def test_exclusive_without_ai_tools_domain_rejected(self):
        """exclusive without ai-tools domain is rejected."""
        infra = _minimal_infra()
        infra["global"]["ai_access_policy"] = "exclusive"
        infra["global"]["ai_access_default"] = "test"
        errors = validate(infra)
        assert any("no 'ai-tools' domain exists" in e for e in errors)

    def test_exclusive_valid_setup(self):
        """Valid exclusive setup passes validation."""
        infra = _minimal_infra()
        infra["global"]["ai_access_policy"] = "exclusive"
        infra["global"]["ai_access_default"] = "test"
        infra["domains"]["ai-tools"] = {
            "subnet_id": 10,
            "machines": {"ai-m": {"type": "lxc", "ip": "10.100.10.10"}},
        }
        errors = validate(infra)
        assert errors == []

    def test_open_policy_no_constraints(self):
        """open policy imposes no additional constraints."""
        infra = _minimal_infra()
        infra["global"]["ai_access_policy"] = "open"
        errors = validate(infra)
        assert errors == []

    def test_invalid_ai_policy_rejected(self):
        """Invalid ai_access_policy is rejected."""
        infra = _minimal_infra()
        infra["global"]["ai_access_policy"] = "custom"
        errors = validate(infra)
        assert any("ai_access_policy must be" in e for e in errors)


# ── PSOT: managed block content ─────────────────────────────


class TestPSOTManagedBlockContent:
    """Test _managed_block formatting."""

    def test_managed_block_has_begin_end(self):
        """Managed block contains BEGIN and END markers."""
        block = _managed_block("key: value\n")
        assert MANAGED_BEGIN in block
        assert MANAGED_END in block

    def test_managed_block_has_notice(self):
        """Managed block contains the do-not-edit notice."""
        block = _managed_block("key: value\n")
        assert "Do not edit this section" in block

    def test_managed_block_content_inside(self):
        """Managed block contains the provided YAML content."""
        block = _managed_block("my_key: my_value\n")
        assert "my_key: my_value" in block

    def test_managed_block_trailing_newline_stripped(self):
        """Managed block strips trailing whitespace from content."""
        block = _managed_block("key: value\n\n\n")
        # Should not have multiple newlines before END marker
        lines = block.split("\n")
        end_idx = next(i for i, ln in enumerate(lines) if MANAGED_END in ln)
        # Line before END should have content (not be blank)
        assert lines[end_idx - 1].strip() != ""


# ── PSOT: GPU policy edge cases ─────────────────────────────


class TestPSOTGPUPolicyEdgeCases:
    """Test GPU policy validation edge cases."""

    def test_zero_gpu_exclusive_ok(self):
        """No GPU instances in exclusive mode is fine."""
        infra = _minimal_infra()
        infra["global"]["gpu_policy"] = "exclusive"
        errors = validate(infra)
        assert errors == []

    def test_one_gpu_exclusive_ok(self):
        """One GPU instance in exclusive mode is fine."""
        infra = _minimal_infra()
        infra["global"]["gpu_policy"] = "exclusive"
        infra["domains"]["test"]["machines"]["test-m1"]["gpu"] = True
        errors = validate(infra)
        assert errors == []

    def test_two_gpu_exclusive_rejected(self):
        """Two GPU instances in exclusive mode are rejected."""
        infra = _minimal_infra()
        infra["global"]["gpu_policy"] = "exclusive"
        infra["domains"]["test"]["machines"]["test-m1"]["gpu"] = True
        infra["domains"]["test"]["machines"]["test-m2"] = {
            "type": "lxc", "ip": "10.100.1.20", "gpu": True,
        }
        errors = validate(infra)
        assert any("GPU policy is 'exclusive'" in e for e in errors)

    def test_two_gpu_shared_ok(self):
        """Two GPU instances in shared mode pass validation."""
        infra = _minimal_infra()
        infra["global"]["gpu_policy"] = "shared"
        infra["domains"]["test"]["machines"]["test-m1"]["gpu"] = True
        infra["domains"]["test"]["machines"]["test-m2"] = {
            "type": "lxc", "ip": "10.100.1.20", "gpu": True,
        }
        errors = validate(infra)
        assert errors == []


# ── YAML internal edge cases ────────────────────────────────


class TestYamlInternalEdgeCases:
    """Test _yaml() with edge case inputs."""

    def test_empty_list(self):
        """_yaml renders empty list correctly."""
        result = _yaml({"items": []})
        data = yaml.safe_load(result)
        assert data["items"] == []

    def test_nested_none(self):
        """_yaml handles nested None values."""
        result = _yaml({"outer": {"inner": None}})
        assert "null" not in result.lower()
        data = yaml.safe_load(result)
        assert data["outer"]["inner"] is None or data["outer"]["inner"] == ""

    def test_long_string(self):
        """_yaml handles long string values."""
        long_val = "x" * 200
        result = _yaml({"key": long_val})
        data = yaml.safe_load(result)
        assert data["key"] == long_val

    def test_special_yaml_chars(self):
        """_yaml handles values with special YAML characters."""
        result = _yaml({"key": "value: with colon"})
        data = yaml.safe_load(result)
        assert data["key"] == "value: with colon"

    def test_integer_values(self):
        """_yaml preserves integer values."""
        result = _yaml({"port": 8080, "count": 0})
        data = yaml.safe_load(result)
        assert data["port"] == 8080
        assert data["count"] == 0

    def test_float_values(self):
        """_yaml preserves float values."""
        result = _yaml({"ratio": 3.14})
        data = yaml.safe_load(result)
        assert abs(data["ratio"] - 3.14) < 0.001

    def test_roundtrip_consistency(self):
        """_yaml output can be parsed back to the same structure."""
        original = {
            "name": "test",
            "count": 42,
            "nested": {"a": 1, "b": 2},
            "items": ["x", "y", "z"],
        }
        result = _yaml(original)
        data = yaml.safe_load(result)
        assert data == original
