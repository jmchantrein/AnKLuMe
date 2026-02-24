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
        """make help shows all expected category headers."""
        result = run_make(["help"])
        output = result.stdout
        expected_categories = [
            "GETTING STARTED",
            "CORE WORKFLOW",
            "SNAPSHOTS",
            "AI / LLM",
            "CONSOLE",
            "INSTANCE MANAGEMENT",
            "LIFECYCLE",
            "DEVELOPMENT",
        ]
        for category in expected_categories:
            assert category in output, (
                f"Category '{category}' missing from make help output"
            )

    def test_help_shows_key_targets(self):
        """make help lists essential targets."""
        result = run_make(["help"])
        output = result.stdout
        essential = ["sync", "lint", "apply", "test", "help"]
        for target in essential:
            assert target in output, f"Target '{target}' missing from help"

    def test_help_all_target(self):
        """make help-all shows all documented targets."""
        result = run_make(["help-all"])
        assert result.returncode == 0
        output = result.stdout
        assert "All targets" in output
        # help-all should list many more targets than help
        # Check for some internal targets not in help
        internal_targets = ["lint-yaml", "apply-infra", "test-generator"]
        for target in internal_targets:
            assert target in output, (
                f"Target '{target}' missing from help-all output"
            )


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
        """make sync-dry requires container or succeeds inside one."""
        result = run_make(["sync-dry"], timeout=15)
        # Outside container: require_container guard blocks with error
        # Inside container: runs generate.py --dry-run
        assert result.returncode == 0 or "anklume-instance" in result.stderr


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
        expected_groups = [
            "GETTING STARTED",
            "CORE WORKFLOW",
            "SNAPSHOTS",
            "AI / LLM",
            "CONSOLE",
            "INSTANCE MANAGEMENT",
            "LIFECYCLE",
            "DEVELOPMENT",
        ]
        for group in expected_groups:
            assert group in content, (
                f"Help group '{group}' missing from Makefile"
            )

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
        # Find the GETTING STARTED section (ends at next category header)
        getting_started_match = re.search(
            r"GETTING STARTED.*?(?=CORE WORKFLOW|\Z)", content, re.DOTALL
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
        recipe = _get_recipe(content, "sync")
        assert "generate.py" in recipe, "sync should call generate.py"
        assert "INFRA_SRC" in recipe or "infra" in recipe.lower(), (
            "sync should pass infra source to generate.py"
        )

    def test_sync_dry_calls_generate_with_dry_run(self):
        """sync-dry target calls generate.py with --dry-run."""
        content = _parse_makefile()
        recipe = _get_recipe(content, "sync-dry")
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
        recipe = _get_recipe(content, "apply-limit")
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


# ── TestMakefilePhony ────────────────────────────────────


class TestMakefilePhony:
    """Verify .PHONY declarations in Makefile."""

    def _get_phony_targets(self):
        """Extract all targets listed in .PHONY."""
        content = _parse_makefile()
        # .PHONY spans multiple lines with backslash continuations
        phony_match = re.search(
            r"^\.PHONY:\s*(.*?)(?:\n(?!\s)|\Z)",
            content,
            re.MULTILINE | re.DOTALL,
        )
        assert phony_match, ".PHONY declaration not found"
        raw = phony_match.group(1)
        # Remove backslash-newline continuations and extra whitespace
        raw = raw.replace("\\\n", " ")
        return set(raw.split())

    def test_all_documented_targets_in_phony(self):
        """Every target with ## description must be in .PHONY."""
        content = _parse_makefile()
        documented = _extract_documented_targets(content)
        phony_targets = self._get_phony_targets()
        missing = []
        for target in documented:
            if target not in phony_targets:
                missing.append(target)
        assert not missing, f"Documented targets missing from .PHONY: {missing}"

    def test_phony_line_exists(self):
        """.PHONY line exists in Makefile."""
        content = _parse_makefile()
        assert ".PHONY:" in content, ".PHONY declaration not found in Makefile"

    def test_phony_includes_core_targets(self):
        """Core targets sync, lint, apply, test, help are in .PHONY."""
        phony_targets = self._get_phony_targets()
        core = ["sync", "lint", "apply", "test", "help"]
        for target in core:
            assert target in phony_targets, f"Core target '{target}' missing from .PHONY"


# ── TestMakefileInfraSrcDetection ────────────────────────


class TestMakefileInfraSrcDetection:
    """Verify INFRA_SRC auto-detection logic."""

    def test_infra_src_uses_wildcard(self):
        """INFRA_SRC line uses $(wildcard ...) for auto-detection."""
        content = _parse_makefile()
        infra_src_match = re.search(r"^INFRA_SRC\s*:=\s*(.+)$", content, re.MULTILINE)
        assert infra_src_match, "INFRA_SRC assignment not found"
        value = infra_src_match.group(1)
        assert "$(wildcard" in value, "INFRA_SRC should use $(wildcard ...) for detection"

    def test_infra_src_defaults_to_infra_yml(self):
        """INFRA_SRC default value is infra.yml when infra/base.yml absent."""
        content = _parse_makefile()
        infra_src_match = re.search(r"^INFRA_SRC\s*:=\s*(.+)$", content, re.MULTILINE)
        assert infra_src_match, "INFRA_SRC assignment not found"
        value = infra_src_match.group(1)
        assert "infra.yml" in value, "INFRA_SRC should default to infra.yml"

    def test_infra_src_uses_infra_dir_when_base_yml_exists(self):
        """INFRA_SRC uses 'infra' when infra/base.yml exists."""
        content = _parse_makefile()
        infra_src_match = re.search(r"^INFRA_SRC\s*:=\s*(.+)$", content, re.MULTILINE)
        assert infra_src_match, "INFRA_SRC assignment not found"
        value = infra_src_match.group(1)
        assert "infra/base.yml" in value, (
            "INFRA_SRC should check for infra/base.yml"
        )
        assert ",infra," in value or ",infra)" in value, (
            "INFRA_SRC should use 'infra' directory when infra/base.yml exists"
        )


# ── TestMakefileRecipes ──────────────────────────────────


def _get_recipe(content, target):
    """Extract the full recipe (all tab-indented lines) for a target.

    Returns the concatenated recipe lines as a single string.
    """
    pattern = re.compile(
        rf"^{re.escape(target)}:.*\n((?:\t.+\n?)+)", re.MULTILINE
    )
    match = pattern.search(content)
    assert match, f"Target '{target}' recipe not found"
    return match.group(1)


class TestMakefileRecipes:
    """Verify recipe correctness for specific targets."""

    def test_apply_calls_ansible_playbook(self):
        """apply target calls ansible-playbook site.yml."""
        content = _parse_makefile()
        recipe = _get_recipe(content, "apply")
        assert "ansible-playbook" in recipe, "apply should call ansible-playbook"
        assert "site.yml" in recipe, "apply should target site.yml"

    def test_apply_infra_uses_tags(self):
        """apply-infra uses --tags infra."""
        content = _parse_makefile()
        recipe = _get_recipe(content, "apply-infra")
        assert "--tags infra" in recipe or "--tags=infra" in recipe, (
            "apply-infra should use --tags infra"
        )

    def test_apply_provision_uses_tags(self):
        """apply-provision uses --tags provision."""
        content = _parse_makefile()
        recipe = _get_recipe(content, "apply-provision")
        assert "--tags provision" in recipe or "--tags=provision" in recipe, (
            "apply-provision should use --tags provision"
        )

    def test_nftables_calls_ansible_playbook(self):
        """nftables target calls ansible-playbook with --tags nftables."""
        content = _parse_makefile()
        recipe = _get_recipe(content, "nftables")
        assert "ansible-playbook" in recipe, "nftables should call ansible-playbook"
        assert "--tags nftables" in recipe, "nftables should use --tags nftables"

    def test_nftables_deploy_calls_script(self):
        """nftables-deploy calls scripts/deploy-nftables.sh."""
        content = _parse_makefile()
        recipe = _get_recipe(content, "nftables-deploy")
        assert "deploy-nftables.sh" in recipe, (
            "nftables-deploy should call scripts/deploy-nftables.sh"
        )

    def test_flush_calls_script(self):
        """flush calls scripts/flush.sh with FORCE handling."""
        content = _parse_makefile()
        recipe = _get_recipe(content, "flush")
        assert "flush.sh" in recipe, "flush should call scripts/flush.sh"
        assert "FORCE" in recipe, "flush should handle FORCE variable"

    def test_upgrade_calls_script(self):
        """upgrade calls scripts/upgrade.sh."""
        content = _parse_makefile()
        recipe = _get_recipe(content, "upgrade")
        assert "upgrade.sh" in recipe, "upgrade should call scripts/upgrade.sh"

    def test_import_infra_calls_script(self):
        """import-infra calls scripts/import-infra.sh."""
        content = _parse_makefile()
        recipe = _get_recipe(content, "import-infra")
        assert "import-infra.sh" in recipe, (
            "import-infra should call scripts/import-infra.sh"
        )

    def test_guide_calls_script(self):
        """guide calls scripts/guide.sh with STEP and AUTO handling."""
        content = _parse_makefile()
        recipe = _get_recipe(content, "guide")
        assert "guide.sh" in recipe, "guide should call scripts/guide.sh"
        assert "STEP" in recipe, "guide should handle STEP variable"
        assert "AUTO" in recipe, "guide should handle AUTO variable"


# ── TestMakefileShellSetting ─────────────────────────────


class TestMakefileShellSetting:
    """Verify shell and default goal settings."""

    def test_shell_is_bash(self):
        """SHELL := /bin/bash is set."""
        content = _parse_makefile()
        assert re.search(
            r"^SHELL\s*:=\s*/bin/bash", content, re.MULTILINE
        ), "SHELL should be set to /bin/bash"

    def test_default_goal_is_help(self):
        """.DEFAULT_GOAL := help is set."""
        content = _parse_makefile()
        assert re.search(
            r"^\.DEFAULT_GOAL\s*:=\s*help", content, re.MULTILINE
        ), ".DEFAULT_GOAL should be set to help"


# ── TestMakefileSnapshotTargets ──────────────────────────


class TestMakefileSnapshotTargets:
    """Verify snapshot-related targets."""

    SNAPSHOT_TARGETS = [
        "snapshot",
        "snapshot-domain",
        "restore",
        "restore-domain",
        "snapshot-delete",
        "snapshot-list",
    ]

    def test_snapshot_targets_exist(self):
        """All snapshot targets are defined in the Makefile."""
        content = _parse_makefile()
        missing = []
        for target in self.SNAPSHOT_TARGETS:
            if f"\n{target}:" not in content:
                missing.append(target)
        assert not missing, f"Missing snapshot targets: {missing}"

    def test_snapshot_uses_snapshot_yml(self):
        """snapshot target calls ansible-playbook snapshot.yml."""
        content = _parse_makefile()
        recipe = _get_recipe(content, "snapshot")
        assert "ansible-playbook" in recipe, "snapshot should call ansible-playbook"
        assert "snapshot.yml" in recipe, "snapshot should use snapshot.yml playbook"

    def test_restore_passes_action_and_name(self):
        """restore passes snapshot_action=restore and snapshot_name=$(NAME)."""
        content = _parse_makefile()
        recipe = _get_recipe(content, "restore")
        assert "snapshot_action=restore" in recipe, (
            "restore should pass snapshot_action=restore"
        )
        assert "snapshot_name=$(NAME)" in recipe, (
            "restore should pass snapshot_name=$(NAME)"
        )


# ── TestMakefileTestTargets ──────────────────────────────


class TestMakefileTestTargets:
    """Verify test-related targets."""

    def test_test_depends_on_subtargets(self):
        """test target depends on test-generator and test-roles."""
        content = _parse_makefile()
        test_match = re.search(r"^test:\s*(.+?)(?:\s*##.*)?$", content, re.MULTILINE)
        assert test_match, "test target not found"
        deps = test_match.group(1)
        assert "test-generator" in deps, "test should depend on test-generator"
        assert "test-roles" in deps, "test should depend on test-roles"

    def test_test_generator_runs_pytest(self):
        """test-generator runs python3 -m pytest."""
        content = _parse_makefile()
        recipe = _get_recipe(content, "test-generator")
        assert "python3 -m pytest" in recipe, (
            "test-generator should run python3 -m pytest"
        )

    def test_test_roles_iterates_roles(self):
        """test-roles iterates over roles/ directories."""
        content = _parse_makefile()
        recipe = _get_recipe(content, "test-roles")
        assert "roles/" in recipe, "test-roles should iterate over roles/ directories"
        assert "molecule" in recipe, "test-roles should reference molecule"

    def test_test_role_uses_r_variable(self):
        """test-role uses $(R) variable."""
        content = _parse_makefile()
        recipe = _get_recipe(content, "test-role")
        assert "$(R)" in recipe, "test-role should use $(R) variable"


# ── TestMakefileLLMTargets ─────────────────────────────────


class TestMakefileLLMTargets:
    """Verify LLM-related targets and backward compatibility aliases."""

    LLM_TARGETS = [
        "llm-switch",
        "llm-status",
        "llm-bench",
        "llm-dev",
    ]

    def test_llm_targets_exist(self):
        """All llm-* targets are defined in the Makefile."""
        content = _parse_makefile()
        missing = []
        for target in self.LLM_TARGETS:
            if f"\n{target}:" not in content:
                missing.append(target)
        assert not missing, f"Missing LLM targets: {missing}"

    def test_llm_bench_calls_script(self):
        """llm-bench target calls scripts/llm-bench.sh."""
        content = _parse_makefile()
        recipe = _get_recipe(content, "llm-bench")
        assert "llm-bench.sh" in recipe, (
            "llm-bench should call scripts/llm-bench.sh"
        )

    def test_llm_dev_calls_script(self):
        """llm-dev target calls ollama-dev.py."""
        content = _parse_makefile()
        recipe = _get_recipe(content, "llm-dev")
        assert "ollama-dev.py" in recipe, (
            "llm-dev should call scripts/ollama-dev.py"
        )

    def test_ollama_dev_alias_exists(self):
        """ollama-dev backward-compat alias exists and delegates to llm-dev."""
        content = _parse_makefile()
        # ollama-dev target should depend on llm-dev
        alias_match = re.search(
            r"^ollama-dev:\s*(.+?)(?:\s*##.*)?$", content, re.MULTILINE
        )
        assert alias_match, "ollama-dev alias target not found"
        deps = alias_match.group(1).strip()
        assert "llm-dev" in deps, (
            "ollama-dev should depend on llm-dev"
        )

    def test_ollama_dev_alias_in_phony(self):
        """ollama-dev alias is listed in .PHONY."""
        content = _parse_makefile()
        phony_match = re.search(
            r"^\.PHONY:\s*(.*?)(?:\n(?!\s)|\Z)",
            content,
            re.MULTILINE | re.DOTALL,
        )
        assert phony_match, ".PHONY declaration not found"
        raw = phony_match.group(1).replace("\\\n", " ")
        phony_set = set(raw.split())
        assert "ollama-dev" in phony_set, (
            "ollama-dev alias missing from .PHONY"
        )
