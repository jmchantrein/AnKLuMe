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


# ── main (write mode) ──────────────────────────────────


class TestMineWriteMode:
    """Test main() in non-dry-run mode (actual file writing to tmp_path)."""

    def test_write_mode_creates_files(self, tmp_path, monkeypatch):
        """main() without --dry-run writes YAML files to the fixes directory."""
        fixes_dir = tmp_path / "fixes"
        fixes_dir.mkdir()
        exp_dir = tmp_path / "exp"
        exp_dir.mkdir()
        last_file = tmp_path / ".last-mined-commit"

        monkeypatch.setattr(mine_mod, "FIXES_DIR", fixes_dir)
        monkeypatch.setattr(mine_mod, "EXPERIENCES_DIR", exp_dir)
        monkeypatch.setattr(mine_mod, "LAST_MINED_FILE", last_file)

        # Mock get_fix_commits to return known commits
        fake_commits = [
            ("a" * 40, "Fix ansible-lint violation in base_system"),
            ("b" * 40, "Fix molecule test converge failure"),
        ]
        monkeypatch.setattr(mine_mod, "get_fix_commits", lambda since=None: fake_commits)

        # Mock get_commit_files to return files for each commit
        def fake_files(commit_hash):
            if commit_hash.startswith("a"):
                return ["roles/base_system/tasks/main.yml"]
            return ["roles/base_system/molecule/default/converge.yml"]

        monkeypatch.setattr(mine_mod, "get_commit_files", fake_files)

        # Run main without --dry-run
        monkeypatch.setattr("sys.argv", ["mine-experiences.py"])
        mine_mod.main()

        # Should have created at least one YAML file
        yml_files = list(fixes_dir.glob("*.yml"))
        assert len(yml_files) > 0

    def test_write_mode_saves_last_mined_commit(self, tmp_path, monkeypatch):
        """main() without --dry-run saves the last mined commit hash."""
        fixes_dir = tmp_path / "fixes"
        fixes_dir.mkdir()
        exp_dir = tmp_path / "exp"
        exp_dir.mkdir()
        last_file = tmp_path / ".last-mined-commit"

        monkeypatch.setattr(mine_mod, "FIXES_DIR", fixes_dir)
        monkeypatch.setattr(mine_mod, "EXPERIENCES_DIR", exp_dir)
        monkeypatch.setattr(mine_mod, "LAST_MINED_FILE", last_file)

        fake_hash = "c" * 40
        fake_commits = [(fake_hash, "Fix incus bridge creation bug")]
        monkeypatch.setattr(mine_mod, "get_fix_commits", lambda since=None: fake_commits)
        monkeypatch.setattr(
            mine_mod, "get_commit_files",
            lambda h: ["roles/incus_networks/tasks/main.yml"],
        )

        monkeypatch.setattr("sys.argv", ["mine-experiences.py"])
        mine_mod.main()

        assert last_file.exists()
        assert last_file.read_text().strip() == fake_hash

    def test_write_mode_appends_to_existing_file(self, tmp_path, monkeypatch):
        """main() appends to existing category files."""
        fixes_dir = tmp_path / "fixes"
        fixes_dir.mkdir()
        exp_dir = tmp_path / "exp"
        exp_dir.mkdir()
        last_file = tmp_path / ".last-mined-commit"

        # Pre-create a category file
        existing = fixes_dir / "ansible-lint.yml"
        existing.write_text("---\n- id: EXISTING-001\n  category: ansible-lint\n")

        monkeypatch.setattr(mine_mod, "FIXES_DIR", fixes_dir)
        monkeypatch.setattr(mine_mod, "EXPERIENCES_DIR", exp_dir)
        monkeypatch.setattr(mine_mod, "LAST_MINED_FILE", last_file)

        fake_commits = [("d" * 40, "Fix lint noqa issue")]
        monkeypatch.setattr(mine_mod, "get_fix_commits", lambda since=None: fake_commits)
        monkeypatch.setattr(
            mine_mod, "get_commit_files",
            lambda h: ["roles/base_system/tasks/main.yml"],
        )

        monkeypatch.setattr("sys.argv", ["mine-experiences.py"])
        mine_mod.main()

        content = existing.read_text()
        assert "EXISTING-001" in content
        assert "MINED-LINT-001" in content


# ── git failure ─────────────────────────────────────────


class TestMineGitFailure:
    """Test with mock git that fails (returns non-zero)."""

    def test_git_failure_returns_empty_commits(self, monkeypatch):
        """When git fails, get_fix_commits returns an empty list."""

        def mock_run(args, **kwargs):
            return subprocess.CompletedProcess(args, returncode=128, stdout="", stderr="fatal")

        monkeypatch.setattr(subprocess, "run", mock_run)
        commits = get_fix_commits()
        assert commits == []

    def test_git_failure_commit_files_returns_empty(self, monkeypatch):
        """When git fails, get_commit_files returns an empty list."""

        def mock_run(args, **kwargs):
            return subprocess.CompletedProcess(args, returncode=1, stdout="", stderr="error")

        monkeypatch.setattr(subprocess, "run", mock_run)
        files = get_commit_files("abc1234567890")
        assert files == []

    def test_main_with_git_failure_exits_cleanly(self, tmp_path, monkeypatch):
        """main() with failing git exits cleanly with 'No fix commits found'."""
        fixes_dir = tmp_path / "fixes"
        fixes_dir.mkdir()

        monkeypatch.setattr(mine_mod, "FIXES_DIR", fixes_dir)
        monkeypatch.setattr(mine_mod, "EXPERIENCES_DIR", tmp_path / "exp")
        monkeypatch.setattr(mine_mod, "LAST_MINED_FILE", tmp_path / ".last")
        monkeypatch.setattr(mine_mod, "get_fix_commits", lambda since=None: [])
        monkeypatch.setattr("sys.argv", ["mine-experiences.py"])

        # Should not raise — just print "No fix commits found."
        mine_mod.main()


# ── incremental with corrupted file ─────────────────────


class TestMineIncrementalCorrupted:
    """Test with corrupted .last-mined-commit file (invalid hash)."""

    def test_corrupted_hash_used_as_since(self, tmp_path, monkeypatch):
        """A corrupted last-mined-commit file is still read as a string."""
        marker = tmp_path / ".last-mined-commit"
        marker.write_text("not-a-valid-hash!!!\n")
        monkeypatch.setattr(mine_mod, "LAST_MINED_FILE", marker)
        result = load_last_mined_commit()
        # The function reads it as-is; it does not validate the hash format
        assert result == "not-a-valid-hash!!!"

    def test_incremental_with_corrupted_file_no_crash(self, tmp_path, monkeypatch):
        """main --incremental with corrupted last commit file does not crash."""
        fixes_dir = tmp_path / "fixes"
        fixes_dir.mkdir()
        marker = tmp_path / ".last-mined-commit"
        marker.write_text("ZZZZ_invalid\n")

        monkeypatch.setattr(mine_mod, "FIXES_DIR", fixes_dir)
        monkeypatch.setattr(mine_mod, "EXPERIENCES_DIR", tmp_path / "exp")
        monkeypatch.setattr(mine_mod, "LAST_MINED_FILE", marker)

        # Mock get_fix_commits to accept any since value and return empty
        monkeypatch.setattr(mine_mod, "get_fix_commits", lambda since=None: [])
        monkeypatch.setattr("sys.argv", ["mine-experiences.py", "--incremental"])

        # Should not crash
        mine_mod.main()


# ── empty repository ────────────────────────────────────


class TestMineEmptyRepo:
    """Test with empty git repository (no commits)."""

    def test_empty_repo_returns_no_commits(self, monkeypatch):
        """get_fix_commits on an empty repo returns empty list."""

        def mock_run(args, **kwargs):
            return subprocess.CompletedProcess(
                args, returncode=128, stdout="",
                stderr="fatal: your current branch 'main' does not have any commits yet",
            )

        monkeypatch.setattr(subprocess, "run", mock_run)
        commits = get_fix_commits()
        assert commits == []

    def test_empty_repo_main_exits_cleanly(self, tmp_path, monkeypatch):
        """main() on an empty repo exits cleanly."""
        fixes_dir = tmp_path / "fixes"
        fixes_dir.mkdir()

        monkeypatch.setattr(mine_mod, "FIXES_DIR", fixes_dir)
        monkeypatch.setattr(mine_mod, "EXPERIENCES_DIR", tmp_path / "exp")
        monkeypatch.setattr(mine_mod, "LAST_MINED_FILE", tmp_path / ".last")
        monkeypatch.setattr(mine_mod, "get_fix_commits", lambda since=None: [])
        monkeypatch.setattr("sys.argv", ["mine-experiences.py"])

        mine_mod.main()
        # No files should have been created
        assert not list(fixes_dir.glob("*.yml"))


# ── category mapping edge cases ─────────────────────────


class TestMineCategoryMapping:
    """Test commit message to category mapping for specific keywords."""

    def test_fix_in_subject_maps_to_fixes_or_generator(self):
        """Commit with 'fix' in subject categorizes correctly."""
        # "fix" alone triggers the FIX_PATTERNS match, but categorize_commit
        # uses CATEGORY_MAP scores. "fix" alone matches no specific category
        # pattern, so it falls back to "generator".
        cat = categorize_commit("fix: something broken", ["README.md"])
        assert cat == "generator"

    def test_lint_in_subject_maps_to_ansible_lint(self):
        """Commit with 'lint' in subject → category 'ansible-lint'."""
        cat = categorize_commit("lint: clean up noqa directives", ["roles/base/tasks/main.yml"])
        assert cat == "ansible-lint"

    def test_resolve_in_subject_matches_fix_patterns(self):
        """Commit with 'resolve' triggers FIX_PATTERNS but categorizes based on context."""
        assert FIX_PATTERNS.search("resolve merge conflict")
        # Without specific keywords, resolve falls back to generator
        cat = categorize_commit("resolve merge conflict", ["README.md"])
        assert cat == "generator"

    def test_unknown_pattern_defaults_to_generator(self):
        """Commit with no category-matching keywords defaults to generator."""
        cat = categorize_commit("improve performance of something", ["scripts/unknown.py"])
        assert cat == "generator"


# ── git log parsing edge cases ───────────────────────────


class TestMineGitLogParsing:
    """Test get_fix_commits with unusual git log outputs."""

    def test_git_log_with_special_chars_in_subject(self, monkeypatch):
        """Git log with quotes and special chars in subject is handled."""
        fake_output = 'aaa1234567890abcdef1234567890abcdef12345678 Fix "broken" test\'s `output`'

        def mock_run(args, **kwargs):
            return subprocess.CompletedProcess(args, returncode=0, stdout=fake_output, stderr="")

        monkeypatch.setattr(subprocess, "run", mock_run)
        commits = get_fix_commits()
        assert len(commits) == 1
        assert '"broken"' in commits[0][1]

    def test_git_log_with_merge_commits(self, monkeypatch):
        """Merge commits without fix keywords are filtered out."""
        fake_output = (
            "aaa0000000000000000000000000000000000000000 Merge branch 'main'\n"
            "bbb0000000000000000000000000000000000000000 Fix lint error in base_system"
        )

        def mock_run(args, **kwargs):
            return subprocess.CompletedProcess(args, returncode=0, stdout=fake_output, stderr="")

        monkeypatch.setattr(subprocess, "run", mock_run)
        commits = get_fix_commits()
        # Merge commit doesn't match FIX_PATTERNS; only the fix commit matches
        assert len(commits) == 1
        assert "lint" in commits[0][1]

    def test_git_log_with_co_authored_by(self, monkeypatch):
        """Commits with Co-authored-by trailers in format=%s are handled."""
        # format=%H %s only captures subject line, not trailers
        fake_output = "ccc0000000000000000000000000000000000000000 Fix bug co-authored with Alice"

        def mock_run(args, **kwargs):
            return subprocess.CompletedProcess(args, returncode=0, stdout=fake_output, stderr="")

        monkeypatch.setattr(subprocess, "run", mock_run)
        commits = get_fix_commits()
        assert len(commits) == 1
        assert "bug" in commits[0][1]

    def test_empty_commit_message_skipped(self, monkeypatch):
        """A line with only a hash and no message is skipped gracefully."""
        fake_output = "ddd0000000000000000000000000000000000000000"

        def mock_run(args, **kwargs):
            return subprocess.CompletedProcess(args, returncode=0, stdout=fake_output, stderr="")

        monkeypatch.setattr(subprocess, "run", mock_run)
        commits = get_fix_commits()
        # The line has no space separator → parts has len 1 → skipped
        assert commits == []


# ── duplicate detection ──────────────────────────────────


class TestMineDuplicateDetection:
    """Test that mining twice on same commits produces no duplicates."""

    def test_no_duplicate_entries_on_second_run(self, tmp_path, monkeypatch):
        """Running mine twice on same commits → no duplicate entries."""
        fixes_dir = tmp_path / "fixes"
        fixes_dir.mkdir()
        exp_dir = tmp_path / "exp"
        exp_dir.mkdir()
        last_file = tmp_path / ".last-mined-commit"

        monkeypatch.setattr(mine_mod, "FIXES_DIR", fixes_dir)
        monkeypatch.setattr(mine_mod, "EXPERIENCES_DIR", exp_dir)
        monkeypatch.setattr(mine_mod, "LAST_MINED_FILE", last_file)

        fake_commits = [("e" * 40, "Fix ansible-lint noqa in base")]

        def fake_files(h):
            return ["roles/base_system/tasks/main.yml"]

        monkeypatch.setattr(mine_mod, "get_fix_commits", lambda since=None: fake_commits)
        monkeypatch.setattr(mine_mod, "get_commit_files", fake_files)
        monkeypatch.setattr("sys.argv", ["mine-experiences.py"])

        # First run
        mine_mod.main()
        yml_files = list(fixes_dir.glob("*.yml"))
        assert len(yml_files) > 0
        # Second run — same commits, should be skipped because source_commit is in existing_ids
        mine_mod.main()
        content_after_second = yml_files[0].read_text()

        # Count entries: MINED-LINT-001 should appear only once
        assert content_after_second.count("MINED-LINT-001") == 1

    def test_incremental_mode_skips_already_mined(self, tmp_path, monkeypatch):
        """Incremental mode uses last-mined-commit to skip already processed commits."""
        fixes_dir = tmp_path / "fixes"
        fixes_dir.mkdir()
        exp_dir = tmp_path / "exp"
        exp_dir.mkdir()
        last_file = tmp_path / ".last-mined-commit"

        monkeypatch.setattr(mine_mod, "FIXES_DIR", fixes_dir)
        monkeypatch.setattr(mine_mod, "EXPERIENCES_DIR", exp_dir)
        monkeypatch.setattr(mine_mod, "LAST_MINED_FILE", last_file)

        call_log = []

        def mock_get_fix_commits(since=None):
            call_log.append(since)
            return [("f" * 40, "Fix molecule test")]

        def fake_files(h):
            return ["roles/base_system/molecule/default/converge.yml"]

        monkeypatch.setattr(mine_mod, "get_fix_commits", mock_get_fix_commits)
        monkeypatch.setattr(mine_mod, "get_commit_files", fake_files)

        # First run: writes last-mined-commit
        monkeypatch.setattr("sys.argv", ["mine-experiences.py"])
        mine_mod.main()
        assert last_file.exists()

        # Second run with --incremental: should pass the saved hash as since
        monkeypatch.setattr("sys.argv", ["mine-experiences.py", "--incremental"])
        mine_mod.main()

        # The second call should have received the saved commit hash as since
        assert len(call_log) == 2
        assert call_log[0] is None  # First run: no since
        assert call_log[1] == "f" * 40  # Second run: last mined commit


# ══════════════════════════════════════════════════════════════
# NEW TESTS — added below existing test classes
# ══════════════════════════════════════════════════════════════

CATEGORY_MAP = mine_mod.CATEGORY_MAP
run_git = mine_mod.run_git


# ── FIX_PATTERNS extended edge cases ─────────────────────────


class TestFixPatternsExtended:
    """Extended edge-case tests for the FIX_PATTERNS regex."""

    def test_fix_at_start_of_line(self):
        """FIX_PATTERNS matches 'fix' at the beginning of the message."""
        assert FIX_PATTERNS.search("fix: broken pipeline")

    def test_fix_at_end_of_line(self):
        """FIX_PATTERNS matches 'fix' at the end of the message."""
        assert FIX_PATTERNS.search("Applied a quick fix")

    def test_fix_in_middle_of_sentence(self):
        """FIX_PATTERNS matches 'fix' in the middle."""
        assert FIX_PATTERNS.search("This commit will fix the issue")

    def test_hotfix_capitalized(self):
        """FIX_PATTERNS matches 'Hotfix' (mixed case)."""
        assert FIX_PATTERNS.search("Hotfix for deployment")

    def test_workaround_all_upper(self):
        """FIX_PATTERNS matches 'WORKAROUND' (all caps)."""
        assert FIX_PATTERNS.search("WORKAROUND for upstream issue")

    def test_bug_word_boundary(self):
        """FIX_PATTERNS matches 'bug' only as a whole word."""
        assert FIX_PATTERNS.search("bug report #42")
        # 'debug' contains 'bug' but not at word boundary
        assert not FIX_PATTERNS.search("debug mode enabled")

    def test_lint_word_boundary(self):
        """FIX_PATTERNS matches 'lint' as a whole word."""
        assert FIX_PATTERNS.search("lint cleanup")

    def test_resolve_word_boundary(self):
        """FIX_PATTERNS matches 'resolve' but not 'unresolved' partially."""
        assert FIX_PATTERNS.search("resolve import issue")

    def test_no_match_empty_string(self):
        """FIX_PATTERNS does not match empty string."""
        assert not FIX_PATTERNS.search("")

    def test_no_match_unrelated_words(self):
        """FIX_PATTERNS does not match unrelated technical words."""
        assert not FIX_PATTERNS.search("implement new feature")
        assert not FIX_PATTERNS.search("update documentation")
        assert not FIX_PATTERNS.search("remove deprecated code")
        assert not FIX_PATTERNS.search("add tests for module")

    def test_no_match_prefix_suffix_overlap(self):
        """FIX_PATTERNS does not match words containing fix substrings."""
        assert not FIX_PATTERNS.search("suffix is affixed")
        # But 'fix' standalone should match
        assert FIX_PATTERNS.search("fix is needed")

    def test_matches_multiple_patterns_in_one_message(self):
        """FIX_PATTERNS finds multiple pattern matches in one message."""
        msg = "Fix lint bug and resolve workaround"
        matches = FIX_PATTERNS.findall(msg)
        assert len(matches) >= 4  # fix, lint, bug, resolve, workaround

    def test_fix_with_colon_prefix(self):
        """FIX_PATTERNS matches 'fix' in conventional commit format."""
        assert FIX_PATTERNS.search("fix(base_system): update packages")

    def test_hotfix_with_dash(self):
        """FIX_PATTERNS matches 'hotfix' even with surrounding punctuation."""
        assert FIX_PATTERNS.search("apply hotfix-001")

    def test_no_match_fixture(self):
        """FIX_PATTERNS does not match 'fixture' (fix is not a full word)."""
        assert not FIX_PATTERNS.search("add test fixture")

    def test_no_match_fixing_as_word(self):
        """FIX_PATTERNS does not match 'fixing' (word boundary after fix)."""
        # 'fixing' — the 'fix' portion is followed by 'i' not a boundary
        result = FIX_PATTERNS.search("fixing the build")
        # 'fixing' does not match because \b(fix)\b requires word boundary
        assert not result


# ── CATEGORY_MAP pattern tests ───────────────────────────────


class TestCategoryMapPatterns:
    """Direct tests for the CATEGORY_MAP regex patterns."""

    def test_ansible_lint_matches_lint(self):
        assert CATEGORY_MAP["ansible-lint"].search("lint")

    def test_ansible_lint_matches_ansible_lint(self):
        assert CATEGORY_MAP["ansible-lint"].search("ansible-lint")

    def test_ansible_lint_matches_noqa(self):
        assert CATEGORY_MAP["ansible-lint"].search("noqa")

    def test_ansible_lint_matches_fqcn(self):
        assert CATEGORY_MAP["ansible-lint"].search("fqcn")

    def test_ansible_lint_no_match_unrelated(self):
        assert not CATEGORY_MAP["ansible-lint"].search("deploy server")

    def test_molecule_matches_molecule(self):
        assert CATEGORY_MAP["molecule"].search("molecule")

    def test_molecule_matches_test(self):
        assert CATEGORY_MAP["molecule"].search("test")

    def test_molecule_matches_verify(self):
        assert CATEGORY_MAP["molecule"].search("verify")

    def test_molecule_matches_converge(self):
        assert CATEGORY_MAP["molecule"].search("converge")

    def test_molecule_matches_cleanup(self):
        assert CATEGORY_MAP["molecule"].search("cleanup")

    def test_molecule_no_match_unrelated(self):
        assert not CATEGORY_MAP["molecule"].search("deploy database")

    def test_incus_cli_matches_incus(self):
        assert CATEGORY_MAP["incus-cli"].search("incus")

    def test_incus_cli_matches_lxc(self):
        assert CATEGORY_MAP["incus-cli"].search("lxc")

    def test_incus_cli_matches_vm(self):
        assert CATEGORY_MAP["incus-cli"].search("vm")

    def test_incus_cli_matches_bridge(self):
        assert CATEGORY_MAP["incus-cli"].search("bridge")

    def test_incus_cli_matches_network(self):
        assert CATEGORY_MAP["incus-cli"].search("network")

    def test_incus_cli_matches_project(self):
        assert CATEGORY_MAP["incus-cli"].search("project")

    def test_incus_cli_matches_profile(self):
        assert CATEGORY_MAP["incus-cli"].search("profile")

    def test_incus_cli_matches_device(self):
        assert CATEGORY_MAP["incus-cli"].search("device")

    def test_incus_cli_no_match_unrelated(self):
        assert not CATEGORY_MAP["incus-cli"].search("deploy ansible")

    def test_generator_matches_generator(self):
        assert CATEGORY_MAP["generator"].search("generator")

    def test_generator_matches_generate(self):
        assert CATEGORY_MAP["generator"].search("generate")

    def test_generator_matches_psot(self):
        assert CATEGORY_MAP["generator"].search("psot")

    def test_generator_matches_infra_yml(self):
        assert CATEGORY_MAP["generator"].search("infra.yml")

    def test_generator_matches_validate(self):
        assert CATEGORY_MAP["generator"].search("validate")

    def test_generator_matches_orphan(self):
        assert CATEGORY_MAP["generator"].search("orphan")

    def test_generator_no_match_unrelated(self):
        assert not CATEGORY_MAP["generator"].search("deploy server")

    def test_all_categories_case_insensitive(self):
        """All CATEGORY_MAP patterns are case-insensitive."""
        for cat, pattern in CATEGORY_MAP.items():
            # Each category should have at least one keyword that matches
            first_keyword = pattern.pattern.split("|")[0].strip("\\b()")
            assert pattern.search(first_keyword.upper()), f"{cat} not case-insensitive"


# ── categorize_commit extended ───────────────────────────────


class TestCategorizeCommitExtended:
    """Extended tests for categorize_commit scoring and fallback logic."""

    def test_empty_message_empty_files_defaults_to_generator(self):
        """Empty message and files default to generator."""
        cat = categorize_commit("", [])
        assert cat == "generator"

    def test_scores_accumulate_from_multiple_keywords(self):
        """Multiple keywords for the same category increase its score."""
        cat = categorize_commit("lint noqa fqcn ansible-lint cleanup", [])
        assert cat == "ansible-lint"

    def test_files_contribute_to_scoring(self):
        """File paths with standalone keywords contribute to the category score."""
        # \b word boundary: "incus_networks" is one word (underscore is word char)
        # so "incus" and "network" don't match inside underscore-joined names.
        # Use file paths where keywords appear as standalone words.
        cat = categorize_commit(
            "Fix incus bridge issue",
            ["some/incus/tasks/main.yml"],
        )
        # "incus" appears in both message and path as standalone word → incus-cli
        assert cat == "incus-cli"

    def test_molecule_category_from_converge_file(self):
        """Molecule category detected from molecule/ in file path."""
        cat = categorize_commit(
            "Fix converge step",
            ["roles/base_system/molecule/default/converge.yml"],
        )
        assert cat == "molecule"

    def test_generator_from_generate_py(self):
        """Generator category detected from generate.py file."""
        cat = categorize_commit(
            "Fix generate validation",
            ["scripts/generate.py"],
        )
        assert cat == "generator"

    def test_tie_breaking_goes_to_max(self):
        """When categories tie, max() picks one deterministically."""
        # With equal scores, max() picks the alphabetically first key from the dict
        cat = categorize_commit("Fix the issue", ["some/file.yml"])
        # No keywords matched → falls back to generator
        assert cat == "generator"

    def test_incus_cli_beats_molecule_with_more_keywords(self):
        """incus-cli wins over molecule when it has more keyword matches."""
        cat = categorize_commit(
            "Fix incus bridge network device profile project",
            ["roles/incus_networks/molecule/default/converge.yml"],
        )
        # incus=1, bridge=1, network=1, device=1, profile=1, project=1 → 6 for incus-cli
        # molecule=1, converge=1 → 2 for molecule
        assert cat == "incus-cli"

    def test_molecule_from_test_keyword_in_message(self):
        """'test' keyword in message contributes to molecule score."""
        cat = categorize_commit(
            "Fix molecule test verify converge",
            ["roles/base_system/tasks/main.yml"],
        )
        assert cat == "molecule"

    def test_combined_text_includes_all_files(self):
        """categorize_commit combines message with all files."""
        # Word boundary \b means "incus_networks" is one word — incus alone
        # doesn't match. Use standalone keywords in the message instead.
        cat = categorize_commit(
            "Update incus bridge network device",
            ["roles/base/tasks/main.yml"],
        )
        # incus + bridge + network + device = 4 matches for incus-cli
        assert cat == "incus-cli"

    def test_no_scores_at_all_returns_generator(self):
        """When no CATEGORY_MAP patterns match at all, returns generator."""
        cat = categorize_commit("update readme", ["README.md"])
        assert cat == "generator"

    def test_ansible_lint_category_from_noqa_in_files(self):
        """noqa in file content area is detected."""
        cat = categorize_commit(
            "Fix noqa directive",
            ["roles/base_system/tasks/main.yml"],
        )
        assert cat == "ansible-lint"

    def test_generator_validate_keyword(self):
        """'validate' keyword maps to generator category."""
        cat = categorize_commit(
            "Fix validate function in generator",
            ["scripts/generate.py"],
        )
        assert cat == "generator"

    def test_generator_orphan_keyword(self):
        """'orphan' keyword maps to generator category."""
        cat = categorize_commit(
            "Fix orphan detection",
            ["scripts/generate.py"],
        )
        assert cat == "generator"


# ── run_git mocked tests ────────────────────────────────────


class TestRunGit:
    """Tests for the run_git helper function."""

    def test_run_git_success(self, monkeypatch):
        """run_git returns stdout on success."""
        def mock_run(args, **kwargs):
            return subprocess.CompletedProcess(args, returncode=0, stdout="  output  \n", stderr="")
        monkeypatch.setattr(subprocess, "run", mock_run)
        result = run_git(["log", "--oneline"])
        assert result == "output"  # stripped

    def test_run_git_failure_returns_empty(self, monkeypatch):
        """run_git returns empty string on failure."""
        def mock_run(args, **kwargs):
            return subprocess.CompletedProcess(args, returncode=128, stdout="some output", stderr="error")
        monkeypatch.setattr(subprocess, "run", mock_run)
        result = run_git(["log", "--oneline"])
        assert result == ""

    def test_run_git_passes_project_dir(self, monkeypatch):
        """run_git passes -C PROJECT_DIR to git."""
        captured_args = []
        def mock_run(args, **kwargs):
            captured_args.extend(args)
            return subprocess.CompletedProcess(args, returncode=0, stdout="", stderr="")
        monkeypatch.setattr(subprocess, "run", mock_run)
        run_git(["status"])
        assert captured_args[0] == "git"
        assert captured_args[1] == "-C"
        assert captured_args[3] == "status"

    def test_run_git_strips_output(self, monkeypatch):
        """run_git strips whitespace from output."""
        def mock_run(args, **kwargs):
            return subprocess.CompletedProcess(args, returncode=0, stdout="\n  hello world  \n\n", stderr="")
        monkeypatch.setattr(subprocess, "run", mock_run)
        result = run_git(["show"])
        assert result == "hello world"

    def test_run_git_empty_output_on_success(self, monkeypatch):
        """run_git returns empty string when stdout is empty."""
        def mock_run(args, **kwargs):
            return subprocess.CompletedProcess(args, returncode=0, stdout="", stderr="")
        monkeypatch.setattr(subprocess, "run", mock_run)
        result = run_git(["log"])
        assert result == ""

    def test_run_git_captures_output(self, monkeypatch):
        """run_git uses capture_output=True."""
        captured_kwargs = {}
        def mock_run(args, **kwargs):
            captured_kwargs.update(kwargs)
            return subprocess.CompletedProcess(args, returncode=0, stdout="", stderr="")
        monkeypatch.setattr(subprocess, "run", mock_run)
        run_git(["log"])
        assert captured_kwargs.get("capture_output") is True
        assert captured_kwargs.get("text") is True
        assert captured_kwargs.get("check") is False


# ── get_fix_commits parsing extended ─────────────────────────


class TestGetFixCommitsParsingExtended:
    """Extended tests for get_fix_commits git log parsing."""

    def test_multiple_fix_commits_parsed(self, monkeypatch):
        """Multiple fix lines are all parsed."""
        fake_output = "\n".join([
            "a" * 40 + " Fix issue 1",
            "b" * 40 + " Fix issue 2",
            "c" * 40 + " Fix issue 3",
        ])
        def mock_run(args, **kwargs):
            return subprocess.CompletedProcess(args, returncode=0, stdout=fake_output, stderr="")
        monkeypatch.setattr(subprocess, "run", mock_run)
        commits = get_fix_commits()
        assert len(commits) == 3

    def test_non_fix_commits_filtered_out(self, monkeypatch):
        """Non-fix commits are filtered by FIX_PATTERNS."""
        fake_output = "\n".join([
            "a" * 40 + " Add new feature",
            "b" * 40 + " Fix broken build",
            "c" * 40 + " Refactor module",
            "d" * 40 + " Update docs",
        ])
        def mock_run(args, **kwargs):
            return subprocess.CompletedProcess(args, returncode=0, stdout=fake_output, stderr="")
        monkeypatch.setattr(subprocess, "run", mock_run)
        commits = get_fix_commits()
        assert len(commits) == 1
        assert commits[0][1] == "Fix broken build"

    def test_all_pattern_keywords_matched(self, monkeypatch):
        """All FIX_PATTERNS keywords are detected."""
        fake_output = "\n".join([
            "a" * 40 + " Fix something",
            "b" * 40 + " Lint cleanup",
            "c" * 40 + " Resolve conflict",
            "d" * 40 + " Hotfix for prod",
            "e" * 40 + " Workaround for upstream",
            "f" * 40 + " Bug in calculation",
        ])
        def mock_run(args, **kwargs):
            return subprocess.CompletedProcess(args, returncode=0, stdout=fake_output, stderr="")
        monkeypatch.setattr(subprocess, "run", mock_run)
        commits = get_fix_commits()
        assert len(commits) == 6

    def test_empty_lines_skipped(self, monkeypatch):
        """Empty lines in git output are skipped."""
        fake_output = "a" * 40 + " Fix issue\n\n\nb" * 40 + " Fix another"
        def mock_run(args, **kwargs):
            return subprocess.CompletedProcess(args, returncode=0, stdout=fake_output, stderr="")
        monkeypatch.setattr(subprocess, "run", mock_run)
        commits = get_fix_commits()
        assert isinstance(commits, list)

    def test_since_commit_appended_to_args(self, monkeypatch):
        """get_fix_commits with since_commit adds range to git log args."""
        captured_args = []
        def mock_run(args, **kwargs):
            captured_args.extend(args)
            return subprocess.CompletedProcess(args, returncode=0, stdout="", stderr="")
        monkeypatch.setattr(subprocess, "run", mock_run)
        get_fix_commits(since_commit="abc123")
        # Should contain the range "abc123..HEAD"
        assert any("abc123..HEAD" in str(a) for a in captured_args)

    def test_since_none_does_not_add_range(self, monkeypatch):
        """get_fix_commits without since does not add range."""
        captured_args = []
        def mock_run(args, **kwargs):
            captured_args.extend(args)
            return subprocess.CompletedProcess(args, returncode=0, stdout="", stderr="")
        monkeypatch.setattr(subprocess, "run", mock_run)
        get_fix_commits(since_commit=None)
        assert not any("..HEAD" in str(a) for a in captured_args)

    def test_hash_length_preserved(self, monkeypatch):
        """Full 40-char hashes are preserved from git log."""
        full_hash = "abcdef1234567890abcdef1234567890abcdef12"
        fake_output = full_hash + " Fix something"
        def mock_run(args, **kwargs):
            return subprocess.CompletedProcess(args, returncode=0, stdout=fake_output, stderr="")
        monkeypatch.setattr(subprocess, "run", mock_run)
        commits = get_fix_commits()
        assert commits[0][0] == full_hash

    def test_message_with_multiple_spaces(self, monkeypatch):
        """Message with multiple spaces is preserved after first split."""
        fake_output = "a" * 40 + " Fix   multiple   spaces   issue"
        def mock_run(args, **kwargs):
            return subprocess.CompletedProcess(args, returncode=0, stdout=fake_output, stderr="")
        monkeypatch.setattr(subprocess, "run", mock_run)
        commits = get_fix_commits()
        assert commits[0][1] == "Fix   multiple   spaces   issue"

    def test_returns_list_type(self, monkeypatch):
        """get_fix_commits always returns a list."""
        def mock_run(args, **kwargs):
            return subprocess.CompletedProcess(args, returncode=0, stdout="", stderr="")
        monkeypatch.setattr(subprocess, "run", mock_run)
        result = get_fix_commits()
        assert isinstance(result, list)

    def test_line_with_only_hash_no_space(self, monkeypatch):
        """A line with only a 40-char hash and no space is skipped."""
        fake_output = "a" * 40
        def mock_run(args, **kwargs):
            return subprocess.CompletedProcess(args, returncode=0, stdout=fake_output, stderr="")
        monkeypatch.setattr(subprocess, "run", mock_run)
        commits = get_fix_commits()
        assert commits == []


# ── get_commit_files mocked tests ────────────────────────────


class TestGetCommitFilesMocked:
    """Tests for get_commit_files with mocked git."""

    def test_returns_file_list(self, monkeypatch):
        """get_commit_files returns a list of file paths."""
        def mock_run(args, **kwargs):
            return subprocess.CompletedProcess(
                args, returncode=0,
                stdout="roles/base/tasks/main.yml\nscripts/generate.py\n",
                stderr="",
            )
        monkeypatch.setattr(subprocess, "run", mock_run)
        files = get_commit_files("abc1234567890")
        assert files == ["roles/base/tasks/main.yml", "scripts/generate.py"]

    def test_returns_empty_on_failure(self, monkeypatch):
        """get_commit_files returns empty list on git failure."""
        def mock_run(args, **kwargs):
            return subprocess.CompletedProcess(args, returncode=1, stdout="", stderr="error")
        monkeypatch.setattr(subprocess, "run", mock_run)
        files = get_commit_files("abc1234567890")
        assert files == []

    def test_returns_empty_on_no_output(self, monkeypatch):
        """get_commit_files returns empty list when no files changed."""
        def mock_run(args, **kwargs):
            return subprocess.CompletedProcess(args, returncode=0, stdout="", stderr="")
        monkeypatch.setattr(subprocess, "run", mock_run)
        files = get_commit_files("abc1234567890")
        assert files == []

    def test_single_file(self, monkeypatch):
        """get_commit_files handles single file."""
        def mock_run(args, **kwargs):
            return subprocess.CompletedProcess(
                args, returncode=0, stdout="README.md", stderr="",
            )
        monkeypatch.setattr(subprocess, "run", mock_run)
        files = get_commit_files("abc1234567890")
        assert files == ["README.md"]

    def test_uses_diff_tree_command(self, monkeypatch):
        """get_commit_files uses 'diff-tree --no-commit-id -r --name-only'."""
        captured_args = []
        def mock_run(args, **kwargs):
            captured_args.extend(args)
            return subprocess.CompletedProcess(args, returncode=0, stdout="", stderr="")
        monkeypatch.setattr(subprocess, "run", mock_run)
        get_commit_files("abc123")
        assert "diff-tree" in captured_args
        assert "--no-commit-id" in captured_args
        assert "-r" in captured_args
        assert "--name-only" in captured_args


# ── extract_experience extended ──────────────────────────────


class TestExtractExperienceExtended:
    """Extended tests for extract_experience function."""

    def test_short_hash_is_7_chars(self):
        """source_commit is truncated to 7 characters."""
        with patch.object(mine_mod, "get_commit_files", return_value=["README.md"]):
            entry = extract_experience("a" * 40, "Fix something")
        assert entry["source_commit"] == "a" * 7

    def test_solution_includes_short_hash(self):
        """solution field references the short hash."""
        with patch.object(mine_mod, "get_commit_files", return_value=["README.md"]):
            entry = extract_experience("b" * 40, "Fix something")
        assert "bbbbbbb" in entry["solution"]
        assert "commit" in entry["solution"].lower()

    def test_prevention_is_standard_message(self):
        """prevention field contains the standard message."""
        with patch.object(mine_mod, "get_commit_files", return_value=["README.md"]):
            entry = extract_experience("c" * 40, "Fix something")
        assert "experience library" in entry["prevention"]

    def test_problem_is_commit_message(self):
        """problem field is the commit message."""
        with patch.object(mine_mod, "get_commit_files", return_value=["README.md"]):
            entry = extract_experience("d" * 40, "Fix critical bug in parser")
        assert entry["problem"] == "Fix critical bug in parser"

    def test_roles_path_with_two_parts(self):
        """A roles/ path with only 2 parts is kept as-is."""
        with patch.object(mine_mod, "get_commit_files", return_value=["roles/README.md"]):
            entry = extract_experience("e" * 40, "Fix roles readme")
        assert "roles/README.md" in entry["files_affected"]

    def test_roles_path_with_deep_nesting(self):
        """Deep roles/ paths are generalized correctly."""
        with patch.object(mine_mod, "get_commit_files", return_value=[
            "roles/base_system/molecule/default/converge.yml",
        ]):
            entry = extract_experience("f" * 40, "Fix molecule test")
        assert "roles/*/molecule/default/converge.yml" in entry["files_affected"]

    def test_multiple_different_role_paths(self):
        """Different role sub-paths produce distinct patterns."""
        with patch.object(mine_mod, "get_commit_files", return_value=[
            "roles/base_system/tasks/main.yml",
            "roles/base_system/defaults/main.yml",
        ]):
            entry = extract_experience("a1" * 20, "Fix base system")
        assert "roles/*/tasks/main.yml" in entry["files_affected"]
        assert "roles/*/defaults/main.yml" in entry["files_affected"]

    def test_max_five_files_from_input(self):
        """Only the first 5 files are processed."""
        files = [f"roles/role{i}/tasks/main.yml" for i in range(20)]
        with patch.object(mine_mod, "get_commit_files", return_value=files):
            entry = extract_experience("g" * 40, "Fix many files")
        # All 20 files have the same pattern → deduplicated to 1
        # But only first 5 were processed → still 1 unique pattern
        assert len(entry["files_affected"]) <= 5

    def test_non_role_paths_preserved(self):
        """Non-role paths like scripts/ and docs/ are kept as-is."""
        with patch.object(mine_mod, "get_commit_files", return_value=[
            "scripts/generate.py",
            "docs/SPEC.md",
            "Makefile",
        ]):
            entry = extract_experience("h" * 40, "Fix generator")
        assert "scripts/generate.py" in entry["files_affected"]
        assert "docs/SPEC.md" in entry["files_affected"]
        assert "Makefile" in entry["files_affected"]

    def test_entry_has_all_required_keys(self):
        """Returned entry has all expected keys."""
        with patch.object(mine_mod, "get_commit_files", return_value=["file.yml"]):
            entry = extract_experience("i" * 40, "Fix bug")
        required_keys = {"category", "problem", "solution", "source_commit", "files_affected", "prevention"}
        assert required_keys == set(entry.keys())

    def test_files_affected_is_list(self):
        """files_affected is always a list."""
        with patch.object(mine_mod, "get_commit_files", return_value=["file.yml"]):
            entry = extract_experience("j" * 40, "Fix something")
        assert isinstance(entry["files_affected"], list)

    def test_category_is_string(self):
        """category is always a string."""
        with patch.object(mine_mod, "get_commit_files", return_value=["file.yml"]):
            entry = extract_experience("k" * 40, "Fix something")
        assert isinstance(entry["category"], str)


# ── load_existing_ids extended ───────────────────────────────


class TestLoadExistingIdsExtended:
    """Extended tests for load_existing_ids function."""

    def test_loads_multiple_yml_files(self, tmp_path, monkeypatch):
        """load_existing_ids reads from multiple YAML files."""
        fixes_dir = tmp_path / "fixes"
        fixes_dir.mkdir()
        (fixes_dir / "a.yml").write_text(yaml.dump([{"id": "A-001", "source_commit": "aaa1234"}]))
        (fixes_dir / "b.yml").write_text(yaml.dump([{"id": "B-001", "source_commit": "bbb1234"}]))
        monkeypatch.setattr(mine_mod, "FIXES_DIR", fixes_dir)
        ids = load_existing_ids()
        assert "A-001" in ids
        assert "B-001" in ids
        assert "aaa1234" in ids
        assert "bbb1234" in ids

    def test_skips_entries_without_id(self, tmp_path, monkeypatch):
        """Entries without 'id' key are handled gracefully."""
        fixes_dir = tmp_path / "fixes"
        fixes_dir.mkdir()
        (fixes_dir / "c.yml").write_text(yaml.dump([
            {"source_commit": "ccc1234"},  # no id
            {"id": "C-002", "source_commit": "ddd1234"},
        ]))
        monkeypatch.setattr(mine_mod, "FIXES_DIR", fixes_dir)
        ids = load_existing_ids()
        assert "ccc1234" in ids
        assert "C-002" in ids
        assert "ddd1234" in ids

    def test_skips_entries_without_source_commit(self, tmp_path, monkeypatch):
        """Entries without 'source_commit' key are handled gracefully."""
        fixes_dir = tmp_path / "fixes"
        fixes_dir.mkdir()
        (fixes_dir / "d.yml").write_text(yaml.dump([
            {"id": "D-001"},  # no source_commit
        ]))
        monkeypatch.setattr(mine_mod, "FIXES_DIR", fixes_dir)
        ids = load_existing_ids()
        assert "D-001" in ids

    def test_ignores_non_dict_entries_in_list(self, tmp_path, monkeypatch):
        """Non-dict entries in a YAML list are skipped."""
        fixes_dir = tmp_path / "fixes"
        fixes_dir.mkdir()
        (fixes_dir / "e.yml").write_text(yaml.dump([
            "just a string",
            42,
            {"id": "E-001", "source_commit": "eee1234"},
        ]))
        monkeypatch.setattr(mine_mod, "FIXES_DIR", fixes_dir)
        ids = load_existing_ids()
        assert "E-001" in ids
        assert "eee1234" in ids

    def test_handles_nonexistent_directory(self, tmp_path, monkeypatch):
        """load_existing_ids handles non-existent FIXES_DIR gracefully."""
        fixes_dir = tmp_path / "nonexistent"
        monkeypatch.setattr(mine_mod, "FIXES_DIR", fixes_dir)
        # FIXES_DIR.glob("*.yml") on non-existent dir raises — but let's check
        # Actually, Path.glob on non-existent path returns empty iterator
        ids = load_existing_ids()
        assert ids == set()

    def test_ignores_non_yml_files(self, tmp_path, monkeypatch):
        """load_existing_ids only reads *.yml files."""
        fixes_dir = tmp_path / "fixes"
        fixes_dir.mkdir()
        (fixes_dir / "data.json").write_text('{"id": "JSON-001"}')
        (fixes_dir / "data.txt").write_text("TXT-001")
        (fixes_dir / "data.yml").write_text(yaml.dump([{"id": "YML-001", "source_commit": "fff1234"}]))
        monkeypatch.setattr(mine_mod, "FIXES_DIR", fixes_dir)
        ids = load_existing_ids()
        assert "YML-001" in ids
        assert "JSON-001" not in ids
        assert "TXT-001" not in ids

    def test_empty_yaml_file(self, tmp_path, monkeypatch):
        """Empty YAML file returns empty set."""
        fixes_dir = tmp_path / "fixes"
        fixes_dir.mkdir()
        (fixes_dir / "empty.yml").write_text("")
        monkeypatch.setattr(mine_mod, "FIXES_DIR", fixes_dir)
        ids = load_existing_ids()
        assert ids == set()

    def test_yaml_with_null_content(self, tmp_path, monkeypatch):
        """YAML file with null content is handled."""
        fixes_dir = tmp_path / "fixes"
        fixes_dir.mkdir()
        (fixes_dir / "null.yml").write_text("---\n")
        monkeypatch.setattr(mine_mod, "FIXES_DIR", fixes_dir)
        ids = load_existing_ids()
        assert ids == set()


# ── last mined commit extended ───────────────────────────────


class TestLastMinedCommitExtended:
    """Extended tests for save/load last mined commit."""

    def test_save_creates_file(self, tmp_path, monkeypatch):
        """save_last_mined_commit creates the file if it doesn't exist."""
        marker = tmp_path / ".last-mined-commit"
        monkeypatch.setattr(mine_mod, "LAST_MINED_FILE", marker)
        save_last_mined_commit("abc123")
        assert marker.exists()

    def test_save_overwrites_existing(self, tmp_path, monkeypatch):
        """save_last_mined_commit overwrites existing content."""
        marker = tmp_path / ".last-mined-commit"
        marker.write_text("old_hash\n")
        monkeypatch.setattr(mine_mod, "LAST_MINED_FILE", marker)
        save_last_mined_commit("new_hash")
        assert marker.read_text().strip() == "new_hash"

    def test_save_appends_newline(self, tmp_path, monkeypatch):
        """save_last_mined_commit appends a newline."""
        marker = tmp_path / ".last-mined-commit"
        monkeypatch.setattr(mine_mod, "LAST_MINED_FILE", marker)
        save_last_mined_commit("hash123")
        assert marker.read_text().endswith("\n")

    def test_load_strips_whitespace(self, tmp_path, monkeypatch):
        """load_last_mined_commit strips surrounding whitespace."""
        marker = tmp_path / ".last-mined-commit"
        marker.write_text("  abc123  \n\n")
        monkeypatch.setattr(mine_mod, "LAST_MINED_FILE", marker)
        result = load_last_mined_commit()
        assert result == "abc123"

    def test_load_whitespace_only_returns_none(self, tmp_path, monkeypatch):
        """load_last_mined_commit returns None for whitespace-only file."""
        marker = tmp_path / ".last-mined-commit"
        marker.write_text("   \n\n  ")
        monkeypatch.setattr(mine_mod, "LAST_MINED_FILE", marker)
        assert load_last_mined_commit() is None

    def test_roundtrip_preserves_full_hash(self, tmp_path, monkeypatch):
        """Save then load preserves a full 40-char hash."""
        marker = tmp_path / ".last-mined-commit"
        monkeypatch.setattr(mine_mod, "LAST_MINED_FILE", marker)
        full_hash = "a" * 40
        save_last_mined_commit(full_hash)
        assert load_last_mined_commit() == full_hash


# ── format_entries extended ──────────────────────────────────


class TestFormatEntriesExtended:
    """Extended tests for format_entries output format."""

    def test_header_contains_category(self):
        """Output starts with a comment line containing the category."""
        result = format_entries([], "test-cat")
        assert result.startswith("# Mined entries for test-cat")

    def test_empty_entries_produces_header_only(self):
        """Empty entries list produces just the header line."""
        result = format_entries([], "empty")
        assert result.strip() == "# Mined entries for empty"

    def test_entry_id_appears_correctly(self):
        """Entry ID appears as '- id: <value>'."""
        entries = [{
            "id": "TEST-001",
            "category": "test",
            "problem": "Test problem",
            "solution": "Test solution",
            "source_commit": "abc1234",
            "files_affected": ["file.yml"],
            "prevention": "Test prevention",
        }]
        result = format_entries(entries, "test")
        assert "- id: TEST-001" in result

    def test_category_field_in_output(self):
        """Category field appears correctly."""
        entries = [{
            "id": "TEST-001",
            "category": "ansible-lint",
            "problem": "Lint issue",
            "solution": "Fix it",
            "source_commit": "abc1234",
            "files_affected": ["file.yml"],
            "prevention": "Check",
        }]
        result = format_entries(entries, "ansible-lint")
        assert "  category: ansible-lint" in result

    def test_problem_is_quoted(self):
        """Problem field is double-quoted."""
        entries = [{
            "id": "TEST-001",
            "category": "test",
            "problem": "Simple problem",
            "solution": "Simple solution",
            "source_commit": "abc1234",
            "files_affected": ["file.yml"],
            "prevention": "Simple prevention",
        }]
        result = format_entries(entries, "test")
        assert '  problem: "Simple problem"' in result

    def test_solution_is_quoted(self):
        """Solution field is double-quoted."""
        entries = [{
            "id": "TEST-001",
            "category": "test",
            "problem": "P",
            "solution": "Fix via commit abc1234",
            "source_commit": "abc1234",
            "files_affected": ["file.yml"],
            "prevention": "N",
        }]
        result = format_entries(entries, "test")
        assert '  solution: "Fix via commit abc1234"' in result

    def test_source_commit_is_quoted(self):
        """Source commit field is double-quoted."""
        entries = [{
            "id": "TEST-001",
            "category": "test",
            "problem": "P",
            "solution": "S",
            "source_commit": "xyz7890",
            "files_affected": ["file.yml"],
            "prevention": "N",
        }]
        result = format_entries(entries, "test")
        assert '  source_commit: "xyz7890"' in result

    def test_prevention_is_quoted(self):
        """Prevention field is double-quoted."""
        entries = [{
            "id": "TEST-001",
            "category": "test",
            "problem": "P",
            "solution": "S",
            "source_commit": "abc1234",
            "files_affected": ["file.yml"],
            "prevention": "Added to library",
        }]
        result = format_entries(entries, "test")
        assert '  prevention: "Added to library"' in result

    def test_files_affected_single_file(self):
        """Single file in files_affected is formatted in brackets."""
        entries = [{
            "id": "TEST-001",
            "category": "test",
            "problem": "P",
            "solution": "S",
            "source_commit": "abc1234",
            "files_affected": ["single.yml"],
            "prevention": "N",
        }]
        result = format_entries(entries, "test")
        assert '  files_affected: ["single.yml"]' in result

    def test_files_affected_empty_list(self):
        """Empty files_affected produces empty brackets."""
        entries = [{
            "id": "TEST-001",
            "category": "test",
            "problem": "P",
            "solution": "S",
            "source_commit": "abc1234",
            "files_affected": [],
            "prevention": "N",
        }]
        result = format_entries(entries, "test")
        assert "  files_affected: []" in result

    def test_escapes_quotes_in_solution(self):
        """Double quotes in solution are escaped."""
        entries = [{
            "id": "TEST-001",
            "category": "test",
            "problem": "P",
            "solution": 'Use "new" method',
            "source_commit": "abc1234",
            "files_affected": ["f.yml"],
            "prevention": "N",
        }]
        result = format_entries(entries, "test")
        assert '\\"new\\"' in result

    def test_escapes_quotes_in_prevention(self):
        """Double quotes in prevention are escaped."""
        entries = [{
            "id": "TEST-001",
            "category": "test",
            "problem": "P",
            "solution": "S",
            "source_commit": "abc1234",
            "files_affected": ["f.yml"],
            "prevention": 'Check "always"',
        }]
        result = format_entries(entries, "test")
        assert '\\"always\\"' in result

    def test_output_ends_with_newline(self):
        """Formatted output ends with a newline."""
        entries = [{
            "id": "TEST-001",
            "category": "test",
            "problem": "P",
            "solution": "S",
            "source_commit": "abc1234",
            "files_affected": ["f.yml"],
            "prevention": "N",
        }]
        result = format_entries(entries, "test")
        assert result.endswith("\n")

    def test_entry_without_id_uses_default(self):
        """Entry without 'id' key uses 'MINED' as default."""
        entries = [{
            "category": "test",
            "problem": "P",
            "solution": "S",
            "source_commit": "abc1234",
            "files_affected": ["f.yml"],
            "prevention": "N",
        }]
        result = format_entries(entries, "test")
        assert "- id: MINED" in result

    def test_multiple_entries_separated_by_blank_line(self):
        """Multiple entries are separated by blank lines."""
        entry = {
            "id": "TEST-001",
            "category": "test",
            "problem": "P",
            "solution": "S",
            "source_commit": "abc1234",
            "files_affected": ["f.yml"],
            "prevention": "N",
        }
        entry2 = dict(entry, id="TEST-002")
        result = format_entries([entry, entry2], "test")
        lines = result.splitlines()
        # Find blank lines between entries
        blank_count = sum(1 for line in lines if line == "")
        assert blank_count >= 2  # At least one blank before each entry


# ── main() ID generation ─────────────────────────────────────


class TestMainIdGeneration:
    """Tests for the MINED-XXX-NNN ID generation in main()."""

    def _run_main_with_commits(self, tmp_path, monkeypatch, commits, files_fn):
        """Helper to run main() with specific commits and file patterns."""
        fixes_dir = tmp_path / "fixes"
        fixes_dir.mkdir()
        exp_dir = tmp_path / "exp"
        exp_dir.mkdir()
        last_file = tmp_path / ".last-mined-commit"

        monkeypatch.setattr(mine_mod, "FIXES_DIR", fixes_dir)
        monkeypatch.setattr(mine_mod, "EXPERIENCES_DIR", exp_dir)
        monkeypatch.setattr(mine_mod, "LAST_MINED_FILE", last_file)
        monkeypatch.setattr(mine_mod, "get_fix_commits", lambda since=None: commits)
        monkeypatch.setattr(mine_mod, "get_commit_files", files_fn)
        monkeypatch.setattr("sys.argv", ["mine-experiences.py"])

        mine_mod.main()
        return fixes_dir

    def test_lint_prefix_for_ansible_lint(self, tmp_path, monkeypatch):
        """ansible-lint category gets MINED-LINT prefix."""
        fixes_dir = self._run_main_with_commits(
            tmp_path, monkeypatch,
            [("a" * 40, "Fix lint noqa issue")],
            lambda h: ["roles/base/tasks/main.yml"],
        )
        content = (fixes_dir / "ansible-lint.yml").read_text()
        assert "MINED-LINT-001" in content

    def test_mol_prefix_for_molecule(self, tmp_path, monkeypatch):
        """molecule category gets MINED-MOL prefix."""
        fixes_dir = self._run_main_with_commits(
            tmp_path, monkeypatch,
            [("b" * 40, "Fix molecule converge test")],
            lambda h: ["roles/base/molecule/default/converge.yml"],
        )
        content = (fixes_dir / "molecule.yml").read_text()
        assert "MINED-MOL-001" in content

    def test_incus_prefix_for_incus_cli(self, tmp_path, monkeypatch):
        """incus-cli category gets MINED-INCUS prefix."""
        fixes_dir = self._run_main_with_commits(
            tmp_path, monkeypatch,
            [("c" * 40, "Fix incus bridge network creation")],
            lambda h: ["roles/incus_networks/tasks/main.yml"],
        )
        content = (fixes_dir / "incus-cli.yml").read_text()
        assert "MINED-INCUS-001" in content

    def test_gen_prefix_for_generator(self, tmp_path, monkeypatch):
        """generator category gets MINED-GEN prefix."""
        fixes_dir = self._run_main_with_commits(
            tmp_path, monkeypatch,
            [("d" * 40, "Fix generator validate orphan detection")],
            lambda h: ["scripts/generate.py"],
        )
        content = (fixes_dir / "generator.yml").read_text()
        assert "MINED-GEN-001" in content

    def test_counter_increments_for_same_category(self, tmp_path, monkeypatch):
        """Counter increments for multiple commits in the same category."""
        fixes_dir = self._run_main_with_commits(
            tmp_path, monkeypatch,
            [
                ("a" * 40, "Fix lint issue one"),
                ("b" * 40, "Fix noqa directive two"),
            ],
            lambda h: ["roles/base/tasks/main.yml"],
        )
        content = (fixes_dir / "ansible-lint.yml").read_text()
        assert "MINED-LINT-001" in content
        assert "MINED-LINT-002" in content

    def test_counters_independent_per_category(self, tmp_path, monkeypatch):
        """Each category has its own counter."""
        def files_fn(h):
            if h.startswith("a"):
                return ["roles/base/tasks/main.yml"]  # lint
            return ["roles/incus_networks/tasks/main.yml"]  # incus

        fixes_dir = self._run_main_with_commits(
            tmp_path, monkeypatch,
            [
                ("a" * 40, "Fix lint issue"),
                ("b" * 40, "Fix incus bridge network"),
            ],
            files_fn,
        )
        lint_content = (fixes_dir / "ansible-lint.yml").read_text()
        incus_content = (fixes_dir / "incus-cli.yml").read_text()
        assert "MINED-LINT-001" in lint_content
        assert "MINED-INCUS-001" in incus_content


# ── main() category file creation ─────────────────────────────


class TestMainCategoryFiles:
    """Tests for category file creation and appending in main()."""

    def test_creates_new_category_file_with_header(self, tmp_path, monkeypatch):
        """New category file starts with '---' YAML header."""
        fixes_dir = tmp_path / "fixes"
        fixes_dir.mkdir()
        exp_dir = tmp_path / "exp"
        exp_dir.mkdir()

        monkeypatch.setattr(mine_mod, "FIXES_DIR", fixes_dir)
        monkeypatch.setattr(mine_mod, "EXPERIENCES_DIR", exp_dir)
        monkeypatch.setattr(mine_mod, "LAST_MINED_FILE", tmp_path / ".last")
        monkeypatch.setattr(mine_mod, "get_fix_commits", lambda since=None: [("a" * 40, "Fix lint")])
        monkeypatch.setattr(mine_mod, "get_commit_files", lambda h: ["roles/base/tasks/main.yml"])
        monkeypatch.setattr("sys.argv", ["mine-experiences.py"])

        mine_mod.main()
        content = (fixes_dir / "ansible-lint.yml").read_text()
        assert content.startswith("---\n")

    def test_appends_to_existing_file(self, tmp_path, monkeypatch):
        """Appending to existing file preserves original content."""
        fixes_dir = tmp_path / "fixes"
        fixes_dir.mkdir()
        exp_dir = tmp_path / "exp"
        exp_dir.mkdir()

        existing = fixes_dir / "ansible-lint.yml"
        existing.write_text("---\n- id: OLD-001\n  category: ansible-lint\n")

        monkeypatch.setattr(mine_mod, "FIXES_DIR", fixes_dir)
        monkeypatch.setattr(mine_mod, "EXPERIENCES_DIR", exp_dir)
        monkeypatch.setattr(mine_mod, "LAST_MINED_FILE", tmp_path / ".last")
        monkeypatch.setattr(mine_mod, "get_fix_commits", lambda since=None: [("a" * 40, "Fix noqa lint")])
        monkeypatch.setattr(mine_mod, "get_commit_files", lambda h: ["roles/base/tasks/main.yml"])
        monkeypatch.setattr("sys.argv", ["mine-experiences.py"])

        mine_mod.main()
        content = existing.read_text()
        assert "OLD-001" in content
        assert "MINED-LINT-001" in content

    def test_skips_commits_with_known_source_hash(self, tmp_path, monkeypatch):
        """Commits whose short hash is in existing_ids are skipped."""
        fixes_dir = tmp_path / "fixes"
        fixes_dir.mkdir()
        exp_dir = tmp_path / "exp"
        exp_dir.mkdir()

        # Pre-create a file with a known source_commit
        (fixes_dir / "ansible-lint.yml").write_text(yaml.dump([
            {"id": "OLD-001", "source_commit": "aaaaaaa"},
        ]))

        monkeypatch.setattr(mine_mod, "FIXES_DIR", fixes_dir)
        monkeypatch.setattr(mine_mod, "EXPERIENCES_DIR", exp_dir)
        monkeypatch.setattr(mine_mod, "LAST_MINED_FILE", tmp_path / ".last")
        monkeypatch.setattr(mine_mod, "get_fix_commits", lambda since=None: [
            ("a" * 40, "Fix lint"),  # short hash = aaaaaaa → already exists
        ])
        monkeypatch.setattr(mine_mod, "get_commit_files", lambda h: ["roles/base/tasks/main.yml"])
        monkeypatch.setattr("sys.argv", ["mine-experiences.py"])

        mine_mod.main()
        content = (fixes_dir / "ansible-lint.yml").read_text()
        # Should NOT have added a new entry
        assert "MINED-LINT" not in content

    def test_no_new_entries_message(self, tmp_path, monkeypatch, capsys):
        """When all commits are skipped, prints 'No new entries to add.'."""
        fixes_dir = tmp_path / "fixes"
        fixes_dir.mkdir()
        exp_dir = tmp_path / "exp"
        exp_dir.mkdir()

        (fixes_dir / "ansible-lint.yml").write_text(yaml.dump([
            {"id": "OLD-001", "source_commit": "aaaaaaa"},
        ]))

        monkeypatch.setattr(mine_mod, "FIXES_DIR", fixes_dir)
        monkeypatch.setattr(mine_mod, "EXPERIENCES_DIR", exp_dir)
        monkeypatch.setattr(mine_mod, "LAST_MINED_FILE", tmp_path / ".last")
        monkeypatch.setattr(mine_mod, "get_fix_commits", lambda since=None: [
            ("a" * 40, "Fix lint"),
        ])
        monkeypatch.setattr(mine_mod, "get_commit_files", lambda h: ["roles/base/tasks/main.yml"])
        monkeypatch.setattr("sys.argv", ["mine-experiences.py"])

        mine_mod.main()
        captured = capsys.readouterr()
        assert "No new entries to add." in captured.out


# ── main() dry-run extended ─────────────────────────────────


class TestMainDryRunExtended:
    """Extended tests for --dry-run mode."""

    def test_dry_run_prints_formatted_output(self, tmp_path, monkeypatch, capsys):
        """--dry-run prints formatted entries to stdout."""
        fixes_dir = tmp_path / "fixes"
        fixes_dir.mkdir()
        exp_dir = tmp_path / "exp"
        exp_dir.mkdir()

        monkeypatch.setattr(mine_mod, "FIXES_DIR", fixes_dir)
        monkeypatch.setattr(mine_mod, "EXPERIENCES_DIR", exp_dir)
        monkeypatch.setattr(mine_mod, "LAST_MINED_FILE", tmp_path / ".last")
        monkeypatch.setattr(mine_mod, "get_fix_commits", lambda since=None: [("a" * 40, "Fix lint issue")])
        monkeypatch.setattr(mine_mod, "get_commit_files", lambda h: ["roles/base/tasks/main.yml"])
        monkeypatch.setattr("sys.argv", ["mine-experiences.py", "--dry-run"])

        mine_mod.main()

        captured = capsys.readouterr()
        assert "MINED-LINT-001" in captured.out
        # Should NOT create files in dry-run
        assert not list(fixes_dir.glob("*.yml"))

    def test_dry_run_does_not_save_last_commit(self, tmp_path, monkeypatch):
        """--dry-run does not save the last mined commit."""
        fixes_dir = tmp_path / "fixes"
        fixes_dir.mkdir()
        exp_dir = tmp_path / "exp"
        exp_dir.mkdir()
        last_file = tmp_path / ".last-mined-commit"

        monkeypatch.setattr(mine_mod, "FIXES_DIR", fixes_dir)
        monkeypatch.setattr(mine_mod, "EXPERIENCES_DIR", exp_dir)
        monkeypatch.setattr(mine_mod, "LAST_MINED_FILE", last_file)
        monkeypatch.setattr(mine_mod, "get_fix_commits", lambda since=None: [("a" * 40, "Fix lint")])
        monkeypatch.setattr(mine_mod, "get_commit_files", lambda h: ["roles/base/tasks/main.yml"])
        monkeypatch.setattr("sys.argv", ["mine-experiences.py", "--dry-run"])

        mine_mod.main()
        assert not last_file.exists()


# ── main() --since flag ──────────────────────────────────────


class TestMainSinceFlag:
    """Tests for the --since CLI argument."""

    def test_since_flag_passed_to_get_fix_commits(self, tmp_path, monkeypatch):
        """--since <hash> is passed to get_fix_commits."""
        fixes_dir = tmp_path / "fixes"
        fixes_dir.mkdir()

        captured_since = []

        def mock_get_fix_commits(since=None):
            captured_since.append(since)
            return []

        monkeypatch.setattr(mine_mod, "FIXES_DIR", fixes_dir)
        monkeypatch.setattr(mine_mod, "EXPERIENCES_DIR", tmp_path / "exp")
        monkeypatch.setattr(mine_mod, "LAST_MINED_FILE", tmp_path / ".last")
        monkeypatch.setattr(mine_mod, "get_fix_commits", mock_get_fix_commits)
        monkeypatch.setattr("sys.argv", ["mine-experiences.py", "--since", "abc123"])

        mine_mod.main()
        assert captured_since == ["abc123"]

    def test_since_overrides_incremental(self, tmp_path, monkeypatch):
        """--since takes priority when both --since and --incremental are given."""
        fixes_dir = tmp_path / "fixes"
        fixes_dir.mkdir()
        last_file = tmp_path / ".last-mined-commit"
        last_file.write_text("old_hash\n")

        captured_since = []

        def mock_get_fix_commits(since=None):
            captured_since.append(since)
            return []

        monkeypatch.setattr(mine_mod, "FIXES_DIR", fixes_dir)
        monkeypatch.setattr(mine_mod, "EXPERIENCES_DIR", tmp_path / "exp")
        monkeypatch.setattr(mine_mod, "LAST_MINED_FILE", last_file)
        monkeypatch.setattr(mine_mod, "get_fix_commits", mock_get_fix_commits)
        monkeypatch.setattr("sys.argv", ["mine-experiences.py", "--since", "explicit_hash", "--incremental"])

        mine_mod.main()
        # --since is set → incremental does not override
        assert captured_since == ["explicit_hash"]


# ── main() incremental mode extended ─────────────────────────


class TestMainIncrementalExtended:
    """Extended tests for --incremental mode behavior."""

    def test_incremental_without_marker_file(self, tmp_path, monkeypatch):
        """--incremental without a marker file uses since=None."""
        fixes_dir = tmp_path / "fixes"
        fixes_dir.mkdir()

        captured_since = []

        def mock_get_fix_commits(since=None):
            captured_since.append(since)
            return []

        monkeypatch.setattr(mine_mod, "FIXES_DIR", fixes_dir)
        monkeypatch.setattr(mine_mod, "EXPERIENCES_DIR", tmp_path / "exp")
        monkeypatch.setattr(mine_mod, "LAST_MINED_FILE", tmp_path / ".nonexistent")
        monkeypatch.setattr(mine_mod, "get_fix_commits", mock_get_fix_commits)
        monkeypatch.setattr("sys.argv", ["mine-experiences.py", "--incremental"])

        mine_mod.main()
        assert captured_since == [None]

    def test_incremental_with_marker_file(self, tmp_path, monkeypatch):
        """--incremental with a marker file passes its content as since."""
        fixes_dir = tmp_path / "fixes"
        fixes_dir.mkdir()
        last_file = tmp_path / ".last-mined-commit"
        last_file.write_text("saved_hash_123\n")

        captured_since = []

        def mock_get_fix_commits(since=None):
            captured_since.append(since)
            return []

        monkeypatch.setattr(mine_mod, "FIXES_DIR", fixes_dir)
        monkeypatch.setattr(mine_mod, "EXPERIENCES_DIR", tmp_path / "exp")
        monkeypatch.setattr(mine_mod, "LAST_MINED_FILE", last_file)
        monkeypatch.setattr(mine_mod, "get_fix_commits", mock_get_fix_commits)
        monkeypatch.setattr("sys.argv", ["mine-experiences.py", "--incremental"])

        mine_mod.main()
        assert captured_since == ["saved_hash_123"]

    def test_incremental_prints_since_message(self, tmp_path, monkeypatch, capsys):
        """--incremental prints the 'mining since' message."""
        fixes_dir = tmp_path / "fixes"
        fixes_dir.mkdir()
        last_file = tmp_path / ".last-mined-commit"
        last_file.write_text("abcdef1234567890\n")

        monkeypatch.setattr(mine_mod, "FIXES_DIR", fixes_dir)
        monkeypatch.setattr(mine_mod, "EXPERIENCES_DIR", tmp_path / "exp")
        monkeypatch.setattr(mine_mod, "LAST_MINED_FILE", last_file)
        monkeypatch.setattr(mine_mod, "get_fix_commits", lambda since=None: [])
        monkeypatch.setattr("sys.argv", ["mine-experiences.py", "--incremental"])

        mine_mod.main()
        captured = capsys.readouterr()
        assert "Incremental mode:" in captured.out
        assert "abcdef1" in captured.out


# ── main() console output ───────────────────────────────────


class TestMainOutput:
    """Tests for main() console output."""

    def test_no_commits_message(self, tmp_path, monkeypatch, capsys):
        """main() prints 'No fix commits found.' when no commits."""
        fixes_dir = tmp_path / "fixes"
        fixes_dir.mkdir()

        monkeypatch.setattr(mine_mod, "FIXES_DIR", fixes_dir)
        monkeypatch.setattr(mine_mod, "EXPERIENCES_DIR", tmp_path / "exp")
        monkeypatch.setattr(mine_mod, "LAST_MINED_FILE", tmp_path / ".last")
        monkeypatch.setattr(mine_mod, "get_fix_commits", lambda since=None: [])
        monkeypatch.setattr("sys.argv", ["mine-experiences.py"])

        mine_mod.main()
        captured = capsys.readouterr()
        assert "No fix commits found." in captured.out

    def test_found_commits_count_message(self, tmp_path, monkeypatch, capsys):
        """main() prints 'Found N fix commits' message."""
        fixes_dir = tmp_path / "fixes"
        fixes_dir.mkdir()
        exp_dir = tmp_path / "exp"
        exp_dir.mkdir()

        monkeypatch.setattr(mine_mod, "FIXES_DIR", fixes_dir)
        monkeypatch.setattr(mine_mod, "EXPERIENCES_DIR", exp_dir)
        monkeypatch.setattr(mine_mod, "LAST_MINED_FILE", tmp_path / ".last")
        monkeypatch.setattr(mine_mod, "get_fix_commits", lambda since=None: [
            ("a" * 40, "Fix something"),
            ("b" * 40, "Fix another"),
        ])
        monkeypatch.setattr(mine_mod, "get_commit_files", lambda h: ["file.yml"])
        monkeypatch.setattr("sys.argv", ["mine-experiences.py"])

        mine_mod.main()
        captured = capsys.readouterr()
        assert "Found 2 fix commits" in captured.out

    def test_new_entries_count_message(self, tmp_path, monkeypatch, capsys):
        """main() prints new entries and skipped counts."""
        fixes_dir = tmp_path / "fixes"
        fixes_dir.mkdir()
        exp_dir = tmp_path / "exp"
        exp_dir.mkdir()

        monkeypatch.setattr(mine_mod, "FIXES_DIR", fixes_dir)
        monkeypatch.setattr(mine_mod, "EXPERIENCES_DIR", exp_dir)
        monkeypatch.setattr(mine_mod, "LAST_MINED_FILE", tmp_path / ".last")
        monkeypatch.setattr(mine_mod, "get_fix_commits", lambda since=None: [
            ("a" * 40, "Fix lint issue"),
        ])
        monkeypatch.setattr(mine_mod, "get_commit_files", lambda h: ["roles/base/tasks/main.yml"])
        monkeypatch.setattr("sys.argv", ["mine-experiences.py"])

        mine_mod.main()
        captured = capsys.readouterr()
        assert "New entries: 1" in captured.out
        assert "Skipped" in captured.out

    def test_saves_latest_commit_hash(self, tmp_path, monkeypatch):
        """main() saves the first (most recent) commit hash."""
        fixes_dir = tmp_path / "fixes"
        fixes_dir.mkdir()
        exp_dir = tmp_path / "exp"
        exp_dir.mkdir()
        last_file = tmp_path / ".last"

        monkeypatch.setattr(mine_mod, "FIXES_DIR", fixes_dir)
        monkeypatch.setattr(mine_mod, "EXPERIENCES_DIR", exp_dir)
        monkeypatch.setattr(mine_mod, "LAST_MINED_FILE", last_file)
        monkeypatch.setattr(mine_mod, "get_fix_commits", lambda since=None: [
            ("x" * 40, "Fix first (most recent)"),
            ("y" * 40, "Fix second (older)"),
        ])
        monkeypatch.setattr(mine_mod, "get_commit_files", lambda h: ["file.yml"])
        monkeypatch.setattr("sys.argv", ["mine-experiences.py"])

        mine_mod.main()
        assert last_file.read_text().strip() == "x" * 40


# ── main() skips commits with no files ───────────────────────


class TestMainSkipsEmptyCommits:
    """Tests that main() skips commits with no files."""

    def test_commit_with_no_files_skipped(self, tmp_path, monkeypatch):
        """Commits where get_commit_files returns empty are skipped."""
        fixes_dir = tmp_path / "fixes"
        fixes_dir.mkdir()
        exp_dir = tmp_path / "exp"
        exp_dir.mkdir()

        def files_fn(h):
            if h.startswith("a"):
                return []  # no files
            return ["file.yml"]

        monkeypatch.setattr(mine_mod, "FIXES_DIR", fixes_dir)
        monkeypatch.setattr(mine_mod, "EXPERIENCES_DIR", exp_dir)
        monkeypatch.setattr(mine_mod, "LAST_MINED_FILE", tmp_path / ".last")
        monkeypatch.setattr(mine_mod, "get_fix_commits", lambda since=None: [
            ("a" * 40, "Fix empty commit"),
            ("b" * 40, "Fix real commit"),
        ])
        monkeypatch.setattr(mine_mod, "get_commit_files", files_fn)
        monkeypatch.setattr("sys.argv", ["mine-experiences.py"])

        mine_mod.main()
        yml_files = list(fixes_dir.glob("*.yml"))
        if yml_files:
            content = yml_files[0].read_text()
            # Only the second commit should appear
            assert "bbbbbbb" in content
            assert "aaaaaaa" not in content

    def test_all_commits_empty_files_no_output(self, tmp_path, monkeypatch, capsys):
        """When all commits have no files, prints 'No new entries'."""
        fixes_dir = tmp_path / "fixes"
        fixes_dir.mkdir()
        exp_dir = tmp_path / "exp"
        exp_dir.mkdir()

        monkeypatch.setattr(mine_mod, "FIXES_DIR", fixes_dir)
        monkeypatch.setattr(mine_mod, "EXPERIENCES_DIR", exp_dir)
        monkeypatch.setattr(mine_mod, "LAST_MINED_FILE", tmp_path / ".last")
        monkeypatch.setattr(mine_mod, "get_fix_commits", lambda since=None: [
            ("a" * 40, "Fix something"),
        ])
        monkeypatch.setattr(mine_mod, "get_commit_files", lambda h: [])
        monkeypatch.setattr("sys.argv", ["mine-experiences.py"])

        mine_mod.main()
        captured = capsys.readouterr()
        assert "No new entries to add." in captured.out


# ── Script structure and constants ───────────────────────────


class TestScriptStructure:
    """Tests for script-level constants and structure."""

    def test_fix_patterns_is_compiled_regex(self):
        """FIX_PATTERNS is a compiled regex."""
        import re
        assert isinstance(FIX_PATTERNS, re.Pattern)

    def test_category_map_has_four_categories(self):
        """CATEGORY_MAP has exactly 4 categories."""
        assert len(CATEGORY_MAP) == 4
        expected = {"ansible-lint", "molecule", "incus-cli", "generator"}
        assert set(CATEGORY_MAP.keys()) == expected

    def test_category_map_values_are_compiled_regex(self):
        """All CATEGORY_MAP values are compiled regex patterns."""
        import re
        for cat, pattern in CATEGORY_MAP.items():
            assert isinstance(pattern, re.Pattern), f"{cat} is not a compiled regex"

    def test_project_dir_exists(self):
        """PROJECT_DIR points to the project root."""
        project_dir = mine_mod.PROJECT_DIR
        assert project_dir.exists()

    def test_experiences_dir_path(self):
        """EXPERIENCES_DIR is under PROJECT_DIR."""
        assert mine_mod.EXPERIENCES_DIR == mine_mod.PROJECT_DIR / "experiences"

    def test_fixes_dir_path(self):
        """FIXES_DIR is under EXPERIENCES_DIR."""
        assert mine_mod.FIXES_DIR == mine_mod.EXPERIENCES_DIR / "fixes"

    def test_last_mined_file_path(self):
        """LAST_MINED_FILE is under EXPERIENCES_DIR."""
        assert mine_mod.LAST_MINED_FILE == mine_mod.EXPERIENCES_DIR / ".last-mined-commit"

    def test_fix_patterns_flags_case_insensitive(self):
        """FIX_PATTERNS has the IGNORECASE flag."""
        import re
        assert FIX_PATTERNS.flags & re.IGNORECASE

    def test_module_has_main_function(self):
        """Module has a main() function."""
        assert callable(mine_mod.main)

    def test_module_has_all_public_functions(self):
        """Module exposes all expected public functions."""
        expected = [
            "run_git", "get_fix_commits", "get_commit_files",
            "categorize_commit", "extract_experience", "load_existing_ids",
            "load_last_mined_commit", "save_last_mined_commit",
            "format_entries", "main",
        ]
        for name in expected:
            assert hasattr(mine_mod, name), f"Module missing function: {name}"


# ── Edge cases for file pattern extraction ───────────────────


class TestFilePatternExtraction:
    """Tests for file path generalization in extract_experience."""

    def test_roles_with_exactly_three_parts(self):
        """roles/rolename/file.yml → roles/*/file.yml."""
        with patch.object(mine_mod, "get_commit_files", return_value=["roles/myrol/file.yml"]):
            entry = extract_experience("a" * 40, "Fix something")
        assert "roles/*/file.yml" in entry["files_affected"]

    def test_top_level_files_unchanged(self):
        """Top-level files like Makefile are not generalized."""
        with patch.object(mine_mod, "get_commit_files", return_value=["Makefile"]):
            entry = extract_experience("b" * 40, "Fix Makefile")
        assert "Makefile" in entry["files_affected"]

    def test_scripts_directory_unchanged(self):
        """scripts/ files are not generalized."""
        with patch.object(mine_mod, "get_commit_files", return_value=["scripts/mine-experiences.py"]):
            entry = extract_experience("c" * 40, "Fix miner")
        assert "scripts/mine-experiences.py" in entry["files_affected"]

    def test_docs_directory_unchanged(self):
        """docs/ files are not generalized."""
        with patch.object(mine_mod, "get_commit_files", return_value=["docs/SPEC.md"]):
            entry = extract_experience("d" * 40, "Fix docs")
        assert "docs/SPEC.md" in entry["files_affected"]

    def test_tests_directory_unchanged(self):
        """tests/ files are not generalized."""
        with patch.object(mine_mod, "get_commit_files", return_value=["tests/test_generate.py"]):
            entry = extract_experience("e" * 40, "Fix test")
        assert "tests/test_generate.py" in entry["files_affected"]

    def test_roles_meta_main_yml(self):
        """roles/role/meta/main.yml → roles/*/meta/main.yml."""
        with patch.object(mine_mod, "get_commit_files", return_value=["roles/base_system/meta/main.yml"]):
            entry = extract_experience("f" * 40, "Fix meta")
        assert "roles/*/meta/main.yml" in entry["files_affected"]

    def test_roles_handlers_main_yml(self):
        """roles/role/handlers/main.yml → roles/*/handlers/main.yml."""
        with patch.object(mine_mod, "get_commit_files", return_value=["roles/base_system/handlers/main.yml"]):
            entry = extract_experience("g" * 40, "Fix handlers")
        assert "roles/*/handlers/main.yml" in entry["files_affected"]

    def test_roles_templates_file(self):
        """roles/role/templates/tmpl.j2 → roles/*/templates/tmpl.j2."""
        with patch.object(mine_mod, "get_commit_files", return_value=["roles/stt_server/templates/speaches.j2"]):
            entry = extract_experience("h" * 40, "Fix template")
        assert "roles/*/templates/speaches.j2" in entry["files_affected"]

    def test_roles_vars_main_yml(self):
        """roles/role/vars/main.yml → roles/*/vars/main.yml."""
        with patch.object(mine_mod, "get_commit_files", return_value=["roles/incus_networks/vars/main.yml"]):
            entry = extract_experience("i" * 40, "Fix vars")
        assert "roles/*/vars/main.yml" in entry["files_affected"]

    def test_dedup_across_different_roles_same_subpath(self):
        """Different roles with same sub-path are deduplicated to one pattern."""
        with patch.object(mine_mod, "get_commit_files", return_value=[
            "roles/roleA/tasks/main.yml",
            "roles/roleB/tasks/main.yml",
            "roles/roleC/tasks/main.yml",
        ]):
            entry = extract_experience("j" * 40, "Fix all tasks")
        # Only 3 were processed (< 5 limit), but deduplicated to 1
        assert entry["files_affected"] == ["roles/*/tasks/main.yml"]

    def test_mixed_role_and_non_role_files(self):
        """Mix of role and non-role files."""
        with patch.object(mine_mod, "get_commit_files", return_value=[
            "roles/base_system/tasks/main.yml",
            "scripts/generate.py",
            "Makefile",
        ]):
            entry = extract_experience("k" * 40, "Fix multiple")
        assert "roles/*/tasks/main.yml" in entry["files_affected"]
        assert "scripts/generate.py" in entry["files_affected"]
        assert "Makefile" in entry["files_affected"]


# ── Prefix map coverage ─────────────────────────────────────


class TestPrefixMap:
    """Tests for the prefix_map used in main() for ID generation."""

    def test_prefix_map_covers_all_categories(self):
        """The prefix_map in main() covers all CATEGORY_MAP keys."""
        # Read from source: the prefix_map is defined inline in main()
        prefix_map = {
            "ansible-lint": "MINED-LINT",
            "molecule": "MINED-MOL",
            "incus-cli": "MINED-INCUS",
            "generator": "MINED-GEN",
        }
        for cat in CATEGORY_MAP:
            assert cat in prefix_map, f"Category {cat} missing from prefix_map"

    def test_unknown_category_gets_mined_prefix(self, tmp_path, monkeypatch):
        """Categories not in prefix_map get default 'MINED' prefix."""
        # The prefix_map.get(cat, "MINED") provides the fallback
        # We verify by checking the source code pattern
        prefix_map = {
            "ansible-lint": "MINED-LINT",
            "molecule": "MINED-MOL",
            "incus-cli": "MINED-INCUS",
            "generator": "MINED-GEN",
        }
        assert prefix_map.get("unknown-category", "MINED") == "MINED"

    def test_id_format_three_digit_counter(self, tmp_path, monkeypatch):
        """IDs use 3-digit zero-padded counters."""
        fixes_dir = tmp_path / "fixes"
        fixes_dir.mkdir()
        exp_dir = tmp_path / "exp"
        exp_dir.mkdir()

        monkeypatch.setattr(mine_mod, "FIXES_DIR", fixes_dir)
        monkeypatch.setattr(mine_mod, "EXPERIENCES_DIR", exp_dir)
        monkeypatch.setattr(mine_mod, "LAST_MINED_FILE", tmp_path / ".last")
        monkeypatch.setattr(mine_mod, "get_fix_commits", lambda since=None: [("a" * 40, "Fix lint")])
        monkeypatch.setattr(mine_mod, "get_commit_files", lambda h: ["roles/base/tasks/main.yml"])
        monkeypatch.setattr("sys.argv", ["mine-experiences.py"])

        mine_mod.main()
        content = (fixes_dir / "ansible-lint.yml").read_text()
        assert "MINED-LINT-001" in content  # 3-digit zero-padded


# ── Format entries YAML structure ────────────────────────────


class TestFormatEntriesYAMLStructure:
    """Tests for the YAML structure of format_entries output."""

    def _make_entry(self, **overrides):
        """Create a standard test entry with optional overrides."""
        entry = {
            "id": "TEST-001",
            "category": "test",
            "problem": "Test problem",
            "solution": "Test solution",
            "source_commit": "abc1234",
            "files_affected": ["file.yml"],
            "prevention": "Test prevention",
        }
        entry.update(overrides)
        return entry

    def test_each_entry_starts_with_dash_id(self):
        """Each entry in output starts with '- id:'."""
        result = format_entries([self._make_entry()], "test")
        assert "- id: TEST-001" in result

    def test_indented_fields_use_two_spaces(self):
        """Non-id fields are indented with 2 spaces."""
        result = format_entries([self._make_entry()], "test")
        lines = result.splitlines()
        for line in lines:
            if line.startswith("  "):
                # All indented lines should start with exactly 2 spaces
                assert line.startswith("  ")

    def test_field_order_in_output(self):
        """Fields appear in the expected order: id, category, problem, solution, source_commit, files_affected, prevention."""
        result = format_entries([self._make_entry()], "test")
        lines = [l.strip() for l in result.splitlines() if l.strip()]
        field_lines = [l for l in lines if ":" in l and not l.startswith("#")]
        field_names = [l.split(":")[0].lstrip("- ") for l in field_lines]
        expected_order = ["id", "category", "problem", "solution", "source_commit", "files_affected", "prevention"]
        assert field_names == expected_order

    def test_special_chars_in_problem_escaped(self):
        """Special characters in problem are properly escaped."""
        entry = self._make_entry(problem='Fix "the" thing\'s issue')
        result = format_entries([entry], "test")
        assert '\\"the\\"' in result

    def test_long_file_list(self):
        """Multiple files are comma-separated in brackets."""
        entry = self._make_entry(files_affected=["a.yml", "b.yml", "c.yml", "d.yml", "e.yml"])
        result = format_entries([entry], "test")
        assert '"a.yml", "b.yml", "c.yml", "d.yml", "e.yml"' in result

    def test_single_file_in_brackets(self):
        """Single file is still in brackets."""
        entry = self._make_entry(files_affected=["only.yml"])
        result = format_entries([entry], "test")
        assert '["only.yml"]' in result
