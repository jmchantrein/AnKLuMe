"""Tests for Phase 26: Native App Export.

Covers:
- Shell syntax validation (export-app.sh)
- Script structure and required functions
- Help output and subcommands
- infra.yml export_apps configuration
- Makefile targets for export-app, export-list, export-remove
"""

import re
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPORT_APP_SH = PROJECT_ROOT / "scripts" / "export-app.sh"
MAKEFILE = PROJECT_ROOT / "Makefile"
INFRA_YML = PROJECT_ROOT / "examples" / "ai-tools" / "infra.yml"


# ── Shell syntax validation ──────────────────────────────


class TestShellSyntax:
    """Verify export-app.sh passes bash -n syntax check."""

    def test_export_app_syntax(self):
        result = subprocess.run(
            ["bash", "-n", str(EXPORT_APP_SH)],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, f"export-app.sh syntax error: {result.stderr}"


# ── Script structure ─────────────────────────────────────


class TestExportAppStructure:
    """Verify export-app.sh contains required structure and patterns."""

    @classmethod
    def setup_class(cls):
        cls.content = EXPORT_APP_SH.read_text()

    def test_shebang(self):
        assert self.content.startswith("#!/usr/bin/env bash")

    def test_set_euo_pipefail(self):
        assert "set -euo pipefail" in self.content

    def test_usage_function(self):
        assert re.search(r'^usage\(\)', self.content, re.MULTILINE)

    def test_subcommand_export(self):
        """Has export subcommand."""
        assert "export" in self.content
        assert "cmd_export" in self.content or "export)" in self.content

    def test_subcommand_list(self):
        """Has list subcommand."""
        assert "list" in self.content
        assert "cmd_list" in self.content or "list)" in self.content

    def test_subcommand_remove(self):
        """Has remove subcommand."""
        assert "remove" in self.content
        assert "cmd_remove" in self.content or "remove)" in self.content

    def test_info_helper(self):
        assert re.search(r'^info\(\)', self.content, re.MULTILINE)

    def test_ok_helper(self):
        assert re.search(r'^ok\(\)', self.content, re.MULTILINE)

    def test_warn_helper(self):
        assert re.search(r'^warn\(\)', self.content, re.MULTILINE)

    def test_err_helper(self):
        assert re.search(r'^err\(\)', self.content, re.MULTILINE)

    def test_die_function(self):
        assert re.search(r'^die\(\)', self.content, re.MULTILINE)

    def test_uses_incus_exec(self):
        """Script uses incus exec to run commands in container."""
        assert "incus exec" in self.content or "incus_exec" in self.content

    def test_uses_incus_file_pull(self):
        """Script uses incus file pull to extract files from container."""
        assert "incus file pull" in self.content or "incus_file_pull" in self.content

    def test_desktop_install_dir(self):
        """Installs .desktop files to ~/.local/share/applications/."""
        assert ".local/share/applications" in self.content

    def test_icon_dir(self):
        """Icons stored in ~/.local/share/icons/anklume/."""
        assert ".local/share/icons/anklume" in self.content

    def test_uses_domain_exec_or_incus_exec(self):
        """Generated .desktop uses domain-exec.sh or incus exec."""
        assert "domain-exec.sh" in self.content or "incus exec" in self.content

    def test_update_desktop_database(self):
        """References update-desktop-database for XDG compliance."""
        assert "update-desktop-database" in self.content


# ── Help output ──────────────────────────────────────────


class TestExportAppHelp:
    """Verify export-app.sh --help produces correct output."""

    def test_help_flag(self):
        result = subprocess.run(
            ["bash", str(EXPORT_APP_SH), "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0

    def test_help_shows_export(self):
        result = subprocess.run(
            ["bash", str(EXPORT_APP_SH), "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert "export" in result.stdout

    def test_help_shows_list(self):
        result = subprocess.run(
            ["bash", str(EXPORT_APP_SH), "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert "list" in result.stdout

    def test_help_shows_remove(self):
        result = subprocess.run(
            ["bash", str(EXPORT_APP_SH), "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert "remove" in result.stdout

    def test_short_help_flag(self):
        result = subprocess.run(
            ["bash", str(EXPORT_APP_SH), "-h"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "export" in result.stdout


# ── infra.yml export_apps ────────────────────────────────


class TestInfraYmlExportApps:
    """Verify examples/ai-tools/infra.yml has export_apps for ai-opencode."""

    @classmethod
    def setup_class(cls):
        cls.content = INFRA_YML.read_text()

    def test_export_apps_key_exists(self):
        assert "export_apps" in self.content

    def test_opencode_in_export_apps(self):
        assert "opencode" in self.content

    def test_export_apps_on_ai_opencode(self):
        """export_apps is defined on the ai-opencode machine."""
        # ai-opencode block should contain export_apps
        ai_opencode_pos = self.content.index("ai-opencode:")
        # Find next machine or end of machines block
        next_section = len(self.content)
        for marker in ["ai-coder:", "network_policies:"]:
            try:
                pos = self.content.index(marker, ai_opencode_pos + 1)
                if pos < next_section:
                    next_section = pos
            except ValueError:
                pass
        block = self.content[ai_opencode_pos:next_section]
        assert "export_apps" in block
        assert "opencode" in block


# ── Makefile targets ─────────────────────────────────────


class TestMakefileTargets:
    """Verify Makefile has export-app, export-list, export-remove targets."""

    @classmethod
    def setup_class(cls):
        cls.content = MAKEFILE.read_text()

    def test_export_app_target(self):
        assert "export-app:" in self.content

    def test_export_list_target(self):
        assert "export-list:" in self.content

    def test_export_remove_target(self):
        assert "export-remove:" in self.content

    def test_export_app_uses_script(self):
        """export-app target invokes export-app.sh."""
        assert "export-app.sh" in self.content

    def test_export_app_in_phony(self):
        """export-app is listed in .PHONY."""
        phony_match = re.search(r'\.PHONY:.*', self.content, re.DOTALL)
        assert phony_match
        assert "export-app" in phony_match.group(0)

    def test_export_list_in_phony(self):
        """export-list is listed in .PHONY."""
        phony_match = re.search(r'\.PHONY:.*', self.content, re.DOTALL)
        assert phony_match
        assert "export-list" in phony_match.group(0)

    def test_export_remove_in_phony(self):
        """export-remove is listed in .PHONY."""
        phony_match = re.search(r'\.PHONY:.*', self.content, re.DOTALL)
        assert phony_match
        assert "export-remove" in phony_match.group(0)
