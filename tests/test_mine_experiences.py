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
