"""Tests for Python utility scripts (matrix-coverage, mine-experiences)."""

import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Add scripts/ to path for importing
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))


# ── matrix-coverage.py ──────────────────────────────────────


class TestMatrixCoverage:
    """Tests for matrix-coverage.py functions."""

    def test_load_matrix(self):
        """load_matrix returns all cells from behavior_matrix.yml."""
        from importlib.util import module_from_spec, spec_from_file_location

        spec = spec_from_file_location(
            "matrix_coverage",
            PROJECT_ROOT / "scripts" / "matrix-coverage.py",
        )
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)

        cells, all_ids = mod.load_matrix()
        assert isinstance(cells, dict)
        assert isinstance(all_ids, set)
        assert len(all_ids) >= 100  # We have 132 cells
        # Check known capability exists
        assert "domain_lifecycle" in cells
        assert "ai_access_policy" in cells
        # Check depth structure
        assert "depth_1" in cells["domain_lifecycle"]
        assert "depth_2" in cells["domain_lifecycle"]
        assert "depth_3" in cells["domain_lifecycle"]

    def test_scan_test_files(self):
        """scan_test_files finds matrix IDs in test files."""
        from importlib.util import module_from_spec, spec_from_file_location

        spec = spec_from_file_location(
            "matrix_coverage",
            PROJECT_ROOT / "scripts" / "matrix-coverage.py",
        )
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)

        covered = mod.scan_test_files()
        assert isinstance(covered, set)
        assert len(covered) >= 100  # We have 100% coverage
        assert "DL-001" in covered
        assert "AA-001" in covered

    def test_coverage_is_100_percent(self):
        """Current coverage should be 100%."""
        result = subprocess.run(
            ["python3", str(PROJECT_ROOT / "scripts" / "matrix-coverage.py")],
            capture_output=True, text=True,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0
        assert "100%" in result.stdout
        # Extract total line
        lines = result.stdout.strip().split("\n")
        total_line = [line for line in lines if "TOTAL" in line]
        assert len(total_line) == 1

    def test_matrix_ids_unique(self):
        """All matrix cell IDs are unique."""
        matrix_path = PROJECT_ROOT / "tests" / "behavior_matrix.yml"
        with open(matrix_path) as f:
            data = yaml.safe_load(f)

        all_ids = []
        for cap in (data.get("capabilities") or {}).values():
            for depth in ("depth_1", "depth_2", "depth_3"):
                for item in cap.get(depth) or []:
                    if "id" in item:
                        all_ids.append(item["id"])
        assert len(all_ids) == len(set(all_ids)), f"Duplicate IDs: {[x for x in all_ids if all_ids.count(x) > 1]}"

    def test_matrix_ids_follow_convention(self):
        """All matrix IDs follow the XX-NNN or XX-D-NNN convention."""
        matrix_path = PROJECT_ROOT / "tests" / "behavior_matrix.yml"
        with open(matrix_path) as f:
            data = yaml.safe_load(f)

        id_pattern = re.compile(r"^[A-Z]{2}-(\d-)?(\d{3})$")
        for cap_key, cap in (data.get("capabilities") or {}).items():
            for depth in ("depth_1", "depth_2", "depth_3"):
                for item in cap.get(depth) or []:
                    cell_id = item.get("id", "")
                    assert id_pattern.match(cell_id), \
                        f"ID '{cell_id}' in {cap_key}/{depth} doesn't match convention XX-NNN or XX-D-NNN"

    def test_matrix_structure_complete(self):
        """Every capability has at least depth_1 entries."""
        matrix_path = PROJECT_ROOT / "tests" / "behavior_matrix.yml"
        with open(matrix_path) as f:
            data = yaml.safe_load(f)

        for cap_key, cap in (data.get("capabilities") or {}).items():
            assert "description" in cap, f"Missing description for {cap_key}"
            d1 = cap.get("depth_1") or []
            assert len(d1) >= 1, f"No depth_1 entries for {cap_key}"
            # Each entry should have required fields
            for item in d1:
                assert "id" in item, f"Missing id in {cap_key}/depth_1"
                assert "action" in item, f"Missing action in {cap_key}/depth_1"
                assert "expected" in item, f"Missing expected in {cap_key}/depth_1"


# ── mine-experiences.py ─────────────────────────────────────


class TestMineExperiences:
    """Tests for mine-experiences.py functions."""

    def _load_module(self):
        """Load mine-experiences.py as a module."""
        from importlib.util import module_from_spec, spec_from_file_location

        spec = spec_from_file_location(
            "mine_experiences",
            PROJECT_ROOT / "scripts" / "mine-experiences.py",
        )
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_fix_patterns_match(self):
        """FIX_PATTERNS regex matches expected commit messages."""
        mod = self._load_module()
        assert mod.FIX_PATTERNS.search("fix: correct nftables template")
        assert mod.FIX_PATTERNS.search("hotfix: urgent CI repair")
        assert mod.FIX_PATTERNS.search("chore: resolve lint warnings")
        assert mod.FIX_PATTERNS.search("bug: workaround for Incus API")
        assert not mod.FIX_PATTERNS.search("feat: add new role")
        assert not mod.FIX_PATTERNS.search("docs: update README")

    def test_categorize_commit_ansible_lint(self):
        """Commits with lint-related files categorize as ansible-lint."""
        mod = self._load_module()
        cat = mod.categorize_commit(
            "fix: ansible-lint violations",
            ["roles/base_system/tasks/main.yml", ".ansible-lint"],
        )
        # Should match ansible-lint or molecule (both are valid)
        assert cat in ("ansible-lint", "molecule")

    def test_categorize_commit_incus(self):
        """Commits with incus files categorize as incus-cli."""
        mod = self._load_module()
        cat = mod.categorize_commit(
            "fix: incus network creation",
            ["roles/incus_networks/tasks/main.yml"],
        )
        assert cat == "incus-cli"

    def test_categorize_commit_generator(self):
        """Commits with generator files categorize as generator."""
        mod = self._load_module()
        cat = mod.categorize_commit(
            "fix: validate orphan detection",
            ["scripts/generate.py"],
        )
        assert cat == "generator"

    def test_get_fix_commits_from_real_history(self):
        """get_fix_commits finds real fix commits in the repo."""
        mod = self._load_module()
        commits = mod.get_fix_commits()
        assert isinstance(commits, list)
        assert len(commits) >= 1  # We have fix commits in the repo
        for commit_hash, message in commits:
            assert len(commit_hash) == 40  # Full SHA
            assert isinstance(message, str)

    def test_extract_experience(self):
        """extract_experience creates a valid entry from a commit."""
        mod = self._load_module()
        commits = mod.get_fix_commits()
        if not commits:
            pytest.skip("No fix commits found")

        entry = mod.extract_experience(commits[0][0], commits[0][1])
        if entry is None:
            pytest.skip("First commit has no files")

        assert "category" in entry
        assert "problem" in entry
        assert "solution" in entry
        assert "source_commit" in entry
        assert "files_affected" in entry
        assert isinstance(entry["files_affected"], list)

    def test_load_existing_ids(self):
        """load_existing_ids reads experience library."""
        mod = self._load_module()
        ids = mod.load_existing_ids()
        assert isinstance(ids, set)
        # We have some experiences already
        assert len(ids) >= 1

    def test_category_map_complete(self):
        """CATEGORY_MAP covers the main categories."""
        mod = self._load_module()
        assert "ansible-lint" in mod.CATEGORY_MAP
        assert "molecule" in mod.CATEGORY_MAP
        assert "incus-cli" in mod.CATEGORY_MAP
        assert "generator" in mod.CATEGORY_MAP


# ── Experience library structure ────────────────────────────


class TestExperienceLibrary:
    """Tests for the experiences/ directory structure and content."""

    def test_experiences_directory_exists(self):
        """experiences/ directory exists with expected structure."""
        exp_dir = PROJECT_ROOT / "experiences"
        assert exp_dir.exists()
        assert (exp_dir / "fixes").exists()
        assert (exp_dir / "patterns").exists()
        assert (exp_dir / "README.md").exists()

    def test_fix_files_valid_yaml(self):
        """All fix YAML files are valid and have required fields."""
        fixes_dir = PROJECT_ROOT / "experiences" / "fixes"
        for yml_file in fixes_dir.glob("*.yml"):
            with open(yml_file) as f:
                data = yaml.safe_load(f)
            assert isinstance(data, list), f"{yml_file.name} should be a list"
            for entry in data:
                assert isinstance(entry, dict), f"Entry in {yml_file.name} should be dict"
                assert "id" in entry, f"Missing id in {yml_file.name}"
                assert "category" in entry, f"Missing category in {yml_file.name}"
                assert "problem" in entry, f"Missing problem in {yml_file.name}"
                assert "solution" in entry, f"Missing solution in {yml_file.name}"

    def test_pattern_files_valid_yaml(self):
        """All pattern YAML files are valid."""
        patterns_dir = PROJECT_ROOT / "experiences" / "patterns"
        for yml_file in patterns_dir.glob("*.yml"):
            with open(yml_file) as f:
                data = yaml.safe_load(f)
            assert data is not None, f"{yml_file.name} is empty"

    def test_fix_ids_unique_across_files(self):
        """All fix IDs are unique across all fix files."""
        fixes_dir = PROJECT_ROOT / "experiences" / "fixes"
        all_ids = []
        for yml_file in fixes_dir.glob("*.yml"):
            with open(yml_file) as f:
                data = yaml.safe_load(f)
            if isinstance(data, list):
                for entry in data:
                    if isinstance(entry, dict) and "id" in entry:
                        all_ids.append(entry["id"])
        assert len(all_ids) == len(set(all_ids)), \
            f"Duplicate IDs: {[x for x in all_ids if all_ids.count(x) > 1]}"


# ── Additional matrix-coverage.py tests ─────────────────────


class TestMatrixCoverageCapabilities:
    """Verify all capabilities are properly defined in the behavior matrix."""

    def _load_matrix_data(self):
        """Load raw behavior matrix YAML data."""
        matrix_path = PROJECT_ROOT / "tests" / "behavior_matrix.yml"
        with open(matrix_path) as f:
            return yaml.safe_load(f)

    def test_all_capabilities_have_description(self):
        """Every capability in the matrix must have a description field."""
        data = self._load_matrix_data()
        capabilities = data.get("capabilities") or {}
        assert len(capabilities) >= 1, "No capabilities found"
        for cap_key, cap in capabilities.items():
            assert "description" in cap, f"Capability '{cap_key}' is missing 'description'"
            assert isinstance(cap["description"], str), \
                f"Capability '{cap_key}' description must be a string"
            assert len(cap["description"]) > 0, \
                f"Capability '{cap_key}' has an empty description"

    def test_expected_capabilities_exist(self):
        """All known capabilities are present in the matrix."""
        data = self._load_matrix_data()
        capabilities = data.get("capabilities") or {}
        expected = [
            "domain_lifecycle",
            "psot_generator",
            "gpu_policy",
            "network_policies",
            "vm_support",
            "privileged_policy",
            "firewall_modes",
            "infra_directory",
            "ephemeral_lifecycle",
            "image_management",
            "ai_access_policy",
        ]
        for cap in expected:
            assert cap in capabilities, f"Expected capability '{cap}' not found in matrix"

    def test_capabilities_have_at_least_depth_1_and_depth_2(self):
        """Every capability has at least depth_1 and depth_2 entries."""
        data = self._load_matrix_data()
        capabilities = data.get("capabilities") or {}
        for cap_key, cap in capabilities.items():
            d1 = cap.get("depth_1") or []
            d2 = cap.get("depth_2") or []
            assert len(d1) >= 1, f"Capability '{cap_key}' has no depth_1 entries"
            assert len(d2) >= 1, f"Capability '{cap_key}' has no depth_2 entries"

    def test_capabilities_have_depth_3(self):
        """Every capability has at least one depth_3 entry."""
        data = self._load_matrix_data()
        capabilities = data.get("capabilities") or {}
        for cap_key, cap in capabilities.items():
            d3 = cap.get("depth_3") or []
            assert len(d3) >= 1, f"Capability '{cap_key}' has no depth_3 entries"


# ── Additional matrix cell structure tests ──────────────────


class TestMatrixCoverageCells:
    """Verify each matrix cell has the required fields."""

    def _load_matrix_data(self):
        """Load raw behavior matrix YAML data."""
        matrix_path = PROJECT_ROOT / "tests" / "behavior_matrix.yml"
        with open(matrix_path) as f:
            return yaml.safe_load(f)

    def test_every_cell_has_required_fields(self):
        """Every cell must have id, action, expected, and deterministic fields."""
        data = self._load_matrix_data()
        capabilities = data.get("capabilities") or {}
        for cap_key, cap in capabilities.items():
            for depth in ("depth_1", "depth_2", "depth_3"):
                for item in cap.get(depth) or []:
                    assert "id" in item, \
                        f"Missing 'id' in {cap_key}/{depth}: {item}"
                    assert "action" in item, \
                        f"Missing 'action' in {cap_key}/{depth} cell {item.get('id', '?')}"
                    assert "expected" in item, \
                        f"Missing 'expected' in {cap_key}/{depth} cell {item.get('id', '?')}"
                    assert "deterministic" in item, \
                        f"Missing 'deterministic' in {cap_key}/{depth} cell {item.get('id', '?')}"

    def test_deterministic_field_is_boolean(self):
        """The deterministic field must be a boolean."""
        data = self._load_matrix_data()
        capabilities = data.get("capabilities") or {}
        for cap_key, cap in capabilities.items():
            for depth in ("depth_1", "depth_2", "depth_3"):
                for item in cap.get(depth) or []:
                    cell_id = item.get("id", "?")
                    assert isinstance(item.get("deterministic"), bool), \
                        f"Cell {cell_id} in {cap_key}/{depth}: 'deterministic' must be boolean"

    def test_action_and_expected_are_non_empty_strings(self):
        """Action and expected fields must be non-empty strings."""
        data = self._load_matrix_data()
        capabilities = data.get("capabilities") or {}
        for _cap_key, cap in capabilities.items():
            for depth in ("depth_1", "depth_2", "depth_3"):
                for item in cap.get(depth) or []:
                    cell_id = item.get("id", "?")
                    action = item.get("action", "")
                    expected = item.get("expected", "")
                    assert isinstance(action, str) and len(action) > 0, \
                        f"Cell {cell_id}: 'action' must be a non-empty string"
                    assert isinstance(expected, str) and len(expected) > 0, \
                        f"Cell {cell_id}: 'expected' must be a non-empty string"

    def test_depth_ids_match_capability_prefix(self):
        """Cell IDs should use a prefix matching their capability."""
        data = self._load_matrix_data()
        capabilities = data.get("capabilities") or {}
        # Map from capability key to known ID prefixes
        prefix_map = {
            "domain_lifecycle": "DL",
            "psot_generator": "PG",
            "gpu_policy": "GP",
            "network_policies": "NP",
            "vm_support": "VM",
            "privileged_policy": "PP",
            "firewall_modes": "FM",
            "infra_directory": "ID",
            "ephemeral_lifecycle": "EL",
            "image_management": "IM",
            "ai_access_policy": "AA",
        }
        for cap_key, cap in capabilities.items():
            expected_prefix = prefix_map.get(cap_key)
            if expected_prefix is None:
                continue  # Unknown capability, skip
            for depth in ("depth_1", "depth_2", "depth_3"):
                for item in cap.get(depth) or []:
                    cell_id = item.get("id", "")
                    assert cell_id.startswith(expected_prefix + "-"), \
                        f"Cell '{cell_id}' in {cap_key}/{depth} should start with '{expected_prefix}-'"

    def test_cell_count_minimum(self):
        """The matrix should have at least 100 cells total."""
        data = self._load_matrix_data()
        capabilities = data.get("capabilities") or {}
        total = 0
        for cap in capabilities.values():
            for depth in ("depth_1", "depth_2", "depth_3"):
                total += len(cap.get(depth) or [])
        assert total >= 100, f"Expected at least 100 cells, found {total}"


# ── Additional mine-experiences.py categorization tests ─────


class TestMineExperiencesCategorization:
    """Additional categorization test cases for mine-experiences.py."""

    def _load_module(self):
        """Load mine-experiences.py as a module."""
        from importlib.util import module_from_spec, spec_from_file_location

        spec = spec_from_file_location(
            "mine_experiences",
            PROJECT_ROOT / "scripts" / "mine-experiences.py",
        )
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_categorize_molecule_files(self):
        """Commits with molecule files categorize as molecule."""
        mod = self._load_module()
        cat = mod.categorize_commit(
            "fix: molecule verify assertion",
            ["roles/base_system/molecule/default/verify.yml"],
        )
        assert cat == "molecule"

    def test_categorize_converge_file(self):
        """Commits with converge.yml categorize as molecule."""
        mod = self._load_module()
        cat = mod.categorize_commit(
            "fix: converge task ordering",
            ["roles/incus_networks/molecule/default/converge.yml"],
        )
        assert cat == "molecule"

    def test_categorize_ci_lint_files(self):
        """Commits affecting CI files with lint context categorize as ansible-lint."""
        mod = self._load_module()
        cat = mod.categorize_commit(
            "fix: lint violations in fqcn usage",
            [".ansible-lint", "roles/base_system/tasks/main.yml"],
        )
        assert cat == "ansible-lint"

    def test_categorize_shell_scripts_generator(self):
        """Commits with generate.py categorize as generator."""
        mod = self._load_module()
        cat = mod.categorize_commit(
            "fix: validate orphan detection edge case",
            ["scripts/generate.py"],
        )
        assert cat == "generator"

    def test_categorize_incus_bridge_files(self):
        """Commits with bridge/network files categorize as incus-cli."""
        mod = self._load_module()
        cat = mod.categorize_commit(
            "fix: bridge creation on missing network",
            ["roles/incus_networks/tasks/main.yml"],
        )
        assert cat == "incus-cli"

    def test_categorize_incus_vm_files(self):
        """Commits with VM-related files categorize as incus-cli."""
        mod = self._load_module()
        cat = mod.categorize_commit(
            "fix: vm startup timeout too short",
            ["roles/incus_instances/tasks/main.yml"],
        )
        assert cat == "incus-cli"

    def test_categorize_incus_profile_files(self):
        """Commits with profile-related files categorize as incus-cli."""
        mod = self._load_module()
        cat = mod.categorize_commit(
            "fix: profile device override issue",
            ["roles/incus_profiles/tasks/main.yml"],
        )
        assert cat == "incus-cli"

    def test_categorize_fallback_to_generator(self):
        """Commits with no matching keywords fall back to generator."""
        mod = self._load_module()
        cat = mod.categorize_commit(
            "fix: typo in readme",
            ["README.md"],
        )
        assert cat == "generator"

    def test_categorize_cleanup_file(self):
        """Commits with cleanup.yml categorize as molecule."""
        mod = self._load_module()
        cat = mod.categorize_commit(
            "fix: cleanup task missing failed_when",
            ["roles/incus_networks/molecule/default/cleanup.yml"],
        )
        assert cat == "molecule"


# ── Additional FIX_PATTERNS regex tests ─────────────────────


class TestMineExperiencesFIXPatterns:
    """Additional FIX_PATTERNS regex matching tests."""

    def _load_module(self):
        """Load mine-experiences.py as a module."""
        from importlib.util import module_from_spec, spec_from_file_location

        spec = spec_from_file_location(
            "mine_experiences",
            PROJECT_ROOT / "scripts" / "mine-experiences.py",
        )
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_workaround_pattern_matches(self):
        """FIX_PATTERNS matches 'workaround' in commit messages."""
        mod = self._load_module()
        assert mod.FIX_PATTERNS.search("workaround for Incus API limitation")
        assert mod.FIX_PATTERNS.search("chore: add workaround for bridge issue")

    def test_noqa_not_matched_directly(self):
        """FIX_PATTERNS does not match 'noqa' alone (it matches in CATEGORY_MAP, not FIX_PATTERNS)."""
        mod = self._load_module()
        # noqa is not in FIX_PATTERNS (fix|lint|resolve|hotfix|workaround|bug)
        assert not mod.FIX_PATTERNS.search("add noqa to suppress warning")

    def test_hotfix_pattern_matches(self):
        """FIX_PATTERNS matches 'hotfix' in commit messages."""
        mod = self._load_module()
        assert mod.FIX_PATTERNS.search("hotfix: emergency repair")
        assert mod.FIX_PATTERNS.search("Apply hotfix for broken deploy")

    def test_resolve_pattern_matches(self):
        """FIX_PATTERNS matches 'resolve' in commit messages."""
        mod = self._load_module()
        assert mod.FIX_PATTERNS.search("resolve: merge conflict in site.yml")
        assert mod.FIX_PATTERNS.search("chore: resolve dependency issue")

    def test_lint_pattern_matches(self):
        """FIX_PATTERNS matches 'lint' in commit messages."""
        mod = self._load_module()
        assert mod.FIX_PATTERNS.search("lint: fix all ansible-lint violations")
        assert mod.FIX_PATTERNS.search("chore: run lint and fix issues")

    def test_bug_pattern_matches(self):
        """FIX_PATTERNS matches 'bug' in commit messages."""
        mod = self._load_module()
        assert mod.FIX_PATTERNS.search("bug: orphan detection false positive")
        assert mod.FIX_PATTERNS.search("fix bug in subnet validation")

    def test_case_insensitive_matching(self):
        """FIX_PATTERNS matches regardless of case."""
        mod = self._load_module()
        assert mod.FIX_PATTERNS.search("FIX: uppercase fix commit")
        assert mod.FIX_PATTERNS.search("Hotfix: capitalized hotfix")
        assert mod.FIX_PATTERNS.search("WORKAROUND: all caps workaround")
        assert mod.FIX_PATTERNS.search("BUG: uppercase bug report")

    def test_non_fix_patterns_do_not_match(self):
        """FIX_PATTERNS does not match non-fix commit messages."""
        mod = self._load_module()
        assert not mod.FIX_PATTERNS.search("feat: add new domain support")
        assert not mod.FIX_PATTERNS.search("docs: update architecture docs")
        assert not mod.FIX_PATTERNS.search("refactor: simplify network logic")
        assert not mod.FIX_PATTERNS.search("chore: update dependencies")
        assert not mod.FIX_PATTERNS.search("style: format yaml files")

    def test_word_boundary_prevents_partial_matches(self):
        """FIX_PATTERNS uses word boundaries to avoid partial matches."""
        mod = self._load_module()
        # 'prefix' contains 'fix' but should not match due to word boundary
        assert not mod.FIX_PATTERNS.search("prefix: some unrelated change")
        # 'suffix' does not contain any pattern word
        assert not mod.FIX_PATTERNS.search("suffix: another change")


# ── Experience library pattern files tests ──────────────────


class TestExperienceLibraryPatterns:
    """Verify patterns/ YAML files have required fields."""

    def test_pattern_files_are_lists(self):
        """All pattern YAML files contain a list of entries."""
        patterns_dir = PROJECT_ROOT / "experiences" / "patterns"
        for yml_file in sorted(patterns_dir.glob("*.yml")):
            with open(yml_file) as f:
                data = yaml.safe_load(f)
            assert isinstance(data, list), \
                f"{yml_file.name} should contain a list, got {type(data).__name__}"

    def test_pattern_entries_have_required_fields(self):
        """Each pattern entry must have id, category, and example fields."""
        patterns_dir = PROJECT_ROOT / "experiences" / "patterns"
        for yml_file in sorted(patterns_dir.glob("*.yml")):
            with open(yml_file) as f:
                data = yaml.safe_load(f)
            if not isinstance(data, list):
                continue
            for entry in data:
                assert "id" in entry, f"Missing 'id' in {yml_file.name}"
                assert "category" in entry, \
                    f"Missing 'category' in {yml_file.name} entry {entry.get('id', '?')}"
                assert "example" in entry, \
                    f"Missing 'example' in {yml_file.name} entry {entry.get('id', '?')}"

    def test_pattern_entries_have_name_and_description(self):
        """Each pattern entry should have name and description fields."""
        patterns_dir = PROJECT_ROOT / "experiences" / "patterns"
        for yml_file in sorted(patterns_dir.glob("*.yml")):
            with open(yml_file) as f:
                data = yaml.safe_load(f)
            if not isinstance(data, list):
                continue
            for entry in data:
                entry_id = entry.get("id", "?")
                assert "name" in entry, \
                    f"Missing 'name' in {yml_file.name} entry {entry_id}"
                assert "description" in entry, \
                    f"Missing 'description' in {yml_file.name} entry {entry_id}"

    def test_pattern_ids_are_unique(self):
        """All pattern IDs are unique across all pattern files."""
        patterns_dir = PROJECT_ROOT / "experiences" / "patterns"
        all_ids = []
        for yml_file in sorted(patterns_dir.glob("*.yml")):
            with open(yml_file) as f:
                data = yaml.safe_load(f)
            if isinstance(data, list):
                for entry in data:
                    if isinstance(entry, dict) and "id" in entry:
                        all_ids.append(entry["id"])
        assert len(all_ids) == len(set(all_ids)), \
            f"Duplicate pattern IDs: {[x for x in all_ids if all_ids.count(x) > 1]}"

    def test_known_pattern_files_exist(self):
        """Expected pattern files exist in patterns/ directory."""
        patterns_dir = PROJECT_ROOT / "experiences" / "patterns"
        expected_files = ["reconciliation.yml", "role-structure.yml", "testing.yml"]
        for filename in expected_files:
            assert (patterns_dir / filename).exists(), \
                f"Expected pattern file '{filename}' not found"


# ── Experience library consistency tests ────────────────────


class TestExperienceLibraryConsistency:
    """Verify IDs follow naming conventions (FIX-XXX-NNN, PAT-XXX-NNN)."""

    def test_fix_ids_follow_convention(self):
        """Fix IDs follow FIX-XXXX-NNN pattern (e.g., FIX-LINT-001, FIX-GEN-001)."""
        fixes_dir = PROJECT_ROOT / "experiences" / "fixes"
        fix_id_pattern = re.compile(r"^FIX-[A-Z]+-\d{3}$")
        for yml_file in sorted(fixes_dir.glob("*.yml")):
            with open(yml_file) as f:
                data = yaml.safe_load(f)
            if not isinstance(data, list):
                continue
            for entry in data:
                if not isinstance(entry, dict):
                    continue
                entry_id = entry.get("id", "")
                assert fix_id_pattern.match(entry_id), \
                    f"Fix ID '{entry_id}' in {yml_file.name} doesn't match FIX-XXX-NNN convention"

    def test_pattern_ids_follow_convention(self):
        """Pattern IDs follow PAT-XXXX-NNN pattern (e.g., PAT-RECON-001, PAT-ROLE-001)."""
        patterns_dir = PROJECT_ROOT / "experiences" / "patterns"
        pat_id_pattern = re.compile(r"^PAT-[A-Z]+-\d{3}$")
        for yml_file in sorted(patterns_dir.glob("*.yml")):
            with open(yml_file) as f:
                data = yaml.safe_load(f)
            if not isinstance(data, list):
                continue
            for entry in data:
                if not isinstance(entry, dict):
                    continue
                entry_id = entry.get("id", "")
                assert pat_id_pattern.match(entry_id), \
                    f"Pattern ID '{entry_id}' in {yml_file.name} doesn't match PAT-XXX-NNN convention"

    def test_fix_categories_match_filenames(self):
        """Fix entries' category field matches the filename they are in."""
        fixes_dir = PROJECT_ROOT / "experiences" / "fixes"
        for yml_file in sorted(fixes_dir.glob("*.yml")):
            expected_category = yml_file.stem  # e.g., 'ansible-lint', 'generator'
            with open(yml_file) as f:
                data = yaml.safe_load(f)
            if not isinstance(data, list):
                continue
            for entry in data:
                if not isinstance(entry, dict):
                    continue
                category = entry.get("category", "")
                assert category == expected_category, \
                    f"Entry {entry.get('id', '?')} in {yml_file.name} has category " \
                    f"'{category}' but expected '{expected_category}'"

    def test_fix_entries_have_source_commit(self):
        """All fix entries have a source_commit field."""
        fixes_dir = PROJECT_ROOT / "experiences" / "fixes"
        for yml_file in sorted(fixes_dir.glob("*.yml")):
            with open(yml_file) as f:
                data = yaml.safe_load(f)
            if not isinstance(data, list):
                continue
            for entry in data:
                if not isinstance(entry, dict):
                    continue
                entry_id = entry.get("id", "?")
                assert "source_commit" in entry, \
                    f"Missing 'source_commit' in {yml_file.name} entry {entry_id}"

    def test_fix_entries_have_files_affected(self):
        """All fix entries have a files_affected field that is a list."""
        fixes_dir = PROJECT_ROOT / "experiences" / "fixes"
        for yml_file in sorted(fixes_dir.glob("*.yml")):
            with open(yml_file) as f:
                data = yaml.safe_load(f)
            if not isinstance(data, list):
                continue
            for entry in data:
                if not isinstance(entry, dict):
                    continue
                entry_id = entry.get("id", "?")
                assert "files_affected" in entry, \
                    f"Missing 'files_affected' in {yml_file.name} entry {entry_id}"
                assert isinstance(entry["files_affected"], list), \
                    f"'files_affected' in {yml_file.name} entry {entry_id} must be a list"

    def test_fix_entries_have_prevention(self):
        """All fix entries have a prevention field."""
        fixes_dir = PROJECT_ROOT / "experiences" / "fixes"
        for yml_file in sorted(fixes_dir.glob("*.yml")):
            with open(yml_file) as f:
                data = yaml.safe_load(f)
            if not isinstance(data, list):
                continue
            for entry in data:
                if not isinstance(entry, dict):
                    continue
                entry_id = entry.get("id", "?")
                assert "prevention" in entry, \
                    f"Missing 'prevention' in {yml_file.name} entry {entry_id}"
