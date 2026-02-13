"""Tests for Makefile targets — existence, help text, and basic invocations."""

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
