"""Tests for Phase 25: XDG Desktop Portal for Cross-Domain File Access.

Covers:
- Shell syntax validation (file-portal.sh)
- Script structure: shebang, set -euo pipefail, functions, subcommands
- Help output and exit code
- Audit log configuration
- infra.yml file_portal config
- Makefile portal targets
"""

import re
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FILE_PORTAL_SH = PROJECT_ROOT / "scripts" / "file-portal.sh"
MAKEFILE = PROJECT_ROOT / "Makefile"
INFRA_YML = PROJECT_ROOT / "examples" / "ai-tools" / "infra.yml"


# ── Shell syntax validation ──────────────────────────────


class TestShellSyntax:
    """Verify file-portal.sh passes bash -n syntax check."""

    def test_file_portal_syntax(self):
        result = subprocess.run(
            ["bash", "-n", str(FILE_PORTAL_SH)],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, f"file-portal.sh syntax error: {result.stderr}"


# ── Script structure ─────────────────────────────────────


class TestFilePortalStructure:
    """Verify file-portal.sh contains expected structure and features."""

    @classmethod
    def setup_class(cls):
        cls.content = FILE_PORTAL_SH.read_text()

    def test_shebang(self):
        assert self.content.startswith("#!/usr/bin/env bash")

    def test_set_euo_pipefail(self):
        assert "set -euo pipefail" in self.content

    def test_usage_function(self):
        assert "usage()" in self.content

    def test_subcommand_open(self):
        assert "open" in self.content

    def test_subcommand_push(self):
        assert "push" in self.content

    def test_subcommand_pull(self):
        assert "pull" in self.content

    def test_subcommand_list(self):
        assert "list" in self.content

    def test_audit_log_function(self):
        assert "audit_log()" in self.content

    def test_check_policy_function(self):
        assert "check_policy()" in self.content

    def test_die_function(self):
        assert "die()" in self.content

    def test_reads_file_portal_from_infra(self):
        """Script uses inline python3 to read file_portal config."""
        assert "python3" in self.content
        assert "file_portal" in self.content

    def test_uses_incus_file_push(self):
        """Script uses incus file push for transfers."""
        assert "file push" in self.content

    def test_uses_incus_file_pull(self):
        """Script uses incus file pull for transfers."""
        assert "file pull" in self.content

    def test_enforces_allowed_paths(self):
        """Script checks container paths against allowed_paths."""
        assert "allowed_paths" in self.content

    def test_enforces_read_only(self):
        """Script checks read_only flag to block push operations."""
        assert "read_only" in self.content

    def test_info_function(self):
        assert "info()" in self.content

    def test_find_project(self):
        """Script resolves instance to project like transfer.sh."""
        assert "find_project" in self.content

    def test_xdg_open(self):
        """Open subcommand uses xdg-open."""
        assert "xdg-open" in self.content


# ── Help output ──────────────────────────────────────────


class TestFilePortalHelp:
    """Verify --help output contains subcommands and exits 0."""

    def test_help_flag(self):
        result = subprocess.run(
            ["bash", str(FILE_PORTAL_SH), "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "open" in result.stdout
        assert "push" in result.stdout
        assert "pull" in result.stdout
        assert "list" in result.stdout

    def test_help_subcommand(self):
        result = subprocess.run(
            ["bash", str(FILE_PORTAL_SH), "help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "open" in result.stdout
        assert "push" in result.stdout

    def test_no_args_shows_help(self):
        result = subprocess.run(
            ["bash", str(FILE_PORTAL_SH)],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "open" in result.stdout or "Usage" in result.stdout


# ── Audit log path ───────────────────────────────────────


class TestFilePortalAuditLog:
    """Verify audit log path is ~/.anklume/portal-audit.log."""

    @classmethod
    def setup_class(cls):
        cls.content = FILE_PORTAL_SH.read_text()

    def test_audit_log_path(self):
        assert "portal-audit.log" in self.content

    def test_audit_log_home_dir(self):
        assert ".anklume/portal-audit.log" in self.content

    def test_audit_log_timestamp(self):
        """Audit log entries include a timestamp."""
        assert "timestamp" in self.content or "date" in self.content

    def test_audit_log_action(self):
        """Audit log entries include the action."""
        assert "action=" in self.content

    def test_audit_log_instance(self):
        """Audit log entries include the instance."""
        assert "instance=" in self.content


# ── infra.yml file_portal config ─────────────────────────


class TestInfraYmlFilePortal:
    """Verify examples/ai-tools/infra.yml has file_portal config."""

    @classmethod
    def setup_class(cls):
        cls.content = INFRA_YML.read_text()

    def test_file_portal_key(self):
        assert "file_portal:" in self.content

    def test_allowed_paths(self):
        assert "allowed_paths:" in self.content

    def test_read_only(self):
        assert "read_only:" in self.content

    def test_shared_ai_tools_path(self):
        assert "/shared/ai-tools" in self.content

    def test_tmp_portal_path(self):
        assert "/tmp/portal" in self.content

    def test_in_ai_tools_domain(self):
        """file_portal config is under the ai-tools domain."""
        ai_tools_pos = self.content.index("ai-tools:")
        file_portal_pos = self.content.index("file_portal:")
        # file_portal should appear after ai-tools domain declaration
        assert file_portal_pos > ai_tools_pos


# ── Makefile targets ─────────────────────────────────────


class TestMakefileTargets:
    """Verify portal-open, portal-push, portal-pull, portal-list targets."""

    @classmethod
    def setup_class(cls):
        cls.content = MAKEFILE.read_text()

    def test_portal_open_target(self):
        assert "portal-open:" in self.content

    def test_portal_push_target(self):
        assert "portal-push:" in self.content

    def test_portal_pull_target(self):
        assert "portal-pull:" in self.content

    def test_portal_list_target(self):
        assert "portal-list:" in self.content

    def test_portal_open_calls_script(self):
        assert "file-portal.sh open" in self.content

    def test_portal_push_calls_script(self):
        assert "file-portal.sh push" in self.content

    def test_portal_pull_calls_script(self):
        assert "file-portal.sh pull" in self.content

    def test_portal_list_calls_script(self):
        assert "file-portal.sh list" in self.content

    def test_portal_open_phony(self):
        phony_match = re.search(r'\.PHONY:.*', self.content, re.DOTALL)
        assert phony_match
        assert "portal-open" in phony_match.group(0)

    def test_portal_push_phony(self):
        phony_match = re.search(r'\.PHONY:.*', self.content, re.DOTALL)
        assert phony_match
        assert "portal-push" in phony_match.group(0)

    def test_portal_pull_phony(self):
        phony_match = re.search(r'\.PHONY:.*', self.content, re.DOTALL)
        assert phony_match
        assert "portal-pull" in phony_match.group(0)

    def test_portal_list_phony(self):
        phony_match = re.search(r'\.PHONY:.*', self.content, re.DOTALL)
        assert phony_match
        assert "portal-list" in phony_match.group(0)

    def test_portal_section_comment(self):
        """Phase 25 section comment exists."""
        assert "File Portal" in self.content
