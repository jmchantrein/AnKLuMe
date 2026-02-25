"""Tests for Phase 42: Desktop Environment Plugin System.

Covers:
- Plugin directory structure
- Plugin schema (plugin.schema.yml)
- Desktop plugin script (scripts/desktop-plugin.sh)
- Reference Sway plugin (detect.sh, apply.sh)
- Behavior matrix cells DP-001 to DP-005, DP-2-001
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_DIR = PROJECT_ROOT / "plugins" / "desktop"
SCHEMA_FILE = PLUGIN_DIR / "plugin.schema.yml"
PLUGIN_SCRIPT = PROJECT_ROOT / "scripts" / "desktop-plugin.sh"
SWAY_DIR = PLUGIN_DIR / "sway"


# -- DP-001: Plugin directory structure --------------------------------------


class TestPluginDirectoryStructure:
    """Verify plugin directory exists with expected layout.

    # Matrix: DP-001
    """

    def test_plugin_dir_exists(self):
        assert PLUGIN_DIR.is_dir()

    def test_schema_file_exists(self):
        assert SCHEMA_FILE.is_file()

    def test_at_least_one_plugin(self):
        """At least one plugin directory with detect.sh exists."""
        plugins = [
            d for d in PLUGIN_DIR.iterdir()
            if d.is_dir() and (d / "detect.sh").is_file()
        ]
        assert len(plugins) >= 1

    def test_sway_plugin_exists(self):
        assert SWAY_DIR.is_dir()


# -- DP-002: Plugin schema ---------------------------------------------------


class TestPluginSchema:
    """Verify plugin schema defines required interface.

    # Matrix: DP-002
    """

    @classmethod
    def setup_class(cls):
        with open(SCHEMA_FILE) as f:
            cls.schema = yaml.safe_load(f)

    def test_has_interface_section(self):
        assert "interface" in self.schema

    def test_has_required_scripts(self):
        interface = self.schema["interface"]
        assert "required_scripts" in interface

    def test_detect_in_required(self):
        scripts = self.schema["interface"]["required_scripts"]
        names = [s["name"] for s in scripts]
        assert "detect.sh" in names

    def test_apply_in_required(self):
        scripts = self.schema["interface"]["required_scripts"]
        names = [s["name"] for s in scripts]
        assert "apply.sh" in names

    def test_has_config_schema(self):
        assert "config_schema" in self.schema

    def test_config_has_domains(self):
        props = self.schema["config_schema"]["properties"]
        assert "domains" in props

    def test_has_trust_level_colors(self):
        assert "trust_level_colors" in self.schema

    def test_all_trust_levels_have_colors(self):
        colors = self.schema["trust_level_colors"]
        for level in ["admin", "trusted", "semi-trusted",
                      "untrusted", "disposable"]:
            assert level in colors, f"Missing color for {level}"


# -- DP-003: Desktop plugin script -------------------------------------------


class TestDesktopPluginScript:
    """Verify scripts/desktop-plugin.sh works.

    # Matrix: DP-003
    """

    def test_script_exists(self):
        assert PLUGIN_SCRIPT.is_file()

    def test_script_executable(self):
        assert os.access(PLUGIN_SCRIPT, os.X_OK)

    @pytest.mark.skipif(
        not shutil.which("shellcheck"),
        reason="shellcheck not installed",
    )
    def test_shellcheck_clean(self):
        result = subprocess.run(
            ["shellcheck", "-S", "warning", str(PLUGIN_SCRIPT)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stdout

    def test_list_command(self):
        """desktop-plugin.sh list runs without error."""
        result = subprocess.run(
            [str(PLUGIN_SCRIPT), "list"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "sway" in result.stdout.lower() or "Available" in result.stdout

    def test_help_command(self):
        result = subprocess.run(
            [str(PLUGIN_SCRIPT), "help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "Usage" in result.stdout


# -- DP-004: Reference plugin detect.sh -------------------------------------


class TestSwayDetect:
    """Verify Sway plugin has a working detect.sh.

    # Matrix: DP-004
    """

    def test_detect_exists(self):
        assert (SWAY_DIR / "detect.sh").is_file()

    def test_detect_executable(self):
        assert os.access(SWAY_DIR / "detect.sh", os.X_OK)

    @pytest.mark.skipif(
        not shutil.which("shellcheck"),
        reason="shellcheck not installed",
    )
    def test_detect_shellcheck(self):
        result = subprocess.run(
            ["shellcheck", "-S", "warning",
             str(SWAY_DIR / "detect.sh")],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stdout

    def test_detect_runs(self):
        """detect.sh runs without crashing (may return 1 if not in Sway)."""
        result = subprocess.run(
            ["bash", str(SWAY_DIR / "detect.sh")],
            capture_output=True, text=True, timeout=5,
        )
        # Return 0 (Sway active) or 1 (not active) — both valid
        assert result.returncode in (0, 1)


# -- DP-005: Reference plugin apply.sh --------------------------------------


class TestSwayApply:
    """Verify Sway plugin has a working apply.sh.

    # Matrix: DP-005
    """

    def test_apply_exists(self):
        assert (SWAY_DIR / "apply.sh").is_file()

    def test_apply_executable(self):
        assert os.access(SWAY_DIR / "apply.sh", os.X_OK)

    @pytest.mark.skipif(
        not shutil.which("shellcheck"),
        reason="shellcheck not installed",
    )
    def test_apply_shellcheck(self):
        result = subprocess.run(
            ["shellcheck", "-S", "warning",
             str(SWAY_DIR / "apply.sh")],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stdout

    def test_apply_dry_run(self):
        """apply.sh --dry-run with config produces output."""
        config = (
            '{"domains":[{"name":"test","trust_level":"admin",'
            '"color":"#1565C0","machines":["test-vm"]}],'
            '"virtual_desktops":"auto","window_borders":"trust_level"}'
        )
        result = subprocess.run(
            ["bash", str(SWAY_DIR / "apply.sh"), "--dry-run"],
            input=config, capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "anklume" in result.stdout


# -- DP-2-001: Plugin framework discovery ------------------------------------


class TestPluginDiscovery:
    """Verify plugin framework discovers all plugins.

    # Matrix: DP-2-001
    """

    def test_list_shows_sway(self):
        result = subprocess.run(
            [str(PLUGIN_SCRIPT), "list"],
            capture_output=True, text=True, timeout=10,
        )
        assert "sway" in result.stdout.lower()

    def test_validate_passes(self):
        result = subprocess.run(
            [str(PLUGIN_SCRIPT), "validate"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
