"""Tests for role defaults — schema validation across all 18 roles."""

from pathlib import Path

import yaml

ROLES_DIR = Path(__file__).resolve().parent.parent / "roles"

# All roles that should have defaults
EXPECTED_ROLES = sorted([
    "admin_bootstrap",
    "base_system",
    "dev_agent_runner",
    "dev_test_runner",
    "firewall_router",
    "incus_firewall_vm",
    "incus_images",
    "incus_instances",
    "incus_networks",
    "incus_nftables",
    "incus_profiles",
    "incus_projects",
    "incus_snapshots",
    "lobechat",
    "ollama_server",
    "opencode_server",
    "open_webui",
    "stt_server",
])


class TestRoleStructure:
    def test_all_roles_have_defaults(self):
        """Every role has a defaults/main.yml file."""
        missing = []
        for role in EXPECTED_ROLES:
            defaults = ROLES_DIR / role / "defaults" / "main.yml"
            if not defaults.exists():
                missing.append(role)
        assert not missing, f"Roles missing defaults/main.yml: {missing}"

    def test_all_roles_have_tasks(self):
        """Every role has a tasks/main.yml file."""
        missing = []
        for role in EXPECTED_ROLES:
            tasks = ROLES_DIR / role / "tasks" / "main.yml"
            if not tasks.exists():
                missing.append(role)
        assert not missing, f"Roles missing tasks/main.yml: {missing}"

    def test_all_roles_have_meta(self):
        """Every role has a meta/main.yml file."""
        missing = []
        for role in EXPECTED_ROLES:
            meta = ROLES_DIR / role / "meta" / "main.yml"
            if not meta.exists():
                missing.append(role)
        assert not missing, f"Roles missing meta/main.yml: {missing}"

    def test_all_roles_have_molecule(self):
        """Every role has a molecule/ directory."""
        missing = []
        for role in EXPECTED_ROLES:
            molecule = ROLES_DIR / role / "molecule"
            if not molecule.exists():
                missing.append(role)
        assert not missing, f"Roles missing molecule/ directory: {missing}"


class TestDefaultsValidYaml:
    def test_all_defaults_parse_as_yaml(self):
        """All defaults files parse as valid YAML."""
        errors = []
        for role in EXPECTED_ROLES:
            defaults = ROLES_DIR / role / "defaults" / "main.yml"
            if defaults.exists():
                try:
                    data = yaml.safe_load(defaults.read_text())
                    if data is None:
                        errors.append(f"{role}: defaults is empty/null")
                except yaml.YAMLError as e:
                    errors.append(f"{role}: {e}")
        assert not errors, "YAML parse errors:\n" + "\n".join(errors)


class TestDefaultsNoNone:
    """Verify no default variable has a None/null value (likely a bug)."""

    # Roles where empty defaults are OK (overridden by PSOT)
    ALLOW_EMPTY = {
        "incus_instances": [
            "instance_name", "instance_description", "instance_domain",
        ],
        "ollama_server": ["ollama_default_model"],
        "stt_server": ["stt_server_language"],
    }

    def test_no_none_values(self):
        """Default variables should not be None (use empty string instead)."""
        errors = []
        for role in EXPECTED_ROLES:
            defaults = ROLES_DIR / role / "defaults" / "main.yml"
            if not defaults.exists():
                continue
            data = yaml.safe_load(defaults.read_text())
            if not isinstance(data, dict):
                continue
            allowed = self.ALLOW_EMPTY.get(role, [])
            for key, value in data.items():
                if value is None and key not in allowed:
                    errors.append(f"{role}: {key} is None")
        assert not errors, (
            "Variables with None defaults:\n" + "\n".join(errors)
        )


class TestDefaultsTypeConsistency:
    """Verify that default variable types are sensible."""

    # Expected types for variables matching patterns
    TYPE_RULES = {
        "_enabled": bool,
        "_apply": bool,
        "_retries": int,
        "_delay": int,
        "_port": int,
        "_timeout": int,
    }

    def test_boolean_defaults_are_bool(self):
        """Variables ending in _enabled or _apply should be boolean."""
        errors = []
        for role in EXPECTED_ROLES:
            defaults = ROLES_DIR / role / "defaults" / "main.yml"
            if not defaults.exists():
                continue
            data = yaml.safe_load(defaults.read_text())
            if not isinstance(data, dict):
                continue
            for key, value in data.items():
                for suffix, expected_type in self.TYPE_RULES.items():
                    if key.endswith(suffix) and not isinstance(
                        value, expected_type,
                    ):
                        errors.append(
                            f"{role}: {key}={value!r} "
                            f"(expected {expected_type.__name__})",
                        )
        assert not errors, (
            "Type mismatches:\n" + "\n".join(errors)
        )


class TestDefaultsVariableNaming:
    """Verify role variables follow naming conventions."""

    # Cross-role variables passed by PSOT generator (not role-prefixed)
    CROSS_ROLE_VARS = {
        "incus_network", "incus_project", "incus_all_images",
        "domain_ephemeral", "domain_description",
        "snapshot_action", "snapshot_name", "snapshot_stop_first",
        "incus_images_import_from_host",
    }

    def test_infra_role_vars_prefixed(self):
        """Infrastructure roles prefix variables with role name or use cross-role vars."""
        infra_roles = [
            "incus_networks", "incus_projects", "incus_profiles",
            "incus_instances", "incus_nftables", "incus_firewall_vm",
            "incus_images", "incus_snapshots",
        ]
        errors = []
        for role in infra_roles:
            defaults = ROLES_DIR / role / "defaults" / "main.yml"
            if not defaults.exists():
                continue
            data = yaml.safe_load(defaults.read_text())
            if not isinstance(data, dict):
                continue
            prefix = role + "_"
            # Also accept instance_ for incus_instances (legacy naming)
            # and incus_ prefix for shared infra variables
            extra_prefixes = ["incus_"]
            if role == "incus_instances":
                extra_prefixes.append("instance_")
            for key in data:
                if key in self.CROSS_ROLE_VARS:
                    continue
                if not key.startswith(prefix) and not any(
                    key.startswith(p) for p in extra_prefixes
                ):
                    errors.append(f"{role}: variable '{key}' "
                                  f"doesn't start with '{prefix}'")
        assert not errors, (
            "Naming convention violations:\n" + "\n".join(errors)
        )

    def test_provision_role_vars_prefixed(self):
        """Provisioning roles prefix variables with a recognizable prefix."""
        provision_roles = [
            "ollama_server", "open_webui", "stt_server",
            "lobechat", "opencode_server", "firewall_router",
            "dev_test_runner", "dev_agent_runner",
        ]
        errors = []
        for role in provision_roles:
            defaults = ROLES_DIR / role / "defaults" / "main.yml"
            if not defaults.exists():
                continue
            data = yaml.safe_load(defaults.read_text())
            if not isinstance(data, dict):
                continue
            # Accept role_name_ prefix or shorter variant (e.g., ollama_)
            role_short = role.split("_")[0] + "_"
            prefix = role + "_"
            for key in data:
                if key in self.CROSS_ROLE_VARS:
                    continue
                if not key.startswith(prefix) and not key.startswith(
                    role_short,
                ):
                    errors.append(f"{role}: variable '{key}' "
                                  f"doesn't start with '{prefix}' "
                                  f"or '{role_short}'")
        assert not errors, (
            "Naming convention violations:\n" + "\n".join(errors)
        )


class TestMetaContent:
    """Verify meta/main.yml contains required fields."""

    def test_meta_has_galaxy_info(self):
        """All roles have galaxy_info in meta/main.yml."""
        errors = []
        for role in EXPECTED_ROLES:
            meta = ROLES_DIR / role / "meta" / "main.yml"
            if not meta.exists():
                continue
            data = yaml.safe_load(meta.read_text())
            if not isinstance(data, dict):
                errors.append(f"{role}: meta is not a dict")
                continue
            if "galaxy_info" not in data:
                errors.append(f"{role}: missing galaxy_info")
        assert not errors, (
            "Meta issues:\n" + "\n".join(errors)
        )

    def test_meta_has_author(self):
        """All roles declare an author."""
        errors = []
        for role in EXPECTED_ROLES:
            meta = ROLES_DIR / role / "meta" / "main.yml"
            if not meta.exists():
                continue
            data = yaml.safe_load(meta.read_text())
            if not isinstance(data, dict):
                continue
            gi = data.get("galaxy_info", {})
            if not gi.get("author"):
                errors.append(f"{role}: missing galaxy_info.author")
        assert not errors, (
            "Missing author:\n" + "\n".join(errors)
        )


class TestRoleDefaultRanges:
    """Validate that default values are in sensible ranges."""

    def _load_all_defaults(self):
        """Load defaults from all roles."""
        result = {}
        for role in EXPECTED_ROLES:
            defaults = ROLES_DIR / role / "defaults" / "main.yml"
            if defaults.exists():
                data = yaml.safe_load(defaults.read_text())
                if isinstance(data, dict):
                    result[role] = data
        return result

    def test_port_defaults_in_valid_range(self):
        """Any variable ending in _port has value 1-65535."""
        errors = []
        for role, defaults in self._load_all_defaults().items():
            for key, val in defaults.items():
                if key.endswith("_port") and isinstance(val, int) and not (1 <= val <= 65535):
                    errors.append(f"{role}.{key} = {val} (out of range)")
        assert not errors, "Invalid port defaults:\n" + "\n".join(errors)

    def test_retry_defaults_are_positive(self):
        """Any variable with 'retries' or 'retry' has positive integer value."""
        errors = []
        for role, defaults in self._load_all_defaults().items():
            for key, val in defaults.items():
                if ("retries" in key or "retry" in key) and isinstance(val, int) and val <= 0:
                    errors.append(f"{role}.{key} = {val} (not positive)")
        assert not errors, "Non-positive retry defaults:\n" + "\n".join(errors)

    def test_delay_defaults_are_positive(self):
        """Any variable with 'delay' has positive integer value."""
        errors = []
        for role, defaults in self._load_all_defaults().items():
            for key, val in defaults.items():
                if "delay" in key and isinstance(val, int) and val <= 0:
                    errors.append(f"{role}.{key} = {val} (not positive)")
        assert not errors, "Non-positive delay defaults:\n" + "\n".join(errors)

    def test_boolean_defaults_are_booleans(self):
        """Variables ending in _enabled or _apply are actual booleans, not strings."""
        errors = []
        for role, defaults in self._load_all_defaults().items():
            for key, val in defaults.items():
                if key.endswith(("_enabled", "_apply")) and val is not None and not isinstance(val, bool):
                    errors.append(f"{role}.{key} = {val!r} (type {type(val).__name__}, not bool)")
        assert not errors, "Non-boolean flag defaults:\n" + "\n".join(errors)

    def test_timeout_defaults_are_reasonable(self):
        """Timeout defaults are between 1 and 3600 seconds."""
        errors = []
        for role, defaults in self._load_all_defaults().items():
            for key, val in defaults.items():
                if "timeout" in key and isinstance(val, int) and not (1 <= val <= 3600):
                    errors.append(f"{role}.{key} = {val} (outside 1-3600)")
        assert not errors, "Unreasonable timeout defaults:\n" + "\n".join(errors)

    def test_no_namespace_collisions(self):
        """No two unrelated roles share the same default variable name."""
        var_to_roles = {}
        for role, defaults in self._load_all_defaults().items():
            for key in defaults:
                var_to_roles.setdefault(key, []).append(role)
        # Only flag if truly unrelated (no shared prefix)
        collisions = []
        for key, roles in var_to_roles.items():
            if len(roles) > 1:
                # Check if all roles share a common prefix (like incus_)
                prefixes = {r.split("_")[0] for r in roles}
                if len(prefixes) > 1:
                    collisions.append(f"{key}: used by {', '.join(roles)}")
        assert not collisions, "Namespace collisions:\n" + "\n".join(collisions)
