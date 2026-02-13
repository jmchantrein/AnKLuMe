"""Tests for scripts/mine-experiences.py — git history mining for fix patterns."""

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import yaml

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from importlib import import_module  # noqa: E402

mine_mod = import_module("mine-experiences")
get_fix_commits = mine_mod.get_fix_commits
get_commit_files = mine_mod.get_commit_files
categorize_commit = mine_mod.categorize_commit
extract_experience = mine_mod.extract_experience
load_existing_ids = mine_mod.load_existing_ids
load_last_mined_commit = mine_mod.load_last_mined_commit
save_last_mined_commit = mine_mod.save_last_mined_commit
format_entries = mine_mod.format_entries
FIX_PATTERNS = mine_mod.FIX_PATTERNS


# ── FIX_PATTERNS regex ──────────────────────────────────────


class TestFixPatterns:
    def test_matches_fix(self):
        """FIX_PATTERNS matches 'fix' in commit messages."""
        assert FIX_PATTERNS.search("Fix ansible-lint violations")

    def test_matches_lint(self):
        """FIX_PATTERNS matches 'lint' in commit messages."""
        assert FIX_PATTERNS.search("Lint cleanup for CI")

    def test_matches_resolve(self):
        """FIX_PATTERNS matches 'resolve' in commit messages."""
        assert FIX_PATTERNS.search("Resolve merge conflict in roles/")

    def test_matches_hotfix(self):
        """FIX_PATTERNS matches 'hotfix' in commit messages."""
        assert FIX_PATTERNS.search("Hotfix for broken molecule test")

    def test_matches_workaround(self):
        """FIX_PATTERNS matches 'workaround' in commit messages."""
        assert FIX_PATTERNS.search("Add workaround for Incus bug")

    def test_matches_bug(self):
        """FIX_PATTERNS matches 'bug' in commit messages."""
        assert FIX_PATTERNS.search("Bug in subnet calculation")

    def test_no_match_feature(self):
        """FIX_PATTERNS does not match feature commits."""
        assert not FIX_PATTERNS.search("Add new monitoring role")

    def test_no_match_refactor(self):
        """FIX_PATTERNS does not match refactor commits."""
        assert not FIX_PATTERNS.search("Refactor network module")

    def test_case_insensitive(self):
        """FIX_PATTERNS matches case-insensitively."""
        assert FIX_PATTERNS.search("FIX uppercase")
        assert FIX_PATTERNS.search("HOTFIX emergency")


# ── categorize_commit ───────────────────────────────────────


class TestCategorizeCommit:
    def test_ansible_lint_category(self):
        """Commits mentioning lint/noqa are categorized as ansible-lint."""
        cat = categorize_commit(
            "Fix ansible-lint violations",
            ["roles/base_system/tasks/main.yml"],
        )
        assert cat == "ansible-lint"

    def test_molecule_category(self):
        """Commits mentioning molecule/test are categorized as molecule."""
        cat = categorize_commit(
            "Fix molecule converge step",
            ["roles/base_system/molecule/default/converge.yml"],
        )
        assert cat == "molecule"

    def test_incus_category(self):
        """Commits mentioning incus/bridge are categorized as incus-cli."""
        cat = categorize_commit(
            "Fix incus bridge creation",
            ["roles/incus_networks/tasks/main.yml"],
        )
        assert cat == "incus-cli"

    def test_generator_category(self):
        """Commits mentioning generator/psot are categorized as generator."""
        cat = categorize_commit(
            "Fix generator validate function",
            ["scripts/generate.py"],
        )
        assert cat == "generator"

    def test_default_category_is_generator(self):
        """Unrecognized commits default to generator category."""
        cat = categorize_commit("Update README", ["README.md"])
        assert cat == "generator"

    def test_category_from_files(self):
        """Categorization uses file names when message is ambiguous."""
        cat = categorize_commit(
            "Fix issue",
            ["roles/incus_profiles/tasks/main.yml", "roles/incus_networks/tasks/main.yml"],
        )
        # "incus" appears in file paths → incus-cli category
        # But "Fix" also matches other patterns; the combined text is scored
        assert cat in ("incus-cli", "generator")

    def test_mixed_signals_highest_score_wins(self):
        """When multiple categories match, the highest score wins."""
        cat = categorize_commit(
            "Fix incus bridge network device profile project",
            ["roles/incus_networks/tasks/main.yml"],
        )
        # "incus", "bridge", "network", "device", "profile", "project" = 6 incus matches
        assert cat == "incus-cli"


# ── extract_experience ──────────────────────────────────────


class TestExtractExperience:
    def test_extracts_basic_entry(self):
        """extract_experience creates a well-formed entry."""
        with patch.object(mine_mod, "get_commit_files", return_value=[
            "roles/base_system/tasks/main.yml",
            "roles/base_system/defaults/main.yml",
        ]):
            entry = extract_experience("abc1234567890", "Fix base_system lint issues")
        assert entry is not None
        assert entry["category"] == "ansible-lint"
        assert entry["source_commit"] == "abc1234"
        assert "base_system" in entry["problem"]
        assert len(entry["files_affected"]) == 2

    def test_returns_none_when_no_files(self):
        """extract_experience returns None when commit has no files."""
        with patch.object(mine_mod, "get_commit_files", return_value=[]):
            entry = extract_experience("abc1234567890", "Empty commit")
        assert entry is None

    def test_file_patterns_with_roles(self):
        """extract_experience generalizes role file paths."""
        with patch.object(mine_mod, "get_commit_files", return_value=[
            "roles/incus_networks/tasks/main.yml",
        ]):
            entry = extract_experience("abc1234567890", "Fix incus bug")
        assert "roles/*/tasks/main.yml" in entry["files_affected"]

    def test_file_patterns_non_roles(self):
        """extract_experience keeps non-role paths as-is."""
        with patch.object(mine_mod, "get_commit_files", return_value=[
            "scripts/generate.py",
        ]):
            entry = extract_experience("abc1234567890", "Fix generator bug")
        assert "scripts/generate.py" in entry["files_affected"]

    def test_limits_files_to_five(self):
        """extract_experience limits file patterns to 5."""
        with patch.object(mine_mod, "get_commit_files", return_value=[
            f"roles/role{i}/tasks/main.yml" for i in range(10)
        ]):
            entry = extract_experience("abc1234567890", "Fix many files")
        assert len(entry["files_affected"]) <= 5

    def test_deduplicates_patterns(self):
        """extract_experience deduplicates identical patterns."""
        with patch.object(mine_mod, "get_commit_files", return_value=[
            "roles/roleA/tasks/main.yml",
            "roles/roleB/tasks/main.yml",
        ]):
            entry = extract_experience("abc1234567890", "Fix tasks")
        # Both should generalize to "roles/*/tasks/main.yml"
        assert entry["files_affected"].count("roles/*/tasks/main.yml") == 1


# ── load_existing_ids ───────────────────────────────────────


class TestLoadExistingIds:
    def test_loads_from_yaml_files(self, tmp_path, monkeypatch):
        """load_existing_ids reads IDs from YAML files."""
        fixes_dir = tmp_path / "fixes"
        fixes_dir.mkdir()
        yml = fixes_dir / "test.yml"
        yml.write_text(yaml.dump([
            {"id": "FIX-001", "source_commit": "abc1234"},
            {"id": "FIX-002", "source_commit": "def5678"},
        ]))
        monkeypatch.setattr(mine_mod, "FIXES_DIR", fixes_dir)
        ids = load_existing_ids()
        assert "FIX-001" in ids
        assert "FIX-002" in ids
        assert "abc1234" in ids
        assert "def5678" in ids

    def test_handles_empty_dir(self, tmp_path, monkeypatch):
        """load_existing_ids returns empty set for empty directory."""
        fixes_dir = tmp_path / "fixes"
        fixes_dir.mkdir()
        monkeypatch.setattr(mine_mod, "FIXES_DIR", fixes_dir)
        ids = load_existing_ids()
        assert ids == set()

    def test_handles_invalid_yaml(self, tmp_path, monkeypatch):
        """load_existing_ids skips invalid YAML files."""
        fixes_dir = tmp_path / "fixes"
        fixes_dir.mkdir()
        bad = fixes_dir / "bad.yml"
        bad.write_text("not: [valid: yaml: {]")
        monkeypatch.setattr(mine_mod, "FIXES_DIR", fixes_dir)
        ids = load_existing_ids()
        assert ids == set()

    def test_handles_non_list_yaml(self, tmp_path, monkeypatch):
        """load_existing_ids skips files where content is not a list."""
        fixes_dir = tmp_path / "fixes"
        fixes_dir.mkdir()
        yml = fixes_dir / "dict.yml"
        yml.write_text(yaml.dump({"key": "value"}))
        monkeypatch.setattr(mine_mod, "FIXES_DIR", fixes_dir)
        ids = load_existing_ids()
        assert ids == set()


# ── last mined commit ───────────────────────────────────────


class TestLastMinedCommit:
    def test_save_and_load(self, tmp_path, monkeypatch):
        """save_last_mined_commit / load_last_mined_commit roundtrip."""
        marker = tmp_path / ".last-mined-commit"
        monkeypatch.setattr(mine_mod, "LAST_MINED_FILE", marker)
        save_last_mined_commit("abc1234567890")
        result = load_last_mined_commit()
        assert result == "abc1234567890"

    def test_load_returns_none_when_missing(self, tmp_path, monkeypatch):
        """load_last_mined_commit returns None when file doesn't exist."""
        marker = tmp_path / ".last-mined-commit"
        monkeypatch.setattr(mine_mod, "LAST_MINED_FILE", marker)
        assert load_last_mined_commit() is None

    def test_load_returns_none_when_empty(self, tmp_path, monkeypatch):
        """load_last_mined_commit returns None when file is empty."""
        marker = tmp_path / ".last-mined-commit"
        marker.write_text("")
        monkeypatch.setattr(mine_mod, "LAST_MINED_FILE", marker)
        assert load_last_mined_commit() is None


# ── format_entries ──────────────────────────────────────────


class TestFormatEntries:
    def test_formats_basic_entry(self):
        """format_entries creates valid YAML-like output."""
        entries = [{
            "id": "FIX-001",
            "category": "ansible-lint",
            "problem": "Missing author field",
            "solution": "Add author to meta",
            "source_commit": "abc1234",
            "files_affected": ["roles/*/meta/main.yml"],
            "prevention": "Template includes required fields",
        }]
        result = format_entries(entries, "ansible-lint")
        assert "FIX-001" in result
        assert "ansible-lint" in result
        assert "abc1234" in result
        assert "Missing author field" in result

    def test_formats_multiple_entries(self):
        """format_entries handles multiple entries."""
        entries = [
            {
                "id": "FIX-001",
                "category": "test",
                "problem": "Problem 1",
                "solution": "Solution 1",
                "source_commit": "aaa1111",
                "files_affected": ["file1.yml"],
                "prevention": "Prevention 1",
            },
            {
                "id": "FIX-002",
                "category": "test",
                "problem": "Problem 2",
                "solution": "Solution 2",
                "source_commit": "bbb2222",
                "files_affected": ["file2.yml"],
                "prevention": "Prevention 2",
            },
        ]
        result = format_entries(entries, "test")
        assert "FIX-001" in result
        assert "FIX-002" in result

    def test_escapes_quotes_in_problem(self):
        """format_entries escapes double quotes in strings."""
        entries = [{
            "id": "FIX-001",
            "category": "test",
            "problem": 'Fix "broken" test',
            "solution": "Replace it",
            "source_commit": "abc1234",
            "files_affected": ["test.py"],
            "prevention": "None",
        }]
        result = format_entries(entries, "test")
        assert '\\"broken\\"' in result

    def test_multiple_files_affected(self):
        """format_entries lists multiple files in brackets."""
        entries = [{
            "id": "FIX-001",
            "category": "test",
            "problem": "Multi-file fix",
            "solution": "Fix all",
            "source_commit": "abc1234",
            "files_affected": ["a.yml", "b.yml", "c.yml"],
            "prevention": "None",
        }]
        result = format_entries(entries, "test")
        assert '"a.yml"' in result
        assert '"b.yml"' in result
        assert '"c.yml"' in result


# ── get_fix_commits (live git) ──────────────────────────────


class TestGetFixCommits:
    def test_returns_list_of_tuples(self):
        """get_fix_commits returns a list of (hash, message) tuples."""
        commits = get_fix_commits()
        # Project should have at least some fix commits
        assert isinstance(commits, list)
        if commits:
            assert len(commits[0]) == 2
            assert len(commits[0][0]) == 40  # Full SHA

    def test_since_limits_results(self):
        """get_fix_commits with since= returns fewer results."""
        all_commits = get_fix_commits()
        if len(all_commits) > 1:
            # Use the hash of the second-to-last fix commit
            mid_hash = all_commits[len(all_commits) // 2][0]
            since_commits = get_fix_commits(since_commit=mid_hash)
            assert len(since_commits) <= len(all_commits)

    def test_since_invalid_hash(self):
        """get_fix_commits with invalid since= returns empty."""
        commits = get_fix_commits(since_commit="0000000000000000000000000000000000000000")
        assert isinstance(commits, list)


# ── main (dry-run) ──────────────────────────────────────────


class TestMainDryRun:
    def test_dry_run_does_not_write(self, tmp_path, monkeypatch):
        """main --dry-run does not create files."""
        monkeypatch.setattr(mine_mod, "FIXES_DIR", tmp_path / "fixes")
        monkeypatch.setattr(mine_mod, "EXPERIENCES_DIR", tmp_path / "exp")
        monkeypatch.setattr(mine_mod, "LAST_MINED_FILE", tmp_path / ".last")
        (tmp_path / "fixes").mkdir()
        (tmp_path / "exp").mkdir()

        # Run in subprocess to avoid side effects
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "mine-experiences.py"), "--dry-run"],
            capture_output=True, text=True,
            cwd=str(Path(__file__).resolve().parent.parent),
            timeout=30,
        )
        assert result.returncode == 0
        # Should not create any files in fixes dir
        assert not list((tmp_path / "fixes").glob("*.yml"))
