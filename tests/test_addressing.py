"""Tests for zone-based addressing (ADR-038)."""

from generate import (
    DEFAULT_TRUST_LEVEL,
    ZONE_OFFSETS,
    _auto_assign_ips,
    _compute_addressing,
    _enrich_addressing,
    detect_orphans,
    enrich_infra,
    generate,
    validate,
)


def _addr_infra(domains, **global_extra):
    """Helper to build infra dict with addressing mode."""
    g = {"addressing": {"base_octet": 10, "zone_base": 100}, **global_extra}
    return {"project_name": "test", "global": g, "domains": domains}


class TestZoneOffsets:
    def test_all_trust_levels_have_offsets(self):
        for level in ("admin", "trusted", "semi-trusted", "untrusted", "disposable"):
            assert level in ZONE_OFFSETS

    def test_default_trust_level(self):
        assert DEFAULT_TRUST_LEVEL == "semi-trusted"

    def test_offsets_produce_valid_octets(self):
        zone_base = 100
        for offset in ZONE_OFFSETS.values():
            assert 0 <= zone_base + offset <= 255


class TestComputeAddressing:
    def test_single_admin_domain(self):
        infra = _addr_infra({"mgmt": {"trust_level": "admin", "machines": {}}})
        result = _compute_addressing(infra)
        assert result == {"mgmt": {"second_octet": 100, "domain_seq": 0}}

    def test_two_domains_same_zone(self):
        infra = _addr_infra({
            "beta": {"trust_level": "trusted", "machines": {}},
            "alpha": {"trust_level": "trusted", "machines": {}},
        })
        result = _compute_addressing(infra)
        # Alphabetical: alpha=0, beta=1
        assert result["alpha"]["domain_seq"] == 0
        assert result["beta"]["domain_seq"] == 1
        assert result["alpha"]["second_octet"] == 110
        assert result["beta"]["second_octet"] == 110

    def test_multiple_zones(self):
        infra = _addr_infra({
            "admin-box": {"trust_level": "admin", "machines": {}},
            "work": {"trust_level": "trusted", "machines": {}},
            "sandbox": {"trust_level": "disposable", "machines": {}},
        })
        result = _compute_addressing(infra)
        assert result["admin-box"]["second_octet"] == 100
        assert result["work"]["second_octet"] == 110
        assert result["sandbox"]["second_octet"] == 150

    def test_explicit_subnet_id_override(self):
        infra = _addr_infra({
            "auto-a": {"trust_level": "trusted", "machines": {}},
            "explicit": {"trust_level": "trusted", "subnet_id": 5, "machines": {}},
            "auto-b": {"trust_level": "trusted", "machines": {}},
        })
        result = _compute_addressing(infra)
        assert result["explicit"]["domain_seq"] == 5
        assert result["auto-a"]["domain_seq"] == 0
        assert result["auto-b"]["domain_seq"] == 1

    def test_auto_skips_explicit_values(self):
        infra = _addr_infra({
            "first": {"trust_level": "trusted", "machines": {}},
            "pinned": {"trust_level": "trusted", "subnet_id": 0, "machines": {}},
            "second": {"trust_level": "trusted", "machines": {}},
        })
        result = _compute_addressing(infra)
        assert result["pinned"]["domain_seq"] == 0
        assert result["first"]["domain_seq"] == 1
        assert result["second"]["domain_seq"] == 2

    def test_default_trust_level_fallback(self):
        infra = _addr_infra({"nozone": {"machines": {}}})
        result = _compute_addressing(infra)
        assert result["nozone"]["second_octet"] == 120  # semi-trusted

    def test_custom_zone_base(self):
        g = {"addressing": {"base_octet": 10, "zone_base": 50}}
        infra = {"project_name": "t", "global": g, "domains": {
            "d": {"trust_level": "admin", "machines": {}}
        }}
        result = _compute_addressing(infra)
        assert result["d"]["second_octet"] == 50  # 50 + 0


class TestAutoAssignIps:
    def test_basic_auto_assign(self):
        domain = {"machines": {
            "a": {"type": "lxc"},
            "b": {"type": "lxc"},
        }}
        _auto_assign_ips(domain, 10, 120, 0)
        assert domain["machines"]["a"]["ip"] == "10.120.0.1"
        assert domain["machines"]["b"]["ip"] == "10.120.0.2"

    def test_skips_explicit_ips(self):
        domain = {"machines": {
            "explicit": {"type": "lxc", "ip": "10.120.0.5"},
            "auto": {"type": "lxc"},
        }}
        _auto_assign_ips(domain, 10, 120, 0)
        assert domain["machines"]["explicit"]["ip"] == "10.120.0.5"
        assert domain["machines"]["auto"]["ip"] == "10.120.0.1"

    def test_auto_avoids_used_hosts(self):
        domain = {"machines": {
            "first": {"type": "lxc", "ip": "10.110.0.1"},
            "auto1": {"type": "lxc"},
            "second": {"type": "lxc", "ip": "10.110.0.2"},
            "auto2": {"type": "lxc"},
        }}
        _auto_assign_ips(domain, 10, 110, 0)
        assert domain["machines"]["auto1"]["ip"] == "10.110.0.3"
        assert domain["machines"]["auto2"]["ip"] == "10.110.0.4"

    def test_no_machines_no_crash(self):
        domain = {"machines": {}}
        _auto_assign_ips(domain, 10, 100, 0)  # No error

    def test_none_machines_no_crash(self):
        domain = {"machines": None}
        _auto_assign_ips(domain, 10, 100, 0)  # No error


class TestEnrichAddressing:
    def test_defaults_trust_level(self):
        infra = _addr_infra({"mydom": {"machines": {"m": {"type": "lxc"}}}})
        _enrich_addressing(infra)
        assert infra["domains"]["mydom"]["trust_level"] == "semi-trusted"

    def test_stores_addressing_dict(self):
        infra = _addr_infra({"d": {"trust_level": "admin", "machines": {}}})
        _enrich_addressing(infra)
        assert "_addressing" in infra
        assert "d" in infra["_addressing"]

    def test_auto_assigns_ips(self):
        infra = _addr_infra({"d": {
            "trust_level": "trusted",
            "machines": {"m1": {"type": "lxc"}, "m2": {"type": "lxc"}},
        }})
        _enrich_addressing(infra)
        assert infra["domains"]["d"]["machines"]["m1"]["ip"] == "10.110.0.1"
        assert infra["domains"]["d"]["machines"]["m2"]["ip"] == "10.110.0.2"

    def test_noop_without_addressing_key(self):
        infra = {"project_name": "t", "global": {"base_subnet": "10.100"},
                 "domains": {"d": {"subnet_id": 1, "machines": {}}}}
        _enrich_addressing(infra)
        assert "_addressing" not in infra


class TestValidateAddressing:
    def test_valid_addressing_config(self):
        infra = _addr_infra({"d": {"trust_level": "admin", "machines": {}}})
        errors = validate(infra)
        assert not errors

    def test_subnet_id_optional(self):
        infra = _addr_infra({"d": {"trust_level": "trusted", "machines": {
            "m": {"type": "lxc"},
        }}})
        errors = validate(infra)
        assert not errors

    def test_explicit_subnet_id_validated(self):
        infra = _addr_infra({"d": {"trust_level": "admin", "subnet_id": 300, "machines": {}}})
        errors = validate(infra)
        assert any("subnet_id must be 0-254" in e for e in errors)

    def test_duplicate_subnet_id_same_zone(self):
        infra = _addr_infra({
            "a": {"trust_level": "trusted", "subnet_id": 0, "machines": {}},
            "b": {"trust_level": "trusted", "subnet_id": 0, "machines": {}},
        })
        errors = validate(infra)
        assert any("subnet_id 0 already used" in e for e in errors)

    def test_same_subnet_id_different_zones_ok(self):
        infra = _addr_infra({
            "a": {"trust_level": "admin", "subnet_id": 0, "machines": {}},
            "b": {"trust_level": "trusted", "subnet_id": 0, "machines": {}},
        })
        errors = validate(infra)
        assert not errors

    def test_ip_validated_against_zone(self):
        infra = _addr_infra({"d": {
            "trust_level": "admin",
            "machines": {"m": {"type": "lxc", "ip": "10.110.0.1"}},
        }})
        errors = validate(infra)
        assert any("not in subnet" in e for e in errors)

    def test_ip_in_correct_zone_passes(self):
        infra = _addr_infra({"d": {
            "trust_level": "admin",
            "machines": {"m": {"type": "lxc", "ip": "10.100.0.1"}},
        }})
        errors = validate(infra)
        assert not errors

    def test_invalid_base_octet(self):
        g = {"addressing": {"base_octet": 11, "zone_base": 100}}
        infra = {"project_name": "t", "global": g, "domains": {
            "d": {"trust_level": "admin", "machines": {}},
        }}
        errors = validate(infra)
        assert any("base_octet must be 10" in e for e in errors)

    def test_invalid_zone_base(self):
        g = {"addressing": {"base_octet": 10, "zone_base": 300}}
        infra = {"project_name": "t", "global": g, "domains": {
            "d": {"trust_level": "admin", "machines": {}},
        }}
        errors = validate(infra)
        assert any("zone_base must be 0-245" in e for e in errors)

    def test_invalid_zone_step(self):
        g = {"addressing": {"base_octet": 10, "zone_base": 100, "zone_step": 0}}
        infra = {"project_name": "t", "global": g, "domains": {
            "d": {"trust_level": "admin", "machines": {}},
        }}
        errors = validate(infra)
        assert any("zone_step must be a positive integer" in e for e in errors)

    def test_enabled_field_validated(self):
        infra = _addr_infra({"d": {
            "trust_level": "admin", "enabled": "yes", "machines": {},
        }})
        errors = validate(infra)
        assert any("enabled must be a boolean" in e for e in errors)

    def test_enabled_false_accepted(self):
        infra = _addr_infra({"d": {
            "trust_level": "admin", "enabled": False, "machines": {},
        }})
        errors = validate(infra)
        assert not errors


class TestGenerateAddressing:
    def test_generates_correct_subnets(self, tmp_path):
        infra = _addr_infra({
            "admin-net": {"trust_level": "admin", "machines": {
                "ctrl": {"type": "lxc"},
            }},
            "work": {"trust_level": "trusted", "machines": {
                "dev": {"type": "lxc"},
            }},
        })
        enrich_infra(infra)
        files = generate(infra, tmp_path)
        assert len(files) > 0

        # Check group_vars content
        admin_gv = (tmp_path / "group_vars" / "admin-net.yml").read_text()
        assert "10.100.0.0/24" in admin_gv
        assert "10.100.0.254" in admin_gv

        work_gv = (tmp_path / "group_vars" / "work.yml").read_text()
        assert "10.110.0.0/24" in work_gv
        assert "10.110.0.254" in work_gv

    def test_generates_auto_assigned_ips(self, tmp_path):
        infra = _addr_infra({"d": {
            "trust_level": "trusted",
            "machines": {"m1": {"type": "lxc"}, "m2": {"type": "lxc"}},
        }})
        enrich_infra(infra)
        generate(infra, tmp_path)
        hv1 = (tmp_path / "host_vars" / "m1.yml").read_text()
        hv2 = (tmp_path / "host_vars" / "m2.yml").read_text()
        assert "10.110.0.1" in hv1
        assert "10.110.0.2" in hv2

    def test_skips_disabled_domains(self, tmp_path):
        infra = _addr_infra({
            "active": {"trust_level": "admin", "machines": {
                "m": {"type": "lxc"},
            }},
            "disabled": {"trust_level": "trusted", "enabled": False, "machines": {
                "n": {"type": "lxc"},
            }},
        })
        enrich_infra(infra)
        files = generate(infra, tmp_path)
        file_names = [f.name for f in files]
        assert "active.yml" in file_names
        assert "disabled.yml" not in [f.name for f in files if "inventory" in str(f)]

    def test_all_yml_has_addressing(self, tmp_path):
        infra = _addr_infra({"d": {"trust_level": "admin", "machines": {}}})
        enrich_infra(infra)
        generate(infra, tmp_path)
        all_content = (tmp_path / "group_vars" / "all.yml").read_text()
        assert "addressing:" in all_content
        assert "base_subnet" not in all_content

    def test_disabled_domain_not_orphan(self, tmp_path):
        infra = _addr_infra({
            "active": {"trust_level": "admin", "machines": {}},
            "off": {"trust_level": "trusted", "enabled": False, "machines": {
                "m": {"type": "lxc"},
            }},
        })
        enrich_infra(infra)
        generate(infra, tmp_path)
        # Create fake files for the disabled domain
        for d in ("group_vars", "inventory", "host_vars"):
            (tmp_path / d).mkdir(exist_ok=True)
        (tmp_path / "group_vars" / "off.yml").write_text("---\n")
        (tmp_path / "inventory" / "off.yml").write_text("---\n")
        (tmp_path / "host_vars" / "m.yml").write_text("---\n")
        orphans = detect_orphans(infra, tmp_path)
        orphan_names = [f.name for f, _ in orphans]
        # Disabled domain files should NOT be orphans
        assert "off.yml" not in orphan_names
        assert "m.yml" not in orphan_names


class TestEnrichFirewallAddressing:
    def test_firewall_uses_computed_addressing(self):
        infra = _addr_infra({
            "anklume": {"trust_level": "admin", "machines": {
                "ctrl": {"type": "lxc"},
            }},
        }, firewall_mode="vm")
        enrich_infra(infra)
        fw = infra["domains"]["anklume"]["machines"]["anklume-firewall"]
        # Admin zone: 10.100.0.253
        assert fw["ip"] == "10.100.0.253"
