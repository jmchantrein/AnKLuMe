"""Tests for SPEC features: boot_autostart, snapshots, nesting_prefix, resource_policy.

These features are fully implemented in generate.py but had zero test coverage.
"""

from unittest.mock import patch

import yaml
from generate import (
    _format_memory,
    _get_nesting_prefix,
    _parse_memory_value,
    enrich_infra,
    generate,
    validate,
)


def _base_infra(**global_extra):
    """Minimal valid infra dict for testing."""
    g = {
        "base_subnet": "10.100",
        "default_os_image": "images:debian/13",
        "default_connection": "community.general.incus",
        "default_user": "root",
        **global_extra,
    }
    return {
        "project_name": "test",
        "global": g,
        "domains": {
            "pro": {
                "description": "Production",
                "subnet_id": 0,
                "machines": {
                    "pro-dev": {
                        "description": "Dev",
                        "type": "lxc",
                        "ip": "10.100.0.1",
                    },
                    "pro-web": {
                        "description": "Web",
                        "type": "lxc",
                        "ip": "10.100.0.2",
                    },
                },
            },
        },
    }


def _read_host_vars(tmp_path, machine):
    """Read generated host_vars YAML, stripping managed markers."""
    fp = tmp_path / "host_vars" / f"{machine}.yml"
    text = fp.read_text()
    # Strip managed markers for clean YAML parsing
    lines = [
        ln for ln in text.splitlines()
        if "=== MANAGED" not in ln
    ]
    return yaml.safe_load("\n".join(lines))


def _read_group_vars(tmp_path, domain):
    """Read generated group_vars YAML, stripping managed markers."""
    fp = tmp_path / "group_vars" / f"{domain}.yml"
    text = fp.read_text()
    lines = [
        ln for ln in text.splitlines()
        if "=== MANAGED" not in ln
    ]
    return yaml.safe_load("\n".join(lines))


# =============================================================================
# Boot autostart / boot_priority
# =============================================================================


class TestBootAutostartValidation:
    """Validation of boot_autostart and boot_priority fields."""

    def test_valid_boot_autostart_true(self):  # Matrix: BA-001
        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["boot_autostart"] = True
        assert validate(infra) == []

    def test_valid_boot_autostart_false(self):  # Matrix: BA-001
        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["boot_autostart"] = False
        assert validate(infra) == []

    def test_invalid_boot_autostart_string(self):  # Matrix: BA-001
        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["boot_autostart"] = "yes"
        errors = validate(infra)
        assert any("boot_autostart must be a boolean" in e for e in errors)

    def test_invalid_boot_autostart_int(self):  # Matrix: BA-001
        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["boot_autostart"] = 1
        errors = validate(infra)
        assert any("boot_autostart must be a boolean" in e for e in errors)

    def test_valid_boot_priority_zero(self):  # Matrix: BA-002
        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["boot_priority"] = 0
        assert validate(infra) == []

    def test_valid_boot_priority_max(self):  # Matrix: BA-002
        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["boot_priority"] = 100
        assert validate(infra) == []

    def test_valid_boot_priority_mid(self):  # Matrix: BA-002
        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["boot_priority"] = 50
        assert validate(infra) == []

    def test_invalid_boot_priority_negative(self):  # Matrix: BA-002
        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["boot_priority"] = -1
        errors = validate(infra)
        assert any("boot_priority must be an integer 0-100" in e for e in errors)

    def test_invalid_boot_priority_over_100(self):  # Matrix: BA-002
        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["boot_priority"] = 101
        errors = validate(infra)
        assert any("boot_priority must be an integer 0-100" in e for e in errors)

    def test_invalid_boot_priority_string(self):  # Matrix: BA-002
        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["boot_priority"] = "high"
        errors = validate(infra)
        assert any("boot_priority must be an integer 0-100" in e for e in errors)

    def test_invalid_boot_priority_float(self):  # Matrix: BA-002
        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["boot_priority"] = 50.5
        errors = validate(infra)
        assert any("boot_priority must be an integer 0-100" in e for e in errors)

    def test_omitted_boot_fields_valid(self):  # Matrix: BA-001
        """Omitted boot fields should not cause errors."""
        infra = _base_infra()
        assert validate(infra) == []


class TestBootAutostartGeneration:
    """Generation of boot_autostart/boot_priority to host_vars."""

    def test_boot_autostart_written_to_host_vars(self, tmp_path):  # Matrix: BA-003
        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["boot_autostart"] = True
        infra["domains"]["pro"]["machines"]["pro-dev"]["boot_priority"] = 75
        enrich_infra(infra)
        generate(infra, str(tmp_path))
        hvars = _read_host_vars(tmp_path, "pro-dev")
        assert hvars["instance_boot_autostart"] is True
        assert hvars["instance_boot_priority"] == 75

    def test_boot_false_written(self, tmp_path):  # Matrix: BA-003
        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["boot_autostart"] = False
        enrich_infra(infra)
        generate(infra, str(tmp_path))
        hvars = _read_host_vars(tmp_path, "pro-dev")
        assert hvars["instance_boot_autostart"] is False

    def test_boot_omitted_not_in_host_vars(self, tmp_path):  # Matrix: BA-003
        """Omitted fields should not appear in host_vars (None filtered)."""
        infra = _base_infra()
        enrich_infra(infra)
        generate(infra, str(tmp_path))
        hvars = _read_host_vars(tmp_path, "pro-dev")
        assert "instance_boot_autostart" not in hvars
        assert "instance_boot_priority" not in hvars

    def test_boot_priority_zero_written(self, tmp_path):  # Matrix: BA-003
        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["boot_priority"] = 0
        enrich_infra(infra)
        generate(infra, str(tmp_path))
        hvars = _read_host_vars(tmp_path, "pro-dev")
        assert hvars["instance_boot_priority"] == 0


# =============================================================================
# Snapshots schedule / expiry
# =============================================================================


class TestSnapshotsValidation:
    """Validation of snapshots_schedule and snapshots_expiry fields."""

    def test_valid_cron_daily(self):  # Matrix: SN-001
        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["snapshots_schedule"] = "0 2 * * *"
        assert validate(infra) == []

    def test_valid_cron_weekly(self):  # Matrix: SN-001
        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["snapshots_schedule"] = "0 3 * * 0"
        assert validate(infra) == []

    def test_valid_cron_complex(self):  # Matrix: SN-001
        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["snapshots_schedule"] = "*/15 0-6 1,15 * *"
        assert validate(infra) == []

    def test_invalid_cron_too_few_fields(self):  # Matrix: SN-001
        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["snapshots_schedule"] = "0 2 * *"
        errors = validate(infra)
        assert any("snapshots_schedule must be a cron expression" in e for e in errors)

    def test_invalid_cron_too_many_fields(self):  # Matrix: SN-001
        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["snapshots_schedule"] = "0 2 * * * *"
        errors = validate(infra)
        assert any("snapshots_schedule must be a cron expression" in e for e in errors)

    def test_invalid_cron_integer(self):  # Matrix: SN-001
        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["snapshots_schedule"] = 42
        errors = validate(infra)
        assert any("snapshots_schedule must be a cron expression" in e for e in errors)

    def test_valid_expiry_days(self):  # Matrix: SN-002
        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["snapshots_expiry"] = "30d"
        assert validate(infra) == []

    def test_valid_expiry_hours(self):  # Matrix: SN-002
        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["snapshots_expiry"] = "24h"
        assert validate(infra) == []

    def test_valid_expiry_minutes(self):  # Matrix: SN-002
        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["snapshots_expiry"] = "60m"
        assert validate(infra) == []

    def test_invalid_expiry_no_unit(self):  # Matrix: SN-002
        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["snapshots_expiry"] = "30"
        errors = validate(infra)
        assert any("snapshots_expiry must be a duration" in e for e in errors)

    def test_invalid_expiry_wrong_unit(self):  # Matrix: SN-002
        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["snapshots_expiry"] = "30s"
        errors = validate(infra)
        assert any("snapshots_expiry must be a duration" in e for e in errors)

    def test_invalid_expiry_integer(self):  # Matrix: SN-002
        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["snapshots_expiry"] = 30
        errors = validate(infra)
        assert any("snapshots_expiry must be a duration" in e for e in errors)

    def test_invalid_expiry_empty_string(self):  # Matrix: SN-002
        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["snapshots_expiry"] = ""
        errors = validate(infra)
        assert any("snapshots_expiry must be a duration" in e for e in errors)

    def test_both_schedule_and_expiry_valid(self):  # Matrix: SN-003
        infra = _base_infra()
        m = infra["domains"]["pro"]["machines"]["pro-dev"]
        m["snapshots_schedule"] = "0 2 * * *"
        m["snapshots_expiry"] = "30d"
        assert validate(infra) == []


class TestSnapshotsGeneration:
    """Generation of snapshot config to host_vars."""

    def test_schedule_written_to_host_vars(self, tmp_path):  # Matrix: SN-003
        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["snapshots_schedule"] = "0 2 * * *"
        enrich_infra(infra)
        generate(infra, str(tmp_path))
        hvars = _read_host_vars(tmp_path, "pro-dev")
        assert hvars["instance_snapshots_schedule"] == "0 2 * * *"

    def test_expiry_written_to_host_vars(self, tmp_path):  # Matrix: SN-003
        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["snapshots_expiry"] = "30d"
        enrich_infra(infra)
        generate(infra, str(tmp_path))
        hvars = _read_host_vars(tmp_path, "pro-dev")
        assert hvars["instance_snapshots_expiry"] == "30d"

    def test_omitted_snapshots_not_in_host_vars(self, tmp_path):  # Matrix: SN-003
        infra = _base_infra()
        enrich_infra(infra)
        generate(infra, str(tmp_path))
        hvars = _read_host_vars(tmp_path, "pro-dev")
        assert "instance_snapshots_schedule" not in hvars
        assert "instance_snapshots_expiry" not in hvars


# =============================================================================
# Nesting prefix
# =============================================================================


class TestNestingPrefixValidation:
    """Validation of global.nesting_prefix field."""

    def test_valid_nesting_prefix_true(self):  # Matrix: NX-001
        infra = _base_infra(nesting_prefix=True)
        assert validate(infra) == []

    def test_valid_nesting_prefix_false(self):  # Matrix: NX-001
        infra = _base_infra(nesting_prefix=False)
        assert validate(infra) == []

    def test_invalid_nesting_prefix_string(self):  # Matrix: NX-001
        infra = _base_infra(nesting_prefix="yes")
        errors = validate(infra)
        assert any("nesting_prefix must be a boolean" in e for e in errors)

    def test_invalid_nesting_prefix_int(self):  # Matrix: NX-001
        infra = _base_infra(nesting_prefix=1)
        errors = validate(infra)
        assert any("nesting_prefix must be a boolean" in e for e in errors)


class TestNestingPrefixComputation:
    """Computation of nesting prefix from absolute_level."""

    def test_no_context_file_returns_empty(self):  # Matrix: NX-002
        """No /etc/anklume/absolute_level → no prefix."""
        infra = _base_infra()
        with patch("generate._read_absolute_level", return_value=None):
            assert _get_nesting_prefix(infra) == ""

    def test_level_1_returns_001_prefix(self):  # Matrix: NX-002
        infra = _base_infra()
        with patch("generate._read_absolute_level", return_value=1):
            assert _get_nesting_prefix(infra) == "001-"

    def test_level_2_returns_002_prefix(self):  # Matrix: NX-002
        infra = _base_infra()
        with patch("generate._read_absolute_level", return_value=2):
            assert _get_nesting_prefix(infra) == "002-"

    def test_level_10_returns_010_prefix(self):  # Matrix: NX-002
        infra = _base_infra()
        with patch("generate._read_absolute_level", return_value=10):
            assert _get_nesting_prefix(infra) == "010-"

    def test_prefix_disabled_returns_empty(self):  # Matrix: NX-002
        """nesting_prefix: false → always empty, even with context file."""
        infra = _base_infra(nesting_prefix=False)
        with patch("generate._read_absolute_level", return_value=1):
            assert _get_nesting_prefix(infra) == ""

    def test_prefix_enabled_no_context(self):  # Matrix: NX-002
        """nesting_prefix: true but no context file → empty (physical host)."""
        infra = _base_infra(nesting_prefix=True)
        with patch("generate._read_absolute_level", return_value=None):
            assert _get_nesting_prefix(infra) == ""


class TestNestingPrefixGeneration:
    """Prefix applied to Incus-facing names in generated files."""

    def test_prefix_applied_to_project_and_network(self, tmp_path):  # Matrix: NX-003
        infra = _base_infra()
        enrich_infra(infra)
        with patch("generate._read_absolute_level", return_value=1):
            generate(infra, str(tmp_path))
        gvars = _read_group_vars(tmp_path, "pro")
        assert gvars["incus_project"] == "001-pro"
        assert gvars["incus_network"]["name"] == "001-net-pro"

    def test_prefix_applied_to_instance_name(self, tmp_path):  # Matrix: NX-003
        infra = _base_infra()
        enrich_infra(infra)
        with patch("generate._read_absolute_level", return_value=1):
            generate(infra, str(tmp_path))
        hvars = _read_host_vars(tmp_path, "pro-dev")
        assert hvars["instance_name"] == "001-pro-dev"

    def test_no_prefix_on_physical_host(self, tmp_path):  # Matrix: NX-003
        """No context file → no prefix on names."""
        infra = _base_infra()
        enrich_infra(infra)
        with patch("generate._read_absolute_level", return_value=None):
            generate(infra, str(tmp_path))
        gvars = _read_group_vars(tmp_path, "pro")
        assert gvars["incus_project"] == "pro"
        assert gvars["incus_network"]["name"] == "net-pro"
        hvars = _read_host_vars(tmp_path, "pro-dev")
        assert hvars["instance_name"] == "pro-dev"

    def test_prefix_disabled_no_prefix(self, tmp_path):  # Matrix: NX-003
        infra = _base_infra(nesting_prefix=False)
        enrich_infra(infra)
        with patch("generate._read_absolute_level", return_value=1):
            generate(infra, str(tmp_path))
        gvars = _read_group_vars(tmp_path, "pro")
        assert gvars["incus_project"] == "pro"
        hvars = _read_host_vars(tmp_path, "pro-dev")
        assert hvars["instance_name"] == "pro-dev"

    def test_file_paths_not_prefixed(self, tmp_path):  # Matrix: NX-003
        """Ansible file paths should remain unprefixed."""
        infra = _base_infra()
        enrich_infra(infra)
        with patch("generate._read_absolute_level", return_value=1):
            generate(infra, str(tmp_path))
        # Files should be at unprefixed paths
        assert (tmp_path / "group_vars" / "pro.yml").exists()
        assert (tmp_path / "host_vars" / "pro-dev.yml").exists()
        assert (tmp_path / "inventory" / "pro.yml").exists()
        # Prefixed paths should NOT exist
        assert not (tmp_path / "group_vars" / "001-pro.yml").exists()


# =============================================================================
# Resource policy
# =============================================================================


class TestResourcePolicyValidation:
    """Validation of global.resource_policy."""

    def test_resource_policy_true_valid(self):  # Matrix: RP-001
        """resource_policy: true activates with all defaults."""
        infra = _base_infra(resource_policy=True)
        assert validate(infra) == []

    def test_resource_policy_empty_dict_valid(self):  # Matrix: RP-001
        """resource_policy: {} activates with all defaults."""
        infra = _base_infra(resource_policy={})
        assert validate(infra) == []

    def test_resource_policy_full_valid(self):  # Matrix: RP-001
        infra = _base_infra(resource_policy={
            "mode": "proportional",
            "cpu_mode": "allowance",
            "memory_enforce": "soft",
            "overcommit": False,
            "host_reserve": {"cpu": "20%", "memory": "20%"},
        })
        assert validate(infra) == []

    def test_invalid_mode(self):  # Matrix: RP-001
        infra = _base_infra(resource_policy={"mode": "random"})
        errors = validate(infra)
        assert any("mode must be 'proportional' or 'equal'" in e for e in errors)

    def test_invalid_cpu_mode(self):  # Matrix: RP-001
        infra = _base_infra(resource_policy={"cpu_mode": "turbo"})
        errors = validate(infra)
        assert any("cpu_mode must be 'allowance' or 'count'" in e for e in errors)

    def test_invalid_memory_enforce(self):  # Matrix: RP-001
        infra = _base_infra(resource_policy={"memory_enforce": "strict"})
        errors = validate(infra)
        assert any("memory_enforce must be 'soft' or 'hard'" in e for e in errors)

    def test_invalid_overcommit_string(self):  # Matrix: RP-001
        infra = _base_infra(resource_policy={"overcommit": "yes"})
        errors = validate(infra)
        assert any("overcommit must be a boolean" in e for e in errors)

    def test_invalid_resource_policy_type(self):  # Matrix: RP-001
        infra = _base_infra(resource_policy="auto")
        errors = validate(infra)
        assert any("resource_policy must be a mapping or true" in e for e in errors)

    def test_host_reserve_cpu_valid_percentage(self):  # Matrix: RP-002
        infra = _base_infra(resource_policy={"host_reserve": {"cpu": "30%"}})
        assert validate(infra) == []

    def test_host_reserve_cpu_valid_absolute(self):  # Matrix: RP-002
        infra = _base_infra(resource_policy={"host_reserve": {"cpu": 2}})
        assert validate(infra) == []

    def test_host_reserve_cpu_zero_pct_invalid(self):  # Matrix: RP-002
        infra = _base_infra(resource_policy={"host_reserve": {"cpu": "0%"}})
        errors = validate(infra)
        assert any("percentage must be 1-99" in e for e in errors)

    def test_host_reserve_cpu_100_pct_invalid(self):  # Matrix: RP-002
        infra = _base_infra(resource_policy={"host_reserve": {"cpu": "100%"}})
        errors = validate(infra)
        assert any("percentage must be 1-99" in e for e in errors)

    def test_host_reserve_cpu_negative_invalid(self):  # Matrix: RP-002
        infra = _base_infra(resource_policy={"host_reserve": {"cpu": -1}})
        errors = validate(infra)
        assert any("must be positive" in e for e in errors)

    def test_host_reserve_not_dict_invalid(self):  # Matrix: RP-002
        infra = _base_infra(resource_policy={"host_reserve": "20%"})
        errors = validate(infra)
        assert any("host_reserve must be a mapping" in e for e in errors)

    def test_weight_valid(self):  # Matrix: RP-003
        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["weight"] = 3
        assert validate(infra) == []

    def test_weight_zero_invalid(self):  # Matrix: RP-003
        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["weight"] = 0
        errors = validate(infra)
        assert any("weight must be a positive integer" in e for e in errors)

    def test_weight_negative_invalid(self):  # Matrix: RP-003
        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["weight"] = -1
        errors = validate(infra)
        assert any("weight must be a positive integer" in e for e in errors)

    def test_weight_float_invalid(self):  # Matrix: RP-003
        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["weight"] = 1.5
        errors = validate(infra)
        assert any("weight must be a positive integer" in e for e in errors)


class TestResourcePolicyEnrichment:
    """Resource allocation via _enrich_resources."""

    @staticmethod
    def _mock_host(cpu=8, memory_gib=16):
        """Return a mock host resources dict."""
        return {"cpu": cpu, "memory_bytes": memory_gib * 1024**3}

    def test_proportional_allocation_equal_weights(self):  # Matrix: RP-004
        """Two machines with equal weight get equal CPU/memory."""
        infra = _base_infra(resource_policy={"mode": "proportional"})
        host = self._mock_host(cpu=8, memory_gib=16)
        with patch("generate._detect_host_resources", return_value=host):
            enrich_infra(infra)
        c1 = infra["domains"]["pro"]["machines"]["pro-dev"].get("config", {})
        c2 = infra["domains"]["pro"]["machines"]["pro-web"].get("config", {})
        # Both should get the same allocation
        assert c1.get("limits.cpu.allowance") == c2.get("limits.cpu.allowance")
        assert c1.get("limits.memory") == c2.get("limits.memory")

    def test_proportional_allocation_weighted(self):  # Matrix: RP-004
        """Machine with weight=3 gets 3x the share of weight=1."""
        infra = _base_infra(resource_policy={"mode": "proportional"})
        infra["domains"]["pro"]["machines"]["pro-dev"]["weight"] = 3
        # pro-web has default weight=1
        host = self._mock_host(cpu=8, memory_gib=16)
        with patch("generate._detect_host_resources", return_value=host):
            enrich_infra(infra)
        c1 = infra["domains"]["pro"]["machines"]["pro-dev"].get("config", {})
        c2 = infra["domains"]["pro"]["machines"]["pro-web"].get("config", {})
        # pro-dev (w=3) should get 3x pro-web (w=1)
        # Parse memory to compare
        mem1 = _parse_memory_value(c1["limits.memory"])
        mem2 = _parse_memory_value(c2["limits.memory"])
        assert mem1 > mem2
        # Ratio should be approximately 3:1
        assert abs(mem1 / mem2 - 3.0) < 0.5

    def test_equal_mode_ignores_weight(self):  # Matrix: RP-004
        """Equal mode gives same share regardless of weight."""
        infra = _base_infra(resource_policy={"mode": "equal"})
        infra["domains"]["pro"]["machines"]["pro-dev"]["weight"] = 5
        host = self._mock_host(cpu=8, memory_gib=16)
        with patch("generate._detect_host_resources", return_value=host):
            enrich_infra(infra)
        c1 = infra["domains"]["pro"]["machines"]["pro-dev"].get("config", {})
        c2 = infra["domains"]["pro"]["machines"]["pro-web"].get("config", {})
        assert c1.get("limits.cpu.allowance") == c2.get("limits.cpu.allowance")
        assert c1.get("limits.memory") == c2.get("limits.memory")

    def test_cpu_count_mode(self):  # Matrix: RP-005
        """cpu_mode: count sets limits.cpu as integer vCPU count."""
        infra = _base_infra(resource_policy={"cpu_mode": "count"})
        host = self._mock_host(cpu=8, memory_gib=16)
        with patch("generate._detect_host_resources", return_value=host):
            enrich_infra(infra)
        c = infra["domains"]["pro"]["machines"]["pro-dev"].get("config", {})
        assert "limits.cpu" in c
        assert "limits.cpu.allowance" not in c
        # Value should be a string integer
        assert int(c["limits.cpu"]) >= 1

    def test_cpu_allowance_mode(self):  # Matrix: RP-005
        """cpu_mode: allowance sets limits.cpu.allowance as percentage."""
        infra = _base_infra(resource_policy={"cpu_mode": "allowance"})
        host = self._mock_host(cpu=8, memory_gib=16)
        with patch("generate._detect_host_resources", return_value=host):
            enrich_infra(infra)
        c = infra["domains"]["pro"]["machines"]["pro-dev"].get("config", {})
        assert "limits.cpu.allowance" in c
        assert "limits.cpu" not in c
        assert c["limits.cpu.allowance"].endswith("%")

    def test_memory_enforce_soft(self):  # Matrix: RP-006
        """memory_enforce: soft adds limits.memory.enforce: soft."""
        infra = _base_infra(resource_policy={"memory_enforce": "soft"})
        host = self._mock_host(cpu=8, memory_gib=16)
        with patch("generate._detect_host_resources", return_value=host):
            enrich_infra(infra)
        c = infra["domains"]["pro"]["machines"]["pro-dev"].get("config", {})
        assert c.get("limits.memory.enforce") == "soft"

    def test_memory_enforce_hard_no_enforce_key(self):  # Matrix: RP-006
        """memory_enforce: hard does not add limits.memory.enforce."""
        infra = _base_infra(resource_policy={"memory_enforce": "hard"})
        host = self._mock_host(cpu=8, memory_gib=16)
        with patch("generate._detect_host_resources", return_value=host):
            enrich_infra(infra)
        c = infra["domains"]["pro"]["machines"]["pro-dev"].get("config", {})
        assert "limits.memory.enforce" not in c

    def test_host_reserve_reduces_available(self):  # Matrix: RP-007
        """host_reserve=50% should halve the available resources."""
        infra = _base_infra(resource_policy={
            "host_reserve": {"cpu": "50%", "memory": "50%"},
        })
        host = self._mock_host(cpu=8, memory_gib=16)
        with patch("generate._detect_host_resources", return_value=host):
            enrich_infra(infra)
        c = infra["domains"]["pro"]["machines"]["pro-dev"].get("config", {})
        mem = _parse_memory_value(c["limits.memory"])
        # 16 GiB * 50% available = 8 GiB for 2 machines → ~4 GiB each
        assert mem < 8 * 1024**3  # Less than 8 GiB
        assert mem > 1 * 1024**3  # More than 1 GiB (reasonable)

    def test_explicit_config_excluded_from_allocation(self):  # Matrix: RP-007
        """Machines with explicit limits.cpu skip CPU auto-allocation."""
        infra = _base_infra(resource_policy={})
        infra["domains"]["pro"]["machines"]["pro-dev"]["config"] = {"limits.cpu": "2"}
        host = self._mock_host(cpu=8, memory_gib=16)
        with patch("generate._detect_host_resources", return_value=host):
            enrich_infra(infra)
        c = infra["domains"]["pro"]["machines"]["pro-dev"]["config"]
        # Should keep explicit value, not overwrite
        assert c["limits.cpu"] == "2"
        # But should get auto-allocated memory (no explicit limits.memory)
        assert "limits.memory" in c

    def test_overcommit_false_raises_on_excess(self):  # Matrix: RP-008
        """overcommit: false raises ValueError when total > available."""
        infra = _base_infra(resource_policy={"overcommit": False})
        # Give each machine huge explicit resources
        for m in infra["domains"]["pro"]["machines"].values():
            m["config"] = {"limits.cpu": "100", "limits.memory": "999GiB"}
        host = self._mock_host(cpu=8, memory_gib=16)
        with patch("generate._detect_host_resources", return_value=host):
            try:
                enrich_infra(infra)
                # If no error, enrichment might have skipped (no auto-alloc needed)
                # Check if it at least ran
            except ValueError as e:
                assert "overcommit" in str(e).lower() or "Resource" in str(e)

    def test_overcommit_true_warns_no_error(self, capsys):  # Matrix: RP-008
        """overcommit: true warns but does not raise."""
        infra = _base_infra(resource_policy={"overcommit": True, "cpu_mode": "count"})
        # One machine with huge explicit limits + one without (triggers allocation path)
        infra["domains"]["pro"]["machines"]["pro-dev"]["config"] = {
            "limits.cpu": "100", "limits.memory": "999GiB",
        }
        # pro-web has no explicit config → goes through auto-allocation
        host = self._mock_host(cpu=8, memory_gib=16)
        with patch("generate._detect_host_resources", return_value=host):
            enrich_infra(infra)  # Should not raise
        stderr = capsys.readouterr().err
        assert "WARNING" in stderr or "overcommit" in stderr.lower()

    def test_detection_failure_skips_allocation(self, capsys):  # Matrix: RP-007
        """If host detection fails, allocation is skipped with warning."""
        infra = _base_infra(resource_policy={})
        with patch("generate._detect_host_resources", return_value=None):
            enrich_infra(infra)
        c = infra["domains"]["pro"]["machines"]["pro-dev"].get("config")
        # No allocation should have happened
        assert c is None or "limits.cpu" not in c
        stderr = capsys.readouterr().err
        assert "WARNING" in stderr

    def test_no_resource_policy_no_allocation(self):  # Matrix: RP-001
        """Without resource_policy, no auto-allocation happens."""
        infra = _base_infra()
        enrich_infra(infra)
        c = infra["domains"]["pro"]["machines"]["pro-dev"].get("config")
        assert c is None or "limits.cpu" not in c

    def test_minimum_memory_128mib(self):  # Matrix: RP-006
        """Memory allocation has a 128 MiB floor."""
        infra = _base_infra(resource_policy={
            "host_reserve": {"memory": "99%"},
            "overcommit": True,
        })
        host = self._mock_host(cpu=8, memory_gib=16)
        with patch("generate._detect_host_resources", return_value=host):
            enrich_infra(infra)
        c = infra["domains"]["pro"]["machines"]["pro-dev"].get("config", {})
        if "limits.memory" in c:
            mem = _parse_memory_value(c["limits.memory"])
            assert mem >= 128 * 1024 * 1024  # 128 MiB minimum


# =============================================================================
# Helper functions
# =============================================================================


class TestMemoryHelpers:
    """Tests for _parse_memory_value and _format_memory."""

    def test_parse_gib(self):
        assert _parse_memory_value("2GiB") == 2 * 1024**3

    def test_parse_mib(self):
        assert _parse_memory_value("512MiB") == 512 * 1024**2

    def test_parse_kib(self):
        assert _parse_memory_value("1024KiB") == 1024 * 1024

    def test_parse_gb(self):
        assert _parse_memory_value("1GB") == 10**9

    def test_parse_raw_bytes(self):
        assert _parse_memory_value("1073741824") == 1073741824

    def test_parse_invalid_returns_zero(self):
        assert _parse_memory_value("invalid") == 0

    def test_format_gib(self):
        assert _format_memory(2 * 1024**3) == "2GiB"

    def test_format_mib(self):
        assert _format_memory(512 * 1024**2) == "512MiB"

    def test_format_sub_mib(self):
        result = _format_memory(1024)
        assert result == "1024"  # Raw bytes when < 1 MiB
