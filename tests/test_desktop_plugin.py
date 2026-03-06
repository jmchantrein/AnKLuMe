"""Tests for Phase 42: Desktop Environment Plugin System.

Covers:
- Plugin directory structure
- Plugin schema (plugin.schema.yml)
- Desktop plugin script (scripts/desktop-plugin.sh)
- Behavior matrix cells DP-001 to DP-003
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


# -- DP-001: Plugin directory structure --------------------------------------


class TestPluginDirectoryStructure:
    """Verify plugin directory exists with expected layout.

    # Matrix: DP-001
    """

    def test_plugin_dir_exists(self):
        assert PLUGIN_DIR.is_dir()

    def test_schema_file_exists(self):
        assert SCHEMA_FILE.is_file()


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
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, result.stdout

    def test_help_command(self):
        result = subprocess.run(
            [str(PLUGIN_SCRIPT), "help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "Usage" in result.stdout
