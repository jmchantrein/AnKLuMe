"""Edge case tests for generate.py — boundary conditions, malformed input, internal functions.

Tests cover:
- Validation boundary conditions (port numbers, subnet_id types, domain names)
- _write_managed with malformed managed sections
- _is_orphan_protected with various inputs
- Network policy edge cases
- _enrich_firewall and _enrich_ai_access edge paths
- extract_all_images edge cases
- _managed_block and _yaml internals
- Domain name edge cases
- IP edge cases
"""

import generate as gen_mod
import pytest
import yaml
from generate import (
    MANAGED_BEGIN,
    MANAGED_END,
    _is_orphan_protected,
    _managed_block,
    _write_managed,
    _yaml,
    detect_orphans,
    enrich_infra,
    extract_all_images,
    generate,
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
        },
        "domains": {
            "admin": {
                "description": "Administration",
                "subnet_id": 0,
                "machines": {
                    "admin-ctrl": {
                        "type": "lxc",
                        "ip": "10.100.0.10",
                        "roles": ["base_system"],
                    },
                },
            },
            "work": {
                "description": "Work",
                "subnet_id": 1,
                "machines": {
                    "dev-ws": {
                        "type": "lxc",
                        "ip": "10.100.1.10",
                    },
                },
            },
        },
    }


# ── Validation boundary conditions ──────────────────────────


class TestValidationBoundaries:
    """Boundary conditions for validate() function."""

    def test_subnet_id_zero_valid(self, sample_infra):
        """subnet_id=0 is the minimum valid value."""
        sample_infra["domains"]["admin"]["subnet_id"] = 0
        errors = validate(sample_infra)
        assert not any("subnet_id" in e and "0-254" in e for e in errors)

    def test_subnet_id_254_valid(self, sample_infra):
        """subnet_id=254 is the maximum valid value."""
        sample_infra["domains"]["work"]["subnet_id"] = 254
        errors = validate(sample_infra)
        assert not any("subnet_id" in e and "0-254" in e for e in errors)

    def test_subnet_id_255_invalid(self, sample_infra):
        """subnet_id=255 exceeds the valid range."""
        sample_infra["domains"]["work"]["subnet_id"] = 255
        errors = validate(sample_infra)
        assert any("0-254" in e for e in errors)

    def test_subnet_id_negative_invalid(self, sample_infra):
        """subnet_id=-1 is below the valid range."""
        sample_infra["domains"]["work"]["subnet_id"] = -1
        errors = validate(sample_infra)
        assert any("0-254" in e for e in errors)

    def test_subnet_id_string_invalid(self, sample_infra):
        """subnet_id as string is invalid (must be int)."""
        sample_infra["domains"]["work"]["subnet_id"] = "5"
        errors = validate(sample_infra)
        assert any("0-254" in e for e in errors)

    def test_subnet_id_float_invalid(self, sample_infra):
        """subnet_id as float is invalid (must be int)."""
        sample_infra["domains"]["work"]["subnet_id"] = 1.5
        errors = validate(sample_infra)
        assert any("0-254" in e for e in errors)

    def test_subnet_id_none_triggers_error(self, sample_infra):
        """subnet_id=None (missing) triggers error."""
        del sample_infra["domains"]["work"]["subnet_id"]
        errors = validate(sample_infra)
        assert any("missing subnet_id" in e for e in errors)

    def test_port_zero_invalid(self, sample_infra):
        """Port 0 is below the valid range (1-65535)."""
        sample_infra["network_policies"] = [
            {"from": "admin", "to": "work", "ports": [0]},
        ]
        errors = validate(sample_infra)
        assert any("invalid port 0" in e for e in errors)

    def test_port_one_valid(self, sample_infra):
        """Port 1 is the minimum valid port."""
        sample_infra["network_policies"] = [
            {"from": "admin", "to": "work", "ports": [1]},
        ]
        errors = validate(sample_infra)
        assert not any("invalid port" in e for e in errors)

    def test_port_65535_valid(self, sample_infra):
        """Port 65535 is the maximum valid port."""
        sample_infra["network_policies"] = [
            {"from": "admin", "to": "work", "ports": [65535]},
        ]
        errors = validate(sample_infra)
        assert not any("invalid port" in e for e in errors)

    def test_port_65536_invalid(self, sample_infra):
        """Port 65536 exceeds the valid range."""
        sample_infra["network_policies"] = [
            {"from": "admin", "to": "work", "ports": [65536]},
        ]
        errors = validate(sample_infra)
        assert any("invalid port" in e for e in errors)

    def test_port_negative_invalid(self, sample_infra):
        """Negative port number is invalid."""
        sample_infra["network_policies"] = [
            {"from": "admin", "to": "work", "ports": [-1]},
        ]
        errors = validate(sample_infra)
        assert any("invalid port" in e for e in errors)

    def test_port_string_in_list_invalid(self, sample_infra):
        """Port as string in a list is invalid."""
        sample_infra["network_policies"] = [
            {"from": "admin", "to": "work", "ports": ["80"]},
        ]
        errors = validate(sample_infra)
        assert any("invalid port" in e for e in errors)

    def test_ports_none_accepted(self, sample_infra):
        """Omitting ports is acceptable (no error)."""
        sample_infra["network_policies"] = [
            {"from": "admin", "to": "work"},
        ]
        errors = validate(sample_infra)
        assert not any("port" in e for e in errors)

    def test_protocol_none_accepted(self, sample_infra):
        """Omitting protocol is acceptable (no error)."""
        sample_infra["network_policies"] = [
            {"from": "admin", "to": "work", "ports": [22]},
        ]
        errors = validate(sample_infra)
        assert not any("protocol" in e for e in errors)

    def test_multiple_valid_ports(self, sample_infra):
        """Multiple valid ports in a single policy."""
        sample_infra["network_policies"] = [
            {"from": "admin", "to": "work", "ports": [22, 80, 443, 8080]},
        ]
        errors = validate(sample_infra)
        assert not any("port" in e for e in errors)

    def test_mixed_valid_invalid_ports(self, sample_infra):
        """Mix of valid and invalid ports produces errors for invalid ones."""
        sample_infra["network_policies"] = [
            {"from": "admin", "to": "work", "ports": [22, 0, 443, 99999]},
        ]
        errors = validate(sample_infra)
        port_errors = [e for e in errors if "invalid port" in e]
        assert len(port_errors) == 2  # port 0 and port 99999


# ── Domain name edge cases ──────────────────────────────────


class TestDomainNameEdgeCases:
    """Edge cases for domain name validation."""

    def test_single_char_domain(self, sample_infra):
        """Single lowercase character is a valid domain name."""
        sample_infra["domains"]["x"] = {
            "subnet_id": 50, "machines": {},
        }
        errors = validate(sample_infra)
        assert not any("invalid name" in e for e in errors)

    def test_numeric_domain(self, sample_infra):
        """All-numeric domain name is valid."""
        sample_infra["domains"]["123"] = {
            "subnet_id": 50, "machines": {},
        }
        errors = validate(sample_infra)
        assert not any("invalid name" in e for e in errors)

    def test_domain_with_hyphens(self, sample_infra):
        """Domain with hyphens (not leading) is valid."""
        sample_infra["domains"]["my-domain-1"] = {
            "subnet_id": 50, "machines": {},
        }
        errors = validate(sample_infra)
        assert not any("invalid name" in e for e in errors)

    def test_domain_starting_with_hyphen_invalid(self, sample_infra):
        """Domain starting with hyphen is invalid."""
        sample_infra["domains"]["-bad"] = {
            "subnet_id": 50, "machines": {},
        }
        errors = validate(sample_infra)
        assert any("invalid name" in e for e in errors)

    def test_domain_uppercase_invalid(self, sample_infra):
        """Domain with uppercase is invalid."""
        sample_infra["domains"]["MyDomain"] = {
            "subnet_id": 50, "machines": {},
        }
        errors = validate(sample_infra)
        assert any("invalid name" in e for e in errors)

    def test_domain_with_underscore_invalid(self, sample_infra):
        """Domain with underscore is invalid."""
        sample_infra["domains"]["my_domain"] = {
            "subnet_id": 50, "machines": {},
        }
        errors = validate(sample_infra)
        assert any("invalid name" in e for e in errors)

    def test_domain_with_dot_invalid(self, sample_infra):
        """Domain with dot is invalid."""
        sample_infra["domains"]["my.domain"] = {
            "subnet_id": 50, "machines": {},
        }
        errors = validate(sample_infra)
        assert any("invalid name" in e for e in errors)

    def test_domain_with_space_invalid(self, sample_infra):
        """Domain with space is invalid."""
        sample_infra["domains"]["my domain"] = {
            "subnet_id": 50, "machines": {},
        }
        errors = validate(sample_infra)
        assert any("invalid name" in e for e in errors)


# ── _write_managed edge cases ─────────────────────────────


class TestWriteManaged:
    """Edge cases for _write_managed internal function."""

    def test_new_file_creation(self, tmp_path):
        """_write_managed creates new file with managed section."""
        fp, content = _write_managed(tmp_path / "new.yml", {"key": "value"})
        assert fp.exists()
        assert MANAGED_BEGIN in content
        assert MANAGED_END in content
        assert "key: value" in content
        assert "Your custom variables below" in content

    def test_existing_file_with_managed_section(self, tmp_path):
        """_write_managed replaces only the managed section in existing file."""
        f = tmp_path / "existing.yml"
        f.write_text(
            f"---\n{MANAGED_BEGIN}\n# Do not edit\nold_key: old\n{MANAGED_END}\n\n"
            "custom_var: keep_this\n"
        )
        _, content = _write_managed(f, {"new_key": "new_value"})
        assert "new_key: new_value" in content
        assert "old_key" not in content
        assert "custom_var: keep_this" in content

    def test_existing_file_without_managed_section(self, tmp_path):
        """_write_managed prepends managed block to file without one."""
        f = tmp_path / "plain.yml"
        f.write_text("existing_var: hello\n")
        _, content = _write_managed(f, {"new_key": "new_value"})
        assert MANAGED_BEGIN in content
        assert "new_key: new_value" in content
        assert "existing_var: hello" in content
        # Managed section should be before the existing content
        managed_pos = content.index(MANAGED_BEGIN)
        existing_pos = content.index("existing_var")
        assert managed_pos < existing_pos

    def test_existing_file_starting_with_yaml_doc_marker(self, tmp_path):
        """File starting with --- does not get an extra --- prefix."""
        f = tmp_path / "yamlstart.yml"
        f.write_text("---\nexisting_var: hello\n")
        _, content = _write_managed(f, {"key": "val"})
        # Should not have double ---
        assert content.count("---") == 1

    def test_existing_file_not_starting_with_yaml_doc_marker(self, tmp_path):
        """File not starting with --- gets one prepended."""
        f = tmp_path / "noyaml.yml"
        f.write_text("existing_var: hello\n")
        _, content = _write_managed(f, {"key": "val"})
        assert content.startswith("---\n")

    def test_dry_run_does_not_write(self, tmp_path):
        """_write_managed with dry_run=True does not create the file."""
        fp, content = _write_managed(tmp_path / "dryrun.yml", {"k": "v"}, dry_run=True)
        assert not fp.exists()
        assert MANAGED_BEGIN in content

    def test_creates_parent_directories(self, tmp_path):
        """_write_managed creates parent directories if needed."""
        fp, _ = _write_managed(tmp_path / "sub" / "dir" / "file.yml", {"k": "v"})
        assert fp.exists()
        assert (tmp_path / "sub" / "dir").is_dir()

    def test_managed_section_replaced_not_duplicated(self, tmp_path):
        """Re-running _write_managed does not duplicate managed sections."""
        f = tmp_path / "rerun.yml"
        _write_managed(f, {"first": "run"})
        _write_managed(f, {"second": "run"})
        content = f.read_text()
        assert content.count(MANAGED_BEGIN) == 1
        assert content.count(MANAGED_END) == 1
        assert "second: run" in content
        assert "first" not in content

    def test_none_value_in_dict(self, tmp_path):
        """_write_managed handles None values in content dict."""
        _, content = _write_managed(tmp_path / "none.yml", {"key": None})
        assert "key:" in content

    def test_empty_dict(self, tmp_path):
        """_write_managed handles empty dict."""
        fp, content = _write_managed(tmp_path / "empty.yml", {})
        assert fp.exists()
        assert MANAGED_BEGIN in content

    def test_nested_dict(self, tmp_path):
        """_write_managed handles nested dict structures."""
        _, content = _write_managed(tmp_path / "nested.yml", {
            "outer": {"inner": "value", "list": [1, 2, 3]},
        })
        assert "inner: value" in content

    def test_special_yaml_characters(self, tmp_path):
        """_write_managed handles YAML special characters in values."""
        _, content = _write_managed(tmp_path / "special.yml", {
            "desc": "value with: colon and [brackets]",
        })
        assert "colon" in content


# ── _is_orphan_protected edge cases ───────────────────────


class TestIsOrphanProtected:
    """Edge cases for _is_orphan_protected."""

    def test_domain_ephemeral_false_is_protected(self, tmp_path):
        """File with domain_ephemeral: false is protected."""
        f = tmp_path / "test.yml"
        f.write_text("domain_ephemeral: false\n")
        assert _is_orphan_protected(f) is True

    def test_domain_ephemeral_true_not_protected(self, tmp_path):
        """File with domain_ephemeral: true is not protected."""
        f = tmp_path / "test.yml"
        f.write_text("domain_ephemeral: true\n")
        assert _is_orphan_protected(f) is False

    def test_instance_ephemeral_false_is_protected(self, tmp_path):
        """File with instance_ephemeral: false is protected."""
        f = tmp_path / "test.yml"
        f.write_text("instance_ephemeral: false\n")
        assert _is_orphan_protected(f) is True

    def test_instance_ephemeral_true_not_protected(self, tmp_path):
        """File with instance_ephemeral: true is not protected."""
        f = tmp_path / "test.yml"
        f.write_text("instance_ephemeral: true\n")
        assert _is_orphan_protected(f) is False

    def test_no_ephemeral_key_not_protected(self, tmp_path):
        """File without ephemeral key is not protected."""
        f = tmp_path / "test.yml"
        f.write_text("some_key: some_value\n")
        assert _is_orphan_protected(f) is False

    def test_empty_file_not_protected(self, tmp_path):
        """Empty file is not protected."""
        f = tmp_path / "test.yml"
        f.write_text("")
        assert _is_orphan_protected(f) is False

    def test_invalid_yaml_not_protected(self, tmp_path):
        """Invalid YAML file is not protected (graceful handling)."""
        f = tmp_path / "test.yml"
        f.write_text("not: [valid: yaml: {]")
        assert _is_orphan_protected(f) is False

    def test_list_yaml_not_protected(self, tmp_path):
        """YAML file with list (not dict) is not protected."""
        f = tmp_path / "test.yml"
        f.write_text("- item1\n- item2\n")
        assert _is_orphan_protected(f) is False

    def test_nonexistent_file_not_protected(self, tmp_path):
        """Nonexistent file is not protected."""
        assert _is_orphan_protected(tmp_path / "nonexistent.yml") is False

    def test_both_ephemeral_keys_domain_takes_precedence(self, tmp_path):
        """When both domain_ephemeral and instance_ephemeral exist, domain is checked first."""
        f = tmp_path / "test.yml"
        f.write_text("domain_ephemeral: false\ninstance_ephemeral: true\n")
        # domain_ephemeral is checked first in the loop
        assert _is_orphan_protected(f) is True


# ── _yaml and _managed_block internals ────────────────────


class TestYamlInternals:
    """Tests for _yaml() and _managed_block() internal functions."""

    def test_yaml_none_as_empty(self):
        """_yaml renders None as empty string."""
        result = _yaml({"key": None})
        assert "key:" in result
        assert "null" not in result

    def test_yaml_preserves_order(self):
        """_yaml preserves dict insertion order."""
        result = _yaml({"zebra": 1, "alpha": 2, "middle": 3})
        lines = result.strip().split("\n")
        assert lines[0].startswith("zebra")
        assert lines[1].startswith("alpha")
        assert lines[2].startswith("middle")

    def test_yaml_list_indent(self):
        """_yaml uses proper list indentation."""
        result = _yaml({"items": [1, 2, 3]})
        assert "- 1" in result

    def test_yaml_unicode(self):
        """_yaml handles unicode characters."""
        result = _yaml({"desc": "Réseau privé"})
        assert "Réseau privé" in result

    def test_managed_block_structure(self):
        """_managed_block produces correct BEGIN/END markers."""
        block = _managed_block("key: value\n")
        assert block.startswith(MANAGED_BEGIN)
        assert block.endswith(MANAGED_END)
        assert "Do not edit" in block
        assert "key: value" in block

    def test_managed_block_strips_trailing_newlines(self):
        """_managed_block strips trailing newlines from content."""
        block = _managed_block("key: value\n\n\n")
        # Should not have extra blank lines before END marker
        lines = block.split("\n")
        assert lines[-2] == "key: value"
        assert lines[-1] == MANAGED_END


# ── Network policy edge cases ──────────────────────────────


class TestNetworkPolicyEdgeCases:
    """Additional edge cases for network policy validation."""

    def test_non_dict_policy_rejected(self, sample_infra):
        """Non-dict entry in network_policies triggers error."""
        sample_infra["network_policies"] = ["not a dict"]
        errors = validate(sample_infra)
        assert any("must be a mapping" in e for e in errors)

    def test_null_policy_entry_rejected(self, sample_infra):
        """None entry in network_policies triggers error."""
        sample_infra["network_policies"] = [None]
        errors = validate(sample_infra)
        assert any("must be a mapping" in e for e in errors)

    def test_multiple_policies_valid(self, sample_infra):
        """Multiple valid policies in a single list."""
        sample_infra["network_policies"] = [
            {"from": "admin", "to": "work", "ports": [22], "protocol": "tcp"},
            {"from": "work", "to": "admin", "ports": [443], "protocol": "tcp"},
            {"from": "host", "to": "work", "ports": "all"},
        ]
        errors = validate(sample_infra)
        assert not any("network_policies" in e for e in errors)

    def test_policy_from_machine_to_machine(self, sample_infra):
        """Policy between two machines (not domains) is valid."""
        sample_infra["network_policies"] = [
            {"from": "admin-ctrl", "to": "dev-ws", "ports": [22]},
        ]
        errors = validate(sample_infra)
        assert not any("network_policies" in e for e in errors)

    def test_policy_with_description(self, sample_infra):
        """Policy with description field is valid (description ignored)."""
        sample_infra["network_policies"] = [
            {"description": "Allow SSH", "from": "admin", "to": "work", "ports": [22]},
        ]
        errors = validate(sample_infra)
        assert not any("network_policies" in e for e in errors)

    def test_multiple_errors_in_single_policy(self, sample_infra):
        """Policy with multiple errors reports all of them."""
        sample_infra["network_policies"] = [
            {"from": "unknown-src", "to": "unknown-dst", "ports": [0], "protocol": "icmp"},
        ]
        errors = validate(sample_infra)
        # Should have: unknown from, unknown to, invalid port, invalid protocol
        assert len([e for e in errors if "network_policies" in e]) >= 3


# ── enrich_infra edge cases ────────────────────────────────


class TestEnrichEdgeCases:
    """Edge cases for enrich_infra and its sub-functions."""

    def test_enrich_firewall_host_mode_noop(self, sample_infra):
        """enrich_infra is a no-op when firewall_mode is 'host' (default)."""
        original_machines = dict(sample_infra["domains"]["admin"]["machines"])
        enrich_infra(sample_infra)
        assert sample_infra["domains"]["admin"]["machines"] == original_machines

    def test_enrich_ai_access_open_mode_noop(self, sample_infra):
        """enrich_infra is a no-op for AI when ai_access_policy is 'open' (default)."""
        enrich_infra(sample_infra)
        assert "network_policies" not in sample_infra

    def test_enrich_ai_access_no_default_noop(self, sample_infra):
        """enrich_infra AI does nothing when ai_access_default is missing."""
        sample_infra["global"]["ai_access_policy"] = "exclusive"
        sample_infra["domains"]["ai-tools"] = {
            "subnet_id": 10, "machines": {},
        }
        # No ai_access_default set
        enrich_infra(sample_infra)
        assert "network_policies" not in sample_infra

    def test_enrich_ai_access_no_ai_tools_domain_noop(self, sample_infra):
        """enrich_infra AI does nothing when ai-tools domain is missing."""
        sample_infra["global"]["ai_access_policy"] = "exclusive"
        sample_infra["global"]["ai_access_default"] = "work"
        # No ai-tools domain
        enrich_infra(sample_infra)
        assert "network_policies" not in sample_infra

    def test_enrich_firewall_vm_null_machines(self, sample_infra):
        """enrich_infra handles admin domain with null machines."""
        sample_infra["global"]["firewall_mode"] = "vm"
        sample_infra["domains"]["admin"]["machines"] = None
        enrich_infra(sample_infra)
        assert "sys-firewall" in sample_infra["domains"]["admin"]["machines"]

    def test_enrich_firewall_sys_firewall_in_other_domain(self, sample_infra):
        """sys-firewall in a non-admin domain prevents auto-creation."""
        sample_infra["global"]["firewall_mode"] = "vm"
        sample_infra["domains"]["work"]["machines"]["sys-firewall"] = {
            "type": "vm", "ip": "10.100.1.253",
        }
        enrich_infra(sample_infra)
        # Should not auto-create in admin since sys-firewall exists
        assert "sys-firewall" not in sample_infra["domains"]["admin"]["machines"]

    def test_enrich_ai_auto_created_policy_is_bidirectional(self, sample_infra):
        """Auto-created AI policy has bidirectional: true and ports: all."""
        sample_infra["global"]["ai_access_policy"] = "exclusive"
        sample_infra["global"]["ai_access_default"] = "work"
        sample_infra["domains"]["ai-tools"] = {
            "subnet_id": 10, "machines": {"ai-srv": {"type": "lxc", "ip": "10.100.10.10"}},
        }
        enrich_infra(sample_infra)
        policies = sample_infra.get("network_policies", [])
        ai_policy = next(p for p in policies if p.get("to") == "ai-tools")
        assert ai_policy["bidirectional"] is True
        assert ai_policy["ports"] == "all"
        assert ai_policy["from"] == "work"


# ── extract_all_images edge cases ───────────────────────────


class TestExtractImagesEdgeCases:
    """Edge cases for extract_all_images."""

    def test_no_domains(self):
        """No domains produces empty image list."""
        infra = {"project_name": "t", "global": {"default_os_image": "img:x"}, "domains": {}}
        assert extract_all_images(infra) == []

    def test_none_domains(self):
        """domains: null produces empty image list."""
        infra = {"project_name": "t", "global": {"default_os_image": "img:x"}, "domains": None}
        assert extract_all_images(infra) == []

    def test_none_machines(self):
        """Domain with machines: null produces no images from machines."""
        infra = {
            "project_name": "t",
            "global": {"default_os_image": "img:x"},
            "domains": {"d": {"subnet_id": 0, "machines": None}},
        }
        assert extract_all_images(infra) == []

    def test_machine_overrides_default_image(self):
        """Machine with os_image overrides global default."""
        infra = {
            "project_name": "t",
            "global": {"default_os_image": "img:default"},
            "domains": {"d": {"subnet_id": 0, "machines": {
                "m": {"type": "lxc", "os_image": "img:custom"},
            }}},
        }
        images = extract_all_images(infra)
        assert "img:custom" in images
        assert "img:default" not in images

    def test_images_are_sorted(self):
        """Extracted images are sorted alphabetically."""
        infra = {
            "project_name": "t",
            "global": {},
            "domains": {"d": {"subnet_id": 0, "machines": {
                "m1": {"type": "lxc", "os_image": "img:z"},
                "m2": {"type": "lxc", "os_image": "img:a"},
                "m3": {"type": "lxc", "os_image": "img:m"},
            }}},
        }
        images = extract_all_images(infra)
        assert images == ["img:a", "img:m", "img:z"]

    def test_no_global_no_machine_image(self):
        """No default_os_image and no machine os_image produces empty list."""
        infra = {
            "project_name": "t",
            "global": {},
            "domains": {"d": {"subnet_id": 0, "machines": {"m": {"type": "lxc"}}}},
        }
        assert extract_all_images(infra) == []


# ── detect_orphans edge cases ───────────────────────────────


class TestDetectOrphansEdgeCases:
    """Edge cases for detect_orphans."""

    def test_no_orphans_when_dirs_dont_exist(self, sample_infra, tmp_path):
        """No orphans when output directories don't exist."""
        orphans = detect_orphans(sample_infra, tmp_path)
        assert orphans == []

    def test_orphan_in_inventory_only(self, sample_infra, tmp_path):
        """Orphan only in inventory/ is detected."""
        generate(sample_infra, tmp_path)
        (tmp_path / "inventory" / "old.yml").write_text("orphan")
        orphans = detect_orphans(sample_infra, tmp_path)
        orphan_names = [o[0].stem for o in orphans]
        assert "old" in orphan_names

    def test_orphan_in_host_vars_only(self, sample_infra, tmp_path):
        """Orphan only in host_vars/ is detected."""
        generate(sample_infra, tmp_path)
        (tmp_path / "host_vars" / "deleted-machine.yml").write_text("orphan")
        orphans = detect_orphans(sample_infra, tmp_path)
        orphan_names = [o[0].stem for o in orphans]
        assert "deleted-machine" in orphan_names

    def test_empty_domains_everything_is_orphan(self, tmp_path):
        """With empty domains, all existing files are orphans."""
        infra = {"project_name": "t", "global": {}, "domains": {}}
        (tmp_path / "inventory").mkdir()
        (tmp_path / "inventory" / "old.yml").write_text("x")
        (tmp_path / "group_vars").mkdir()
        (tmp_path / "group_vars" / "all.yml").write_text("x")
        orphans = detect_orphans(infra, tmp_path)
        # "all" is always valid, so only "old" in inventory is an orphan
        assert len(orphans) == 1


# ── load_infra edge cases ───────────────────────────────────


class TestLoadInfraEdgeCases:
    """Edge cases for load_infra function."""

    def test_load_nonexistent_file(self, tmp_path):
        """load_infra raises FileNotFoundError for nonexistent file."""
        with pytest.raises(FileNotFoundError):
            load_infra(tmp_path / "nonexistent.yml")

    def test_load_empty_yaml(self, tmp_path):
        """load_infra returns None for empty YAML file."""
        f = tmp_path / "empty.yml"
        f.write_text("")
        result = load_infra(f)
        assert result is None

    def test_load_yaml_with_only_comments(self, tmp_path):
        """load_infra returns None for YAML file with only comments."""
        f = tmp_path / "comments.yml"
        f.write_text("# Just a comment\n# Another comment\n")
        result = load_infra(f)
        assert result is None

    def test_load_dir_with_empty_domains_dir(self, tmp_path):
        """Directory mode with no domain files yields empty domains."""
        d = tmp_path / "infra"
        d.mkdir()
        (d / "domains").mkdir()
        (d / "base.yml").write_text(yaml.dump({
            "project_name": "test", "global": {"base_subnet": "10.100"},
        }))
        result = load_infra(d)
        assert result.get("domains", {}) == {}

    def test_load_dir_without_policies(self, tmp_path):
        """Directory mode without policies.yml works fine."""
        d = tmp_path / "infra"
        d.mkdir()
        (d / "domains").mkdir()
        (d / "base.yml").write_text(yaml.dump({
            "project_name": "test", "global": {"base_subnet": "10.100"},
        }))
        result = load_infra(d)
        assert "network_policies" not in result


# ── generate edge cases ───────────────────────────────────


class TestGenerateEdgeCases:
    """Edge cases for generate() function."""

    def test_domain_without_machines_key(self, tmp_path):
        """Domain without 'machines' key generates inventory and group_vars."""
        infra = {
            "project_name": "t",
            "global": {"base_subnet": "10.100"},
            "domains": {"empty": {"subnet_id": 5}},
        }
        generate(infra, tmp_path)
        assert (tmp_path / "inventory" / "empty.yml").exists()
        assert (tmp_path / "group_vars" / "empty.yml").exists()

    def test_domain_with_none_machines(self, tmp_path):
        """Domain with machines: null generates no host_vars."""
        infra = {
            "project_name": "t",
            "global": {"base_subnet": "10.100"},
            "domains": {"d": {"subnet_id": 0, "machines": None}},
        }
        generate(infra, tmp_path)
        assert not (tmp_path / "host_vars").exists() or not list(
            (tmp_path / "host_vars").glob("*.yml")
        )

    def test_machine_minimal_fields(self, tmp_path):
        """Machine with only type generates minimal host_vars."""
        infra = {
            "project_name": "t",
            "global": {"base_subnet": "10.100"},
            "domains": {"d": {"subnet_id": 0, "machines": {
                "m": {"type": "lxc"},
            }}},
        }
        generate(infra, tmp_path)
        content = (tmp_path / "host_vars" / "m.yml").read_text()
        assert "instance_name: m" in content
        assert "instance_type: lxc" in content
        assert "instance_domain: d" in content

    def test_no_domains_returns_empty_list(self, tmp_path):
        """generate() with empty domains returns empty file list."""
        infra = {
            "project_name": "t",
            "global": {"base_subnet": "10.100"},
            "domains": {},
        }
        # Still writes group_vars/all.yml
        written = generate(infra, tmp_path)
        assert len(written) == 1  # only group_vars/all.yml

    def test_machine_with_all_optional_fields(self, tmp_path):
        """Machine with all optional fields generates complete host_vars."""
        infra = {
            "project_name": "t",
            "global": {"base_subnet": "10.100", "default_os_image": "img:d"},
            "domains": {"d": {
                "subnet_id": 0,
                "profiles": {"gpu": {"devices": {"g": {"type": "gpu"}}}},
                "machines": {"m": {
                    "type": "vm",
                    "description": "Full machine",
                    "ip": "10.100.0.10",
                    "os_image": "img:custom",
                    "gpu": True,
                    "ephemeral": True,
                    "profiles": ["default", "gpu"],
                    "config": {"limits.cpu": "4"},
                    "devices": {"disk": {"type": "disk"}},
                    "storage_volumes": {"data": {"size": "10GiB"}},
                    "roles": ["base_system", "ollama_server"],
                }},
            }},
        }
        generate(infra, tmp_path)
        content = (tmp_path / "host_vars" / "m.yml").read_text()
        for expected in [
            "instance_name: m",
            "instance_type: vm",
            "instance_description: Full machine",
            "instance_ip: 10.100.0.10",
            "instance_os_image: img:custom",
            "instance_gpu: true",
            "instance_ephemeral: true",
            "instance_config",
            "instance_devices",
            "instance_storage_volumes",
            "instance_roles",
        ]:
            assert expected in content, f"Missing: {expected}"

    def test_network_policies_not_in_all_when_empty(self, sample_infra, tmp_path):
        """network_policies key absent from all.yml when policies are empty list."""
        sample_infra["network_policies"] = []
        generate(sample_infra, tmp_path)
        content = (tmp_path / "group_vars" / "all.yml").read_text()
        # Empty list is falsy, so it should be filtered out
        assert "network_policies" not in content

    def test_no_connection_vars_leak(self, tmp_path):
        """Connection params stored as psot_* only, never as ansible_*."""
        infra = {
            "project_name": "t",
            "global": {
                "base_subnet": "10.100",
                "default_connection": "community.general.incus",
                "default_user": "root",
            },
            "domains": {"d": {"subnet_id": 0, "machines": {"m": {"type": "lxc"}}}},
        }
        generate(infra, tmp_path)
        for f in tmp_path.rglob("*.yml"):
            content = f.read_text()
            assert "ansible_connection" not in content
            assert "ansible_user" not in content


# ── Privileged policy string boolean edge cases ─────────────


class TestPrivilegedStringBooleans:
    """Test security.privileged with various boolean-like string values."""

    def _make_privileged_config(self, sample_infra, value):
        sample_infra["domains"]["admin"]["machines"]["admin-ctrl"]["config"] = {
            "security.privileged": value,
        }

    def test_privileged_string_true(self, sample_infra, monkeypatch):
        """security.privileged='true' (string) is detected as privileged."""
        monkeypatch.setattr(gen_mod, "_read_vm_nested", lambda: False)
        monkeypatch.setattr(gen_mod, "_read_yolo", lambda: False)
        self._make_privileged_config(sample_infra, "true")
        errors = validate(sample_infra)
        assert any("privileged" in e for e in errors)

    def test_privileged_string_all_caps(self, sample_infra, monkeypatch):
        """security.privileged='TRUE' (uppercase) is detected as privileged."""
        monkeypatch.setattr(gen_mod, "_read_vm_nested", lambda: False)
        monkeypatch.setattr(gen_mod, "_read_yolo", lambda: False)
        self._make_privileged_config(sample_infra, "TRUE")
        errors = validate(sample_infra)
        assert any("privileged" in e for e in errors)

    def test_privileged_string_capitalized(self, sample_infra, monkeypatch):
        """security.privileged='True' (capitalized) is detected as privileged."""
        monkeypatch.setattr(gen_mod, "_read_vm_nested", lambda: False)
        monkeypatch.setattr(gen_mod, "_read_yolo", lambda: False)
        self._make_privileged_config(sample_infra, "True")
        errors = validate(sample_infra)
        assert any("privileged" in e for e in errors)

    def test_privileged_bool_true(self, sample_infra, monkeypatch):
        """security.privileged=True (Python bool) is detected as privileged."""
        monkeypatch.setattr(gen_mod, "_read_vm_nested", lambda: False)
        monkeypatch.setattr(gen_mod, "_read_yolo", lambda: False)
        self._make_privileged_config(sample_infra, True)
        errors = validate(sample_infra)
        assert any("privileged" in e for e in errors)

    def test_privileged_string_false(self, sample_infra, monkeypatch):
        """security.privileged='false' is not detected as privileged."""
        monkeypatch.setattr(gen_mod, "_read_vm_nested", lambda: False)
        monkeypatch.setattr(gen_mod, "_read_yolo", lambda: False)
        self._make_privileged_config(sample_infra, "false")
        errors = validate(sample_infra)
        assert not any("privileged" in e for e in errors)

    def test_privileged_absent_not_privileged(self, sample_infra, monkeypatch):
        """Missing security.privileged config is not privileged."""
        monkeypatch.setattr(gen_mod, "_read_vm_nested", lambda: False)
        monkeypatch.setattr(gen_mod, "_read_yolo", lambda: False)
        sample_infra["domains"]["admin"]["machines"]["admin-ctrl"]["config"] = {}
        errors = validate(sample_infra)
        assert not any("privileged" in e for e in errors)

    def test_privileged_none_config_not_privileged(self, sample_infra, monkeypatch):
        """Machine with config=None is not privileged."""
        monkeypatch.setattr(gen_mod, "_read_vm_nested", lambda: False)
        monkeypatch.setattr(gen_mod, "_read_yolo", lambda: False)
        sample_infra["domains"]["admin"]["machines"]["admin-ctrl"]["config"] = None
        errors = validate(sample_infra)
        assert not any("privileged" in e for e in errors)

    def test_privileged_no_config_key_not_privileged(self, sample_infra, monkeypatch):
        """Machine without config key at all is not privileged."""
        monkeypatch.setattr(gen_mod, "_read_vm_nested", lambda: False)
        monkeypatch.setattr(gen_mod, "_read_yolo", lambda: False)
        sample_infra["domains"]["admin"]["machines"]["admin-ctrl"].pop("config", None)
        errors = validate(sample_infra)
        assert not any("privileged" in e for e in errors)


# ── IP edge cases ────────────────────────────────────────────


class TestIPEdgeCases:
    """Edge cases for IP address validation."""

    def test_ip_host_part_one(self, sample_infra):
        """IP with host part .1 is valid."""
        sample_infra["domains"]["admin"]["machines"]["admin-ctrl"]["ip"] = "10.100.0.1"
        errors = validate(sample_infra)
        assert not any("not in subnet" in e for e in errors)

    def test_ip_host_part_253(self, sample_infra):
        """IP with host part .253 is valid."""
        sample_infra["domains"]["admin"]["machines"]["admin-ctrl"]["ip"] = "10.100.0.253"
        errors = validate(sample_infra)
        assert not any("not in subnet" in e for e in errors)

    def test_ip_host_part_254_gateway(self, sample_infra):
        """IP .254 (gateway) is technically valid from generator perspective."""
        sample_infra["domains"]["admin"]["machines"]["admin-ctrl"]["ip"] = "10.100.0.254"
        errors = validate(sample_infra)
        # The generator validates subnet membership, not gateway collision
        assert not any("not in subnet" in e for e in errors)

    def test_ip_matches_correct_subnet(self, sample_infra):
        """IP in correct subnet passes validation."""
        sample_infra["domains"]["work"]["machines"]["dev-ws"]["ip"] = "10.100.1.50"
        errors = validate(sample_infra)
        assert not any("not in subnet" in e for e in errors)

    def test_ip_wrong_subnet_id_segment(self, sample_infra):
        """IP with wrong subnet_id segment fails validation."""
        # work has subnet_id=1, so IP should be 10.100.1.x
        sample_infra["domains"]["work"]["machines"]["dev-ws"]["ip"] = "10.100.2.10"
        errors = validate(sample_infra)
        assert any("not in subnet" in e for e in errors)

    def test_no_ip_no_validation(self, sample_infra):
        """Machine without IP (DHCP) passes validation."""
        del sample_infra["domains"]["work"]["machines"]["dev-ws"]["ip"]
        errors = validate(sample_infra)
        assert not any("IP" in e or "ip" in e for e in errors)

    def test_same_ip_different_domains(self, sample_infra):
        """Same IP in different domains is a duplicate error."""
        sample_infra["domains"]["admin"]["machines"]["admin-ctrl"]["ip"] = "10.100.0.10"
        sample_infra["domains"]["work"]["machines"]["dev-ws"]["ip"] = "10.100.0.10"
        errors = validate(sample_infra)
        assert any("IP 10.100.0.10 already used" in e for e in errors)


# ── Validate multiple errors ────────────────────────────────


class TestMultipleErrors:
    """Validate reports all errors, not just the first one."""

    def test_multiple_independent_errors(self, sample_infra):
        """Multiple validation errors are all reported."""
        sample_infra["domains"]["admin"]["subnet_id"] = 999  # Invalid range
        sample_infra["domains"]["work"]["machines"]["dev-ws"]["type"] = "docker"  # Invalid type
        sample_infra["domains"]["BAD_NAME"] = {"subnet_id": 50, "machines": {}}  # Invalid name
        errors = validate(sample_infra)
        assert any("0-254" in e for e in errors)
        assert any("type must be" in e for e in errors)
        assert any("invalid name" in e for e in errors)

    def test_missing_all_required_keys(self):
        """Empty dict reports all missing required keys."""
        errors = validate({})
        assert len(errors) == 3  # project_name, global, domains


# ── load_infra directory edge cases ─────────────────────────


class TestLoadInfraDirectoryEdgeCases:
    """Edge cases for load_infra with directory mode."""

    def test_domains_none(self, tmp_path):
        """domains: null in infra.yml is treated as empty dict by validate/generate."""
        f = tmp_path / "infra.yml"
        f.write_text(yaml.dump({
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": None,
        }))
        result = load_infra(f)
        # domains is None from YAML; validate and generate handle it via `or {}`
        assert result["domains"] is None
        errors = validate(result)
        # "domains" key IS present (it's None), so the required key check passes,
        # but the `or {}` pattern in validate means it iterates over empty dict
        assert not any("Missing required key: domains" in e for e in errors)

    def test_empty_base_yml(self, tmp_path):
        """base.yml with no content defaults to {} (plus domains from dir scan)."""
        d = tmp_path / "infra"
        d.mkdir()
        (d / "base.yml").write_text("")
        (d / "domains").mkdir()
        result = load_infra(d)
        # Empty base.yml yields {}, but _load_infra_dir adds domains key
        # via setdefault when domains/ dir exists
        assert isinstance(result, dict)
        assert result.get("domains") == {}

    def test_empty_domain_file(self, tmp_path):
        """domains/empty.yml with no content is skipped (safe_load returns None)."""
        d = tmp_path / "infra"
        d.mkdir()
        (d / "base.yml").write_text(yaml.dump({
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
        }))
        domains_dir = d / "domains"
        domains_dir.mkdir()
        # Write one valid domain file
        (domains_dir / "admin.yml").write_text(yaml.dump({
            "admin": {"subnet_id": 0, "machines": {}},
        }))
        # Write an empty domain file
        (domains_dir / "empty.yml").write_text("")
        result = load_infra(d)
        # The empty file yields None or {}, so no domains are added from it
        assert "admin" in result["domains"]
        # No crash from the empty file
        assert len(result["domains"]) == 1

    def test_policies_yml_null_network_policies(self, tmp_path):
        """policies.yml with network_policies: null does not set network_policies."""
        d = tmp_path / "infra"
        d.mkdir()
        (d / "base.yml").write_text(yaml.dump({
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
        }))
        (d / "domains").mkdir()
        # policies.yml with null network_policies
        (d / "policies.yml").write_text("network_policies: null\n")
        result = load_infra(d)
        # The code checks `if "network_policies" in policies_data:` and
        # assigns the value. None is a valid value from YAML null.
        # The key is set, but its value is None.
        assert result.get("network_policies") is None

    def test_duplicate_domain_in_dir(self, tmp_path, capsys):
        """Two files define same domain, last wins + warning."""
        d = tmp_path / "infra"
        d.mkdir()
        (d / "base.yml").write_text(yaml.dump({
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
        }))
        domains_dir = d / "domains"
        domains_dir.mkdir()
        # Two files define the 'shared' domain — sorted alphabetically,
        # 01-shared.yml is loaded first, then 02-shared.yml overrides it
        (domains_dir / "01-shared.yml").write_text(yaml.dump({
            "shared": {"subnet_id": 1, "description": "First"},
        }))
        (domains_dir / "02-shared.yml").write_text(yaml.dump({
            "shared": {"subnet_id": 2, "description": "Second"},
        }))
        result = load_infra(d)
        # Last file (02-shared.yml) wins
        assert result["domains"]["shared"]["subnet_id"] == 2
        assert result["domains"]["shared"]["description"] == "Second"
        # Warning is printed to stderr
        captured = capsys.readouterr()
        assert "WARNING" in captured.err
        assert "shared" in captured.err

    def test_infra_dir_with_only_base_yml(self, tmp_path):
        """No domain files, just base.yml — no domains directory."""
        d = tmp_path / "infra"
        d.mkdir()
        (d / "base.yml").write_text(yaml.dump({
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
        }))
        # No domains/ directory at all
        result = load_infra(d)
        assert result.get("project_name") == "test"
        # No domains key in result (or empty)
        assert "domains" not in result or result.get("domains") in (None, {})


# ── validate() error branches ────────────────────────────────


class TestValidateEdgeCases:
    """Edge cases for validate() error branches."""

    def test_missing_all_required_keys_returns_early(self):
        """Only project_name present, returns early with missing keys."""
        errors = validate({"project_name": "test"})
        # Missing 'global' and 'domains'
        assert any("Missing required key: global" in e for e in errors)
        assert any("Missing required key: domains" in e for e in errors)
        # Should return early before domain validation
        assert len(errors) == 2

    def test_domains_none_value(self):
        """domains: null doesn't crash — treated as empty dict."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": None,
        }
        errors = validate(infra)
        # Should not crash; None is handled by `or {}`
        assert not any("crash" in str(e).lower() for e in errors)

    def test_machines_none_in_domain(self, sample_infra):
        """machines: null in domain doesn't crash."""
        sample_infra["domains"]["admin"]["machines"] = None
        # Should not crash; machines handled by `or {}`
        errors = validate(sample_infra)
        # No crash, possibly no machine-related errors since None -> {}
        assert not any("NoneType" in str(e) for e in errors)

    def test_machine_config_none(self, sample_infra, monkeypatch):
        """config: null in machine doesn't crash."""
        monkeypatch.setattr(gen_mod, "_read_vm_nested", lambda: False)
        monkeypatch.setattr(gen_mod, "_read_yolo", lambda: False)
        sample_infra["domains"]["admin"]["machines"]["admin-ctrl"]["config"] = None
        errors = validate(sample_infra)
        # config=None handled by `or {}`; no privileged check issue
        assert not any("NoneType" in str(e) for e in errors)

    def test_ip_as_integer(self, sample_infra):
        """ip: 12345 (integer) instead of string — raises AttributeError.

        The validate() code calls ip.startswith() which requires a string.
        An integer IP triggers an unhandled AttributeError. This test documents
        the current behavior (crash on non-string IP).
        """
        sample_infra["domains"]["admin"]["machines"]["admin-ctrl"]["ip"] = 12345
        with pytest.raises(AttributeError):
            validate(sample_infra)

    def test_network_policy_from_empty_string(self, sample_infra):
        """from: '' errors as unknown domain."""
        sample_infra["network_policies"] = [
            {"from": "", "to": "work", "ports": [22]},
        ]
        errors = validate(sample_infra)
        assert any("from:" in e and "not a known" in e for e in errors)

    def test_protocol_empty_string(self, sample_infra):
        """protocol: '' errors as invalid."""
        sample_infra["network_policies"] = [
            {"from": "admin", "to": "work", "ports": [22], "protocol": ""},
        ]
        errors = validate(sample_infra)
        assert any("protocol must be 'tcp' or 'udp'" in e for e in errors)

    def test_ai_access_default_empty_string(self, sample_infra):
        """Empty string ai_access_default errors as unknown domain."""
        sample_infra["global"]["ai_access_policy"] = "exclusive"
        sample_infra["global"]["ai_access_default"] = ""
        sample_infra["domains"]["ai-tools"] = {
            "subnet_id": 10, "machines": {},
        }
        errors = validate(sample_infra)
        # Empty string is not a known domain
        assert any("not a known domain" in e for e in errors)

    def test_gpu_profile_non_gpu_device_type(self, sample_infra):
        """Profile with type: 'disk' not counted as GPU."""
        sample_infra["domains"]["admin"]["profiles"] = {
            "storage": {"devices": {"data": {"type": "disk", "path": "/data"}}},
        }
        sample_infra["domains"]["admin"]["machines"]["admin-ctrl"]["profiles"] = [
            "default", "storage",
        ]
        # With exclusive policy (default), should NOT trigger GPU error
        # because a 'disk' device is not a 'gpu' device
        errors = validate(sample_infra)
        assert not any("GPU" in e for e in errors)


# ── Orphan detection edge cases ──────────────────────────────


class TestOrphanEdgeCases:
    """Edge cases for orphan detection."""

    def test_orphan_in_group_vars_only(self, sample_infra, tmp_path):
        """Orphan in group_vars but not inventory."""
        generate(sample_infra, tmp_path)
        # Add an orphan only in group_vars
        (tmp_path / "group_vars" / "old-domain.yml").write_text(
            "domain_ephemeral: true\n"
        )
        orphans = detect_orphans(sample_infra, tmp_path)
        orphan_names = [o[0].stem for o in orphans]
        assert "old-domain" in orphan_names

    def test_orphan_yaml_root_is_string(self, sample_infra, tmp_path):
        """YAML file with just a string as root — _is_orphan_protected handles gracefully."""
        generate(sample_infra, tmp_path)
        orphan_file = tmp_path / "host_vars" / "weird.yml"
        orphan_file.write_text("just a plain string\n")
        orphans = detect_orphans(sample_infra, tmp_path)
        orphan_dict = {o[0].stem: o[1] for o in orphans}
        # String root is not a dict, so not protected
        assert orphan_dict["weird"] is False

    def test_orphan_with_both_ephemeral_keys(self, sample_infra, tmp_path):
        """domain_ephemeral AND instance_ephemeral present — domain checked first."""
        generate(sample_infra, tmp_path)
        orphan_file = tmp_path / "host_vars" / "mixed.yml"
        # domain_ephemeral: false (protected) comes first in iteration,
        # instance_ephemeral: true would be not-protected
        orphan_file.write_text(
            "domain_ephemeral: false\ninstance_ephemeral: true\n"
        )
        orphans = detect_orphans(sample_infra, tmp_path)
        orphan_dict = {o[0].stem: o[1] for o in orphans}
        # domain_ephemeral is checked first -> protected
        assert orphan_dict["mixed"] is True


# ── CLI main() edge cases ────────────────────────────────────


class TestMainEdgeCases:
    """Edge cases for main() CLI function."""

    def test_main_no_args(self):
        """Exit with argparse error when no arguments provided."""
        from generate import main
        with pytest.raises(SystemExit) as exc_info:
            main([])
        # argparse exits with code 2 for usage errors
        assert exc_info.value.code == 2

    def test_main_clean_orphans_no_orphans(self, sample_infra, tmp_path, capsys):
        """--clean-orphans with nothing to clean runs without error."""
        from generate import main
        # Write infra file
        infra_file = tmp_path / "infra.yml"
        infra_file.write_text(yaml.dump(sample_infra, sort_keys=False))
        base_dir = tmp_path / "out"
        base_dir.mkdir()
        main([str(infra_file), "--base-dir", str(base_dir), "--clean-orphans"])
        # Should complete without error
        captured = capsys.readouterr()
        assert "Generating files" in captured.out

    def test_main_validate_errors_skip_warnings(self, tmp_path, capsys):
        """Validation errors prevent warning display (sys.exit before warnings)."""
        from generate import main
        # Write invalid infra file — missing required keys
        infra_file = tmp_path / "invalid.yml"
        infra_file.write_text(yaml.dump({"project_name": "bad"}, sort_keys=False))
        with pytest.raises(SystemExit) as exc_info:
            main([str(infra_file), "--base-dir", str(tmp_path)])
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Validation errors" in captured.err
        # Warnings should NOT appear because we exited before get_warnings()
        assert "WARNING" not in captured.err

    def test_main_dry_run_writes_nothing(self, sample_infra, tmp_path, capsys):
        """--dry-run previews output but writes no files."""
        from generate import main
        infra_file = tmp_path / "infra.yml"
        infra_file.write_text(yaml.dump(sample_infra, sort_keys=False))
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        main([str(infra_file), "--base-dir", str(out_dir), "--dry-run"])
        captured = capsys.readouterr()
        assert "[DRY-RUN]" in captured.out
        assert "Would write" in captured.out
        # No files actually written
        assert not list(out_dir.rglob("*.yml"))

    def test_main_empty_domains(self, tmp_path, capsys):
        """Empty domains dict prints 'Nothing to generate' message."""
        from generate import main
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {},
        }
        infra_file = tmp_path / "infra.yml"
        infra_file.write_text(yaml.dump(infra, sort_keys=False))
        main([str(infra_file), "--base-dir", str(tmp_path)])
        captured = capsys.readouterr()
        assert "Nothing to generate" in captured.out

    def test_main_clean_orphans_deletes_unprotected(self, sample_infra, tmp_path, capsys):
        """--clean-orphans deletes unprotected orphans but keeps protected ones."""
        from generate import main
        infra_file = tmp_path / "infra.yml"
        infra_file.write_text(yaml.dump(sample_infra, sort_keys=False))
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        # First, generate files
        main([str(infra_file), "--base-dir", str(out_dir)])
        # Create orphan files
        ephemeral_orphan = out_dir / "host_vars" / "temp.yml"
        ephemeral_orphan.write_text("instance_ephemeral: true\n")
        protected_orphan = out_dir / "host_vars" / "perm.yml"
        protected_orphan.write_text("instance_ephemeral: false\n")
        # Run with --clean-orphans
        main([str(infra_file), "--base-dir", str(out_dir), "--clean-orphans"])
        captured = capsys.readouterr()
        assert "Deleted" in captured.out
        assert "Skipped (protected)" in captured.out
        # Ephemeral orphan should be deleted
        assert not ephemeral_orphan.exists()
        # Protected orphan should be kept
        assert protected_orphan.exists()

    def test_main_shows_orphan_report(self, sample_infra, tmp_path, capsys):
        """Orphan files appear in the output report."""
        from generate import main
        infra_file = tmp_path / "infra.yml"
        infra_file.write_text(yaml.dump(sample_infra, sort_keys=False))
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        main([str(infra_file), "--base-dir", str(out_dir)])
        (out_dir / "host_vars" / "orphan-machine.yml").write_text("instance_name: orphan\n")
        main([str(infra_file), "--base-dir", str(out_dir)])
        captured = capsys.readouterr()
        assert "Orphan files" in captured.out
        assert "orphan-machine" in captured.out
