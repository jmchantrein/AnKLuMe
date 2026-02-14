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
    def test_matches_fix_keywords(self):
        """FIX_PATTERNS matches fix, lint, resolve, hotfix, workaround, bug."""
        assert FIX_PATTERNS.search("Fix ansible-lint violations")
        assert FIX_PATTERNS.search("Lint cleanup for CI")
        assert FIX_PATTERNS.search("Resolve merge conflict in roles/")
        assert FIX_PATTERNS.search("Hotfix for broken molecule test")
        assert FIX_PATTERNS.search("Add workaround for Incus bug")
        assert FIX_PATTERNS.search("Bug in subnet calculation")

    def test_no_match_feature_or_refactor(self):
        """FIX_PATTERNS does not match feature/refactor commits."""
        assert not FIX_PATTERNS.search("Add new monitoring role")
        assert not FIX_PATTERNS.search("Refactor network module")

    def test_case_insensitive(self):
        """FIX_PATTERNS matches case-insensitively."""
        assert FIX_PATTERNS.search("FIX uppercase")
        assert FIX_PATTERNS.search("HOTFIX emergency")

    def test_word_boundary(self):
        """FIX_PATTERNS respects word boundaries."""
        assert not FIX_PATTERNS.search("debug mode enabled")
        assert not FIX_PATTERNS.search("add test fixture")
        assert FIX_PATTERNS.search("fix is needed")


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

    def test_mixed_signals_highest_score_wins(self):
        """When multiple categories match, the highest score wins."""
        cat = categorize_commit(
            "Fix incus bridge network device profile project",
            ["roles/incus_networks/tasks/main.yml"],
        )
        assert cat == "incus-cli"


# ── extract_experience ──────────────────────────────────────


class TestExtractExperience:
    def test_extracts_basic_entry(self):
        """extract_experience creates a well-formed entry with required fields."""
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
        required_keys = {"category", "problem", "solution", "source_commit", "files_affected", "prevention"}
        assert required_keys == set(entry.keys())

    def test_returns_none_when_no_files(self):
        """extract_experience returns None when commit has no files."""
        with patch.object(mine_mod, "get_commit_files", return_value=[]):
            entry = extract_experience("abc1234567890", "Empty commit")
        assert entry is None

    def test_file_patterns_generalization(self):
        """extract_experience generalizes role paths but keeps non-role paths."""
        with patch.object(mine_mod, "get_commit_files", return_value=[
            "roles/incus_networks/tasks/main.yml",
        ]):
            entry = extract_experience("abc1234567890", "Fix incus bug")
        assert "roles/*/tasks/main.yml" in entry["files_affected"]

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


# ── get_fix_commits (git log parsing) ─────────────────────────


class TestGetFixCommits:
    def test_returns_list_of_tuples(self):
        """get_fix_commits returns a list of (hash, message) tuples."""
        commits = get_fix_commits()
        assert isinstance(commits, list)
        if commits:
            assert len(commits[0]) == 2
            assert len(commits[0][0]) == 40  # Full SHA

    def test_since_limits_results(self):
        """get_fix_commits with since= returns fewer results."""
        all_commits = get_fix_commits()
        if len(all_commits) > 1:
            mid_hash = all_commits[len(all_commits) // 2][0]
            since_commits = get_fix_commits(since_commit=mid_hash)
            assert len(since_commits) <= len(all_commits)

    def test_parsing_filters_non_fix_commits(self, monkeypatch):
        """Non-fix commits are filtered by FIX_PATTERNS."""
        fake_output = "\n".join([
            "a" * 40 + " Add new feature",
            "b" * 40 + " Fix broken build",
            "c" * 40 + " Refactor module",
        ])

        def mock_run(args, **kwargs):
            return subprocess.CompletedProcess(args, returncode=0, stdout=fake_output, stderr="")

        monkeypatch.setattr(subprocess, "run", mock_run)
        commits = get_fix_commits()
        assert len(commits) == 1
        assert commits[0][1] == "Fix broken build"

    def test_empty_commit_message_skipped(self, monkeypatch):
        """A line with only a hash and no message is skipped gracefully."""
        fake_output = "ddd0000000000000000000000000000000000000000"

        def mock_run(args, **kwargs):
            return subprocess.CompletedProcess(args, returncode=0, stdout=fake_output, stderr="")

        monkeypatch.setattr(subprocess, "run", mock_run)
        commits = get_fix_commits()
        assert commits == []

    def test_git_failure_returns_empty_commits(self, monkeypatch):
        """When git fails, get_fix_commits returns an empty list."""

        def mock_run(args, **kwargs):
            return subprocess.CompletedProcess(args, returncode=128, stdout="", stderr="fatal")

        monkeypatch.setattr(subprocess, "run", mock_run)
        commits = get_fix_commits()
        assert commits == []


# ── get_commit_files (diff parsing) ────────────────────────────


class TestGetCommitFiles:
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

        fake_commits = [
            ("a" * 40, "Fix ansible-lint violation in base_system"),
            ("b" * 40, "Fix molecule test converge failure"),
        ]
        monkeypatch.setattr(mine_mod, "get_fix_commits", lambda since=None: fake_commits)

        def fake_files(commit_hash):
            if commit_hash.startswith("a"):
                return ["roles/base_system/tasks/main.yml"]
            return ["roles/base_system/molecule/default/converge.yml"]

        monkeypatch.setattr(mine_mod, "get_commit_files", fake_files)
        monkeypatch.setattr("sys.argv", ["mine-experiences.py"])
        mine_mod.main()

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


# ── duplicate detection ──────────────────────────────────


class TestMineDuplicateDetection:
    """Test that mining twice on same commits produces no duplicates."""

    def test_no_duplicate_entries_on_second_run(self, tmp_path, monkeypatch):
        """Running mine twice on same commits produces no duplicate entries."""
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
        # Second run — same commits, should be skipped
        mine_mod.main()
        content_after_second = yml_files[0].read_text()
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

        assert len(call_log) == 2
        assert call_log[0] is None  # First run: no since
        assert call_log[1] == "f" * 40  # Second run: last mined commit


# ── dry-run mode ─────────────────────────────────────────


class TestMainDryRun:
    def test_dry_run_does_not_write(self, tmp_path, monkeypatch, capsys):
        """--dry-run prints entries but does not create files or save last commit."""
        fixes_dir = tmp_path / "fixes"
        fixes_dir.mkdir()
        exp_dir = tmp_path / "exp"
        exp_dir.mkdir()
        last_file = tmp_path / ".last-mined-commit"

        monkeypatch.setattr(mine_mod, "FIXES_DIR", fixes_dir)
        monkeypatch.setattr(mine_mod, "EXPERIENCES_DIR", exp_dir)
        monkeypatch.setattr(mine_mod, "LAST_MINED_FILE", last_file)
        monkeypatch.setattr(mine_mod, "get_fix_commits", lambda since=None: [("a" * 40, "Fix lint issue")])
        monkeypatch.setattr(mine_mod, "get_commit_files", lambda h: ["roles/base/tasks/main.yml"])
        monkeypatch.setattr("sys.argv", ["mine-experiences.py", "--dry-run"])

        mine_mod.main()

        captured = capsys.readouterr()
        assert "MINED-LINT-001" in captured.out
        assert not list(fixes_dir.glob("*.yml"))
        assert not last_file.exists()
