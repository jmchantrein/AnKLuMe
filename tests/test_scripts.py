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
