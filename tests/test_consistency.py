"""Bidirectional consistency tests enforcing development workflows.

These tests verify the impact chains defined in scripts/impact-chains.yml.
When you add a file without updating the corresponding mechanism, a test
fails automatically. See the manifest for the full chain list.
"""

import os
import re
import stat
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "scripts" / "impact-chains.yml"
CLI_DIR = ROOT / "scripts" / "cli"
SCRIPTS_DIR = ROOT / "scripts"
TESTS_DIR = ROOT / "tests"
DOCS_DIR = ROOT / "docs"

# ── Helpers ──────────────────────────────────────────────────────


def _cli_public_modules() -> list[str]:
    """Return CLI module filenames (non-private, non-dunder)."""
    return sorted(
        f for f in os.listdir(CLI_DIR)
        if f.endswith(".py")
        and f[0].islower()
        and not f.startswith("_")
    )


def _cli_module_names() -> set[str]:
    """Return CLI module names without .py extension."""
    return {f.removesuffix(".py") for f in _cli_public_modules()}


def _init_imported_modules() -> set[str]:
    """Return module names imported in __init__.py."""
    content = (CLI_DIR / "__init__.py").read_text()
    return set(re.findall(r"from scripts\.cli\.([a-z]\w*) import", content))


def _python_scripts() -> list[str]:
    """Return Python scripts in scripts/ (non-dunder, non-private)."""
    return sorted(
        f for f in os.listdir(SCRIPTS_DIR)
        if f.endswith(".py")
        and f[0].islower()
        and not f.startswith("__")
    )


def _shell_scripts() -> list[Path]:
    """Return .sh files in scripts/."""
    return sorted(SCRIPTS_DIR.glob("*.sh"))


def _english_docs() -> list[str]:
    """Return English doc filenames (exclude .fr.md and decisions-log)."""
    return sorted(
        f for f in os.listdir(DOCS_DIR)
        if f.endswith(".md")
        and f[0].islower()
        and not f.endswith(".fr.md")
        and f != "decisions-log.md"
    )


# ── CLI: bidirectional import check ─────────────────────────────


class TestCLIModuleImports:
    """Every CLI module is imported in __init__.py and vice versa."""

    def test_all_cli_modules_imported(self):
        """Every scripts/cli/<name>.py is imported in __init__.py."""
        expected = _cli_module_names()
        imported = _init_imported_modules()
        missing = expected - imported
        assert not missing, (
            f"CLI modules not imported in __init__.py: {sorted(missing)}. "
            f"Add 'from scripts.cli.<name> import app as <name>_app'."
        )

    def test_no_phantom_imports(self):
        """Every import in __init__.py has a corresponding module file."""
        imported = _init_imported_modules()
        existing = _cli_module_names()
        # Exclude private modules imported for helpers
        public_imports = {m for m in imported if not m.startswith("_")}
        phantom = public_imports - existing
        assert not phantom, (
            f"__init__.py imports modules that don't exist: {sorted(phantom)}. "
            f"Remove the dead imports."
        )


# ── CLI: tree coverage bidirectional ────────────────────────────


class TestCLITreeCoverage:
    """Every Typer command group/subcommand is in the tree test GROUPS."""

    @pytest.fixture(autouse=True)
    def _load_app(self):
        from scripts.cli import app
        from tests.test_cli_tree_coverage import GROUPS, _get_group_names
        self.app = app
        self.groups = GROUPS
        self.get_group_names = _get_group_names

    def test_all_app_groups_in_tree_test(self):
        """Every registered Typer group is declared in GROUPS."""
        registered = set(self.get_group_names())
        declared = set(self.groups.keys())
        missing = registered - declared
        assert not missing, (
            f"Groups in app but not in test_cli_tree_coverage.GROUPS: "
            f"{sorted(missing)}. Add them."
        )

    def test_all_app_subcommands_in_tree_test(self):
        """Every subcommand in each group is declared in GROUPS[group]."""
        from tests.test_cli_tree_coverage import (
            _get_command_names,
            _get_group_app,
        )
        errors = []
        for group_name in self.groups:
            ga = _get_group_app(group_name)
            if ga is None:
                continue
            actual = set(_get_command_names(ga))
            expected = set(self.groups[group_name])
            missing = actual - expected
            if missing:
                errors.append(
                    f"  {group_name}: {sorted(missing)} not in GROUPS"
                )
        assert not errors, (
            "Subcommands in app but not in tree test:\n"
            + "\n".join(errors)
        )


# ── Python scripts: test file coverage ──────────────────────────

# Scripts tested indirectly via their callers or too small to warrant
# a dedicated test file. Shrink this list over time.
_SCRIPT_TEST_EXCEPTIONS = {
    "colors.py",                  # Pure constants, tested via importers
    "create-data-dirs.py",        # Thin CLI wrapper
    "create-shares.py",           # Thin CLI wrapper
    "dashboard.py",               # Interactive TUI, tested via test_web_*
    "desktop_config.py",          # Tested via test_desktop.py
    "generate-bdd-stubs.py",      # Dev tool, tested indirectly
    "generate-dep-scenarios.py",  # Dev tool, tested indirectly
    "help-i18n.py",               # i18n helper, tested via test_student_mode
    "live-os-test-graphical.py",  # E2E test runner (not testable itself)
    "live-os-test-interactive.py",  # E2E test runner
    "live-os-test-qemu.py",      # E2E test runner
    "mcp-client.py",              # Tested via test_mcp.py
    "mcp-policy.py",              # Tested via test_mcp.py
    "mcp-server.py",              # Tested via test_mcp.py
    "ollama-dev.py",              # Dev tool, tested via LLM tests
    "platform_server.py",         # Tested via test_platform.py
    "qemu-screenshot.py",         # E2E test utility
    "run-behavioral-tests.py",    # Test runner wrapper
    "e2e-test-iso.py",            # E2E test runner
    "guide_chapters.py",          # Data module for guide content
    "guide_strings.py",           # Data module for guide i18n strings
    "welcome.py",                 # Live OS only, tested via test_welcome
    "welcome_strings.py",         # Data module for welcome
}


class TestPythonScriptCoverage:
    """Every Python script has a corresponding test file."""

    @pytest.mark.parametrize("script", _python_scripts())
    def test_every_script_has_test(self, script):
        if script in _SCRIPT_TEST_EXCEPTIONS:
            pytest.skip(f"{script} is in exceptions list")
        base = script.replace(".py", "").replace("-", "_")
        test_name = f"test_{base}.py"
        assert (TESTS_DIR / test_name).exists(), (
            f"No test file for scripts/{script}. "
            f"Expected: tests/{test_name}"
        )


# ── Shell scripts: executable + strict mode ─────────────────────

# Sourced library scripts (not directly executed).
# Sourced library scripts and config scripts (no set -e needed).
_SHELL_NO_STRICT = {
    "ai-config.sh",       # Config/env sourced by other scripts
    "doctor-checks.sh",   # Sourced library
    "doctor-network.sh",  # Sourced library
    "domain-lib.sh",      # Sourced library
    "lab-lib.sh",         # Sourced library
    "live-os-lib.sh",     # Sourced library
}

# Sourced libraries (not directly executed, no +x needed).
_SHELL_LIB_SCRIPTS = {
    "doctor-checks.sh",
    "doctor-network.sh",
    "domain-lib.sh",
    "lab-lib.sh",
    "live-os-lib.sh",
}


class TestShellScriptQuality:
    """Shell scripts are executable and use strict mode."""

    @pytest.mark.parametrize(
        "script", _shell_scripts(), ids=lambda p: p.name,
    )
    def test_is_executable(self, script):
        if script.name in _SHELL_LIB_SCRIPTS:
            pytest.skip(f"{script.name} is a sourced library")
        mode = script.stat().st_mode
        assert mode & stat.S_IXUSR, (
            f"{script.name} is not executable. Run: chmod +x {script}"
        )

    @pytest.mark.parametrize(
        "script", _shell_scripts(), ids=lambda p: p.name,
    )
    def test_has_strict_mode(self, script):
        if script.name in _SHELL_NO_STRICT:
            pytest.skip(f"{script.name} is a sourced library/config")
        content = script.read_text()[:2000]
        assert "set -e" in content, (
            f"{script.name} does not use 'set -e' in its first 2000 chars."
        )


# ── Documentation: French translation ───────────────────────────


class TestDocTranslations:
    """Every English doc has a French counterpart."""

    @pytest.mark.parametrize("doc", _english_docs())
    def test_every_doc_has_fr_translation(self, doc):
        fr_name = doc.replace(".md", ".fr.md")
        assert (DOCS_DIR / fr_name).exists(), (
            f"No French translation for docs/{doc}. "
            f"Expected: docs/{fr_name}"
        )


# ── Manifest self-validation ────────────────────────────────────

# Map from check names in the manifest to test method names in this file.
_CHECK_TO_TEST = {
    "imported_in_init": "TestCLIModuleImports::test_all_cli_modules_imported",
    "in_tree_coverage_test": "TestCLITreeCoverage::test_all_app_subcommands_in_tree_test",
    "has_test_file": "TestPythonScriptCoverage::test_every_script_has_test",
    "is_executable": "TestShellScriptQuality::test_is_executable",
    "has_strict_mode": "TestShellScriptQuality::test_has_strict_mode",
    "has_fr_counterpart": "TestDocTranslations::test_every_doc_has_fr_translation",
}


class TestManifestIntegrity:
    """The impact-chains.yml manifest is valid and fully covered."""

    @pytest.fixture(autouse=True)
    def _load_manifest(self):
        with open(MANIFEST) as fh:
            self.manifest = yaml.safe_load(fh)

    def test_manifest_parses(self):
        assert "chains" in self.manifest
        assert isinstance(self.manifest["chains"], dict)
        assert len(self.manifest["chains"]) > 0

    def test_chains_have_required_fields(self):
        for name, chain in self.manifest["chains"].items():
            assert "trigger" in chain, f"Chain '{name}' missing 'trigger'"
            assert "checks" in chain, f"Chain '{name}' missing 'checks'"
            assert "description" in chain, f"Chain '{name}' missing 'description'"

    def test_triggers_match_real_files(self):
        """Every trigger pattern matches at least one file."""
        import glob as globmod

        for name, chain in self.manifest["chains"].items():
            pattern = str(ROOT / chain["trigger"])
            matches = globmod.glob(pattern)
            assert matches, (
                f"Chain '{name}' trigger '{chain['trigger']}' "
                f"matches no files."
            )

    def test_all_checks_have_tests(self):
        """Every check referenced in the manifest maps to a test."""
        all_checks = set()
        for chain in self.manifest["chains"].values():
            all_checks.update(chain["checks"])

        covered = set(_CHECK_TO_TEST.keys())
        uncovered = all_checks - covered
        assert not uncovered, (
            f"Checks without corresponding tests: {sorted(uncovered)}. "
            f"Add entries to _CHECK_TO_TEST in test_consistency.py."
        )

    def test_check_map_has_no_orphans(self):
        """Every entry in _CHECK_TO_TEST is used by the manifest."""
        all_checks = set()
        for chain in self.manifest["chains"].values():
            all_checks.update(chain["checks"])

        orphans = set(_CHECK_TO_TEST.keys()) - all_checks
        assert not orphans, (
            f"_CHECK_TO_TEST entries not in manifest: {sorted(orphans)}. "
            f"Remove them or add the check to a chain."
        )
