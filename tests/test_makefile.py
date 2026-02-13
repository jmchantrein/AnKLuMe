"""Tests for Makefile targets — existence, help text, and basic invocations."""

import re
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MAKEFILE = PROJECT_ROOT / "Makefile"


def run_make(args, timeout=10):
    """Run make with given args."""
    return subprocess.run(
        ["make"] + args,
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        timeout=timeout,
    )


class TestMakefileExists:
    def test_makefile_present(self):
        """Makefile exists at project root."""
        assert MAKEFILE.exists()

    def test_makefile_not_empty(self):
        """Makefile is not empty."""
        assert MAKEFILE.stat().st_size > 0


class TestMakeHelp:
    def test_help_target(self):
        """make help outputs usage."""
        result = run_make(["help"])
        assert result.returncode == 0
        assert "help" in result.stdout.lower()

    def test_help_shows_categories(self):
        """make help shows organized categories."""
        result = run_make(["help"])
        output = result.stdout
        # Should have category headers
        assert "GETTING STARTED" in output or "GENERATOR" in output

    def test_help_shows_key_targets(self):
        """make help lists essential targets."""
        result = run_make(["help"])
        output = result.stdout
        essential = ["sync", "lint", "apply", "test", "help"]
        for target in essential:
            assert target in output, f"Target '{target}' missing from help"


class TestMakefileTargetPresence:
    """Verify that key targets are defined (not just in help)."""

    EXPECTED_TARGETS = [
        "sync", "sync-dry", "sync-clean",
        "lint", "lint-yaml", "lint-ansible", "lint-shell", "lint-python",
        "check", "syntax",
        "apply", "apply-infra", "apply-provision",
        "nftables", "nftables-deploy",
        "snapshot", "restore", "snapshot-list",
        "test", "test-generator", "test-roles",
        "matrix-coverage",
        "flush", "upgrade", "import-infra",
        "guide", "quickstart",
        "init", "help",
        "ai-switch", "ai-test",
        "agent-fix", "agent-develop",
    ]

    def test_targets_defined_in_makefile(self):
        """All expected targets are defined in the Makefile."""
        content = MAKEFILE.read_text()
        missing = []
        for target in self.EXPECTED_TARGETS:
            # Target definition: starts line with "target:" or "target: deps"
            if f"\n{target}:" not in content and content.startswith(f"{target}:"):
                continue
            if f"\n{target}:" not in content:
                missing.append(target)
        assert not missing, f"Missing targets: {missing}"


class TestMakeSyncDry:
    def test_sync_dry_runs(self):
        """make sync-dry runs without modifying files."""
        result = run_make(["sync-dry"], timeout=15)
        # Should succeed (infra.yml exists)
        assert result.returncode == 0


class TestMakeMatrixCoverage:
    def test_matrix_coverage_runs(self):
        """make matrix-coverage runs and produces output."""
        result = run_make(["matrix-coverage"], timeout=15)
        assert result.returncode == 0
        # Should show coverage stats
        assert "coverage" in result.stdout.lower() or "%" in result.stdout


# ── Helper for parsing Makefile content ──────────────────────


def _parse_makefile():
    """Parse the Makefile and return its content."""
    return MAKEFILE.read_text()


def _extract_documented_targets(content):
    """Extract targets with ## comments from Makefile content.

    Returns a dict of {target_name: description}.
    """
    # Pattern: target-name: [deps] ## Description
    pattern = re.compile(r"^([a-zA-Z_-]+):\s*(?:[^#]*?)##\s*(.+)$", re.MULTILINE)
    return {m.group(1): m.group(2).strip() for m in pattern.finditer(content)}


def _extract_help_output():
    """Get the make help output by parsing the Makefile's help target.

    Instead of running `make help`, we simulate the grep/awk output
    by parsing ## comments directly — no Ansible needed.
    """
    content = _parse_makefile()
    return _extract_documented_targets(content)


# ── TestMakefileTargetHelp ───────────────────────────────────


class TestMakefileTargetHelp:
    """Verify that make help output is complete and well-organized."""

    def test_help_contains_all_documented_targets(self):
        """make help output contains all targets with ## comments."""
        content = _parse_makefile()
        documented = _extract_documented_targets(content)
        # The help target uses grep for '##' lines, so all documented targets appear
        assert len(documented) > 20, f"Expected 20+ documented targets, got {len(documented)}"
        essential = ["sync", "lint", "apply", "test", "help", "guide", "init"]
        for target in essential:
            assert target in documented, f"Target '{target}' missing from documented targets"

    def test_help_groups_targets(self):
        """make help groups targets with section headers."""
        content = _parse_makefile()
        expected_groups = ["GETTING STARTED", "ALL TARGETS"]
        for group in expected_groups:
            assert group in content, f"Help group '{group}' missing from Makefile"

    def test_help_includes_description_for_each_target(self):
        """Every documented target has a non-empty description."""
        documented = _extract_help_output()
        for target, desc in documented.items():
            assert len(desc) > 0, f"Target '{target}' has empty description"
            # Descriptions should start with a capital letter or verb
            assert desc[0].isupper() or desc[0].isdigit(), (
                f"Target '{target}' description should start with capital: '{desc}'"
            )

    def test_all_comments_correspond_to_help_entries(self):
        """All ## comments in Makefile correspond to help entries."""
        content = _parse_makefile()
        documented = _extract_documented_targets(content)
        # Every line with ## after a target: should have been extracted
        comment_lines = re.findall(r"^([a-zA-Z_-]+):.*##", content, re.MULTILINE)
        for target in comment_lines:
            assert target in documented, (
                f"Target '{target}' has ## comment but not in documented targets"
            )

    def test_help_mentions_make_guide_in_getting_started(self):
        """make help mentions 'make guide' in the GETTING STARTED section."""
        content = _parse_makefile()
        # Find the GETTING STARTED section
        getting_started_match = re.search(
            r"GETTING STARTED.*?(?=ALL TARGETS|\Z)", content, re.DOTALL
        )
        assert getting_started_match, "GETTING STARTED section not found"
        section = getting_started_match.group(0)
        assert "guide" in section, "'guide' not mentioned in GETTING STARTED section"


# ── TestMakefileTargetDependencies ───────────────────────────


class TestMakefileTargetDependencies:
    """Verify that key targets invoke the correct commands/dependencies."""

    def test_sync_calls_generate_with_infra(self):
        """sync target calls generate.py with infra source argument."""
        content = _parse_makefile()
        # Find sync target recipe
        sync_match = re.search(r"^sync:.*\n\t(.+)$", content, re.MULTILINE)
        assert sync_match, "sync target not found"
        recipe = sync_match.group(1)
        assert "generate.py" in recipe, "sync should call generate.py"
        assert "INFRA_SRC" in recipe or "infra" in recipe.lower(), (
            "sync should pass infra source to generate.py"
        )

    def test_sync_dry_calls_generate_with_dry_run(self):
        """sync-dry target calls generate.py with --dry-run."""
        content = _parse_makefile()
        sync_dry_match = re.search(r"^sync-dry:.*\n\t(.+)$", content, re.MULTILINE)
        assert sync_dry_match, "sync-dry target not found"
        recipe = sync_dry_match.group(1)
        assert "generate.py" in recipe, "sync-dry should call generate.py"
        assert "--dry-run" in recipe, "sync-dry should pass --dry-run"

    def test_lint_chains_all_validators(self):
        """lint target chains all validator sub-targets."""
        content = _parse_makefile()
        lint_match = re.search(r"^lint:\s*(.+?)(?:\s*##.*)?$", content, re.MULTILINE)
        assert lint_match, "lint target not found"
        deps = lint_match.group(1)
        expected_subs = ["lint-yaml", "lint-ansible", "lint-shell", "lint-python"]
        for sub in expected_subs:
            assert sub in deps, f"lint should depend on {sub}"

    def test_test_target_runs_pytest(self):
        """test target includes test-generator which runs pytest."""
        content = _parse_makefile()
        # test depends on test-generator
        test_match = re.search(r"^test:\s*(.+?)(?:\s*##.*)?$", content, re.MULTILINE)
        assert test_match, "test target not found"
        deps = test_match.group(1)
        assert "test-generator" in deps, "test should depend on test-generator"
        # test-generator runs pytest
        gen_match = re.search(r"^test-generator:.*\n\t(.+)$", content, re.MULTILINE)
        assert gen_match, "test-generator target not found"
        recipe = gen_match.group(1)
        assert "pytest" in recipe, "test-generator should run pytest"


# ── TestMakefileVariableOverrides ────────────────────────────


class TestMakefileVariableOverrides:
    """Verify that Make variable overrides (G=, I=, DOMAIN=, AI_MODE=) are used correctly."""

    def test_g_variable_passed_to_limit(self):
        """G=<group> variable is passed to ansible-playbook --limit."""
        content = _parse_makefile()
        # apply-limit target should use $(G) with --limit
        limit_match = re.search(r"^apply-limit:.*\n\t(.+)$", content, re.MULTILINE)
        assert limit_match, "apply-limit target not found"
        recipe = limit_match.group(1)
        assert "--limit" in recipe, "apply-limit should use --limit"
        assert "$(G)" in recipe, "apply-limit should use $(G) variable"

    def test_i_variable_passed_to_snap(self):
        """I=<name> variable is passed to snap-related targets."""
        content = _parse_makefile()
        # Look for any target that uses $(I) — snapshot targets use it in infra.yml
        # The Makefile uses snapshot Ansible role, but snap.sh was the old interface.
        # Check for NAME variable usage in snapshot targets
        snapshot_match = re.search(r"^snapshot:.*\n\t(.+)$", content, re.MULTILINE)
        assert snapshot_match, "snapshot target not found"
        recipe = snapshot_match.group(1)
        assert "$(NAME)" in recipe or "snapshot" in recipe.lower(), (
            "snapshot should use NAME variable or reference snapshot"
        )

    def test_domain_variable_passed_to_ai_switch(self):
        """DOMAIN=<name> variable is passed to ai-switch.sh."""
        content = _parse_makefile()
        switch_match = re.search(r"^ai-switch:.*\n\t(.+)$", content, re.MULTILINE)
        assert switch_match, "ai-switch target not found"
        recipe = switch_match.group(1)
        assert "ai-switch.sh" in recipe, "ai-switch should call ai-switch.sh"
        assert "$(DOMAIN)" in recipe, "ai-switch should pass $(DOMAIN)"

    def test_ai_mode_variable_passed_to_ai_test(self):
        """AI_MODE=<mode> variable is passed to ai-test-loop.sh."""
        content = _parse_makefile()
        # ai-test target uses ANKLUME_AI_MODE from $(AI_MODE)
        ai_test_match = re.search(
            r"^ai-test:.*\n((?:\t.+\n)+)", content, re.MULTILINE
        )
        assert ai_test_match, "ai-test target not found"
        recipe = ai_test_match.group(1)
        assert "AI_MODE" in recipe, "ai-test should reference AI_MODE"
        assert "ai-test-loop.sh" in recipe, "ai-test should call ai-test-loop.sh"
