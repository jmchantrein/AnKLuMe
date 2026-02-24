"""Tests for role defaults — checks that linters cannot perform.

Covers: role existence, tasks/main.yml presence, variable type safety,
template-to-defaults coherence, and role list accuracy.
"""

import re
from pathlib import Path

import yaml

ROLES_DIR = Path(__file__).resolve().parent.parent / "roles"

EXPECTED_ROLES = sorted([
    "admin_bootstrap",
    "base_system",
    "code_sandbox",
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
    "openclaw_server",
    "opencode_server",
    "open_webui",
    "stt_server",
])


def _load_defaults(role: str) -> dict:
    """Load a role's defaults/main.yml, returning {} if absent or empty."""
    path = ROLES_DIR / role / "defaults" / "main.yml"
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text())
    return data if isinstance(data, dict) else {}


# --- Role existence and structure ---


class TestRoleStructure:
    def test_expected_roles_match_disk(self):
        """EXPECTED_ROLES constant matches actual directories under roles/."""
        actual = sorted(
            d.name for d in ROLES_DIR.iterdir()
            if d.is_dir() and not d.name.startswith(".") and not d.name.startswith("_")
        )
        assert actual == EXPECTED_ROLES, (
            f"Mismatch:\n  on disk only: {set(actual) - set(EXPECTED_ROLES)}"
            f"\n  in constant only: {set(EXPECTED_ROLES) - set(actual)}"
        )

    def test_all_roles_exist(self):
        """All 18 expected roles exist as directories."""
        missing = [r for r in EXPECTED_ROLES if not (ROLES_DIR / r).is_dir()]
        assert not missing, f"Missing role directories: {missing}"

    def test_all_roles_have_tasks_main(self):
        """Every role has tasks/main.yml — without this the playbook fails."""
        missing = [
            r for r in EXPECTED_ROLES
            if not (ROLES_DIR / r / "tasks" / "main.yml").exists()
        ]
        assert not missing, f"Roles missing tasks/main.yml: {missing}"


# --- Variable type safety (linters cannot check YAML value types) ---


class TestVariableTypes:
    def test_port_variables_are_integers(self):
        """Variables ending in _port must be int (not string '8080')."""
        errors = []
        for role in EXPECTED_ROLES:
            for key, val in _load_defaults(role).items():
                if key.endswith("_port") and not isinstance(val, int):
                    errors.append(f"{role}.{key} = {val!r} ({type(val).__name__})")
        assert not errors, "Port variables must be int:\n" + "\n".join(errors)

    # Variables ending in _host that aren't hostnames (e.g., "import_from_host")
    _HOST_EXCEPTIONS = {"incus_images_import_from_host"}

    def test_host_variables_are_strings(self):
        """Variables ending in _host (hostnames) must be str (not int or bool)."""
        errors = []
        for role in EXPECTED_ROLES:
            for key, val in _load_defaults(role).items():
                if (
                    key.endswith("_host")
                    and key not in self._HOST_EXCEPTIONS
                    and not isinstance(val, str)
                ):
                    errors.append(f"{role}.{key} = {val!r} ({type(val).__name__})")
        assert not errors, "Host variables must be str:\n" + "\n".join(errors)

    def test_port_values_in_valid_range(self):
        """Port defaults are in 1-65535 range."""
        errors = []
        for role in EXPECTED_ROLES:
            for key, val in _load_defaults(role).items():
                if (
                    key.endswith("_port")
                    and isinstance(val, int)
                    and not 1 <= val <= 65535
                ):
                    errors.append(f"{role}.{key} = {val}")
        assert not errors, "Ports out of range:\n" + "\n".join(errors)


# --- Template-to-defaults coherence ---


class TestTemplateCoherence:
    """Templates referencing role-prefixed variables must have them in defaults.

    This catches real bugs: a variable renamed in defaults but not in the
    template, or a typo in a template variable name.  Linters cannot detect
    this because they don't cross-reference Jinja2 templates with YAML defaults.
    """

    _VAR_RE = re.compile(r"\{\{\s*([a-z][a-z0-9_]*)\s*[\|}\s]")

    # Variables set at runtime (registered vars, set_fact) — not in defaults
    _RUNTIME_VARS = {"incus_nftables_all_bridges", "stt_server_effective_compute"}

    def test_template_vars_exist_in_defaults(self):
        errors = []
        for role in EXPECTED_ROLES:
            tpl_dir = ROLES_DIR / role / "templates"
            if not tpl_dir.exists():
                continue
            defaults = _load_defaults(role)
            # Determine the role prefix(es) for filtering
            prefixes = (role + "_",)
            if "_" in role:
                prefixes += (role.split("_")[0] + "_",)

            for tpl in sorted(tpl_dir.glob("*.j2")):
                content = tpl.read_text()
                refs = set(self._VAR_RE.findall(content))
                for var in sorted(refs):
                    if var in self._RUNTIME_VARS:
                        continue
                    if (
                        any(var.startswith(p) for p in prefixes)
                        and var not in defaults
                    ):
                            errors.append(
                                f"{role}/{tpl.name}: "
                                f"{{ {var} }} not in defaults"
                            )
        assert not errors, (
            "Template variables missing from defaults:\n"
            + "\n".join(errors)
        )
