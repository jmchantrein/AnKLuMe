"""Tests for scripts/doctor.sh — infrastructure health checker.

Covers: script existence, shellcheck, --help, --check with unknown
category, and structural verification of expected check functions.
Does not test behaviors requiring live Incus or network access.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = PROJECT_ROOT / "scripts" / "doctor.sh"


class TestDoctor:
    """Tests for doctor.sh behavior."""

    def test_script_exists(self):
        """doctor.sh exists and is executable."""
        assert SCRIPT.exists()
        assert os.access(SCRIPT, os.X_OK)

    @pytest.mark.skipif(
        shutil.which("shellcheck") is None,
        reason="shellcheck not installed",
    )
    def test_shellcheck(self):
        """doctor.sh passes shellcheck."""
        result = subprocess.run(
            ["shellcheck", "--severity=warning", str(SCRIPT)],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, (
            f"shellcheck errors:\n{result.stdout}\n{result.stderr}"
        )

    def test_help_shows_usage(self):
        """--help flag shows usage information and exits 0."""
        result = subprocess.run(
            ["bash", str(SCRIPT), "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "Usage" in result.stdout
        assert "network" in result.stdout
        assert "instances" in result.stdout
        assert "config" in result.stdout
        assert "deps" in result.stdout

    def test_help_mentions_fix_flag(self):
        """--help output mentions the --fix flag."""
        result = subprocess.run(
            ["bash", str(SCRIPT), "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert "--fix" in result.stdout

    def test_help_mentions_verbose_flag(self):
        """--help output mentions the --verbose flag."""
        result = subprocess.run(
            ["bash", str(SCRIPT), "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert "--verbose" in result.stdout

    def test_unknown_option_exits_nonzero(self):
        """Unknown option exits non-zero with error message."""
        result = subprocess.run(
            ["bash", str(SCRIPT), "--nonexistent-flag"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0
        assert "Unknown option" in result.stdout or "Unknown option" in result.stderr

    def test_unknown_category_exits_nonzero(self):
        """--check with unknown category exits non-zero."""
        result = subprocess.run(
            ["bash", str(SCRIPT), "--check", "nonexistent-category"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0
        assert "Unknown category" in result.stdout or "Unknown category" in result.stderr

    def test_valid_categories_accepted(self):
        """All documented categories are accepted in the case statement.

        Verifies the script source contains case branches for each
        expected category, without requiring live Incus.
        """
        content = SCRIPT.read_text()
        for category in ("network", "instances", "config", "deps", "all"):
            assert f"{category})" in content, (
                f"Category '{category}' not found in case statement"
            )

    def test_expected_check_functions_exist(self):
        """All expected check_* functions are defined in the script."""
        content = SCRIPT.read_text()
        expected_functions = [
            "check_orphan_veths",
            "check_stale_routes",
            "check_nat_rules",
            "check_dns_dhcp_chains",
            "check_bridge_health",
            "check_incus_running",
            "check_anklume_running",
            "check_container_connectivity",
            "check_ip_drift",
            "check_container_deps",
        ]
        for func in expected_functions:
            assert f"{func}()" in content, (
                f"Expected function '{func}' not found in doctor.sh"
            )

    def test_expected_runner_functions_exist(self):
        """All expected run_*_checks() runner functions are defined."""
        content = SCRIPT.read_text()
        expected_runners = [
            "run_network_checks",
            "run_instance_checks",
            "run_config_checks",
            "run_deps_checks",
        ]
        for runner in expected_runners:
            assert f"{runner}()" in content, (
                f"Expected runner '{runner}' not found in doctor.sh"
            )

    def test_output_helpers_defined(self):
        """Output helper functions (result_ok, result_warn, result_err) exist."""
        content = SCRIPT.read_text()
        for helper in ("result_ok", "result_warn", "result_err"):
            assert f"{helper}()" in content, (
                f"Expected helper '{helper}' not found in doctor.sh"
            )

    def test_cleanup_trap_defined(self):
        """Script defines a cleanup trap for the temporary container."""
        content = SCRIPT.read_text()
        assert "trap cleanup EXIT" in content

    def test_summary_section_exists(self):
        """Script has a summary section printing pass/warn/err counts."""
        content = SCRIPT.read_text()
        assert "Summary" in content
        assert "PASS" in content
        assert "WARN" in content
        assert "ERR" in content

    def test_exit_code_logic(self):
        """Script exits with non-zero status when errors are found."""
        content = SCRIPT.read_text()
        # The script uses: exit $(( ERR > 0 ? 1 : 0 ))
        assert "ERR > 0" in content or "ERR -gt 0" in content

    def test_fix_mode_detection(self):
        """Script detects --fix flag and reports fix mode."""
        content = SCRIPT.read_text()
        assert "FIX=true" in content
        assert "auto-fix" in content.lower() or "auto-fix mode" in content.lower()

    def test_verbose_mode_detection(self):
        """Script detects --verbose flag."""
        content = SCRIPT.read_text()
        assert "VERBOSE=true" in content
