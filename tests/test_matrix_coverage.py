"""Tests for scripts/matrix-coverage.py — behavior matrix coverage checker."""

import sys
from pathlib import Path

import pytest
import yaml

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from importlib import import_module  # noqa: E402

# Import without triggering __main__
matrix_mod = import_module("matrix-coverage")
load_matrix = matrix_mod.load_matrix
scan_test_files = matrix_mod.scan_test_files
report = matrix_mod.report
main = matrix_mod.main


# ── load_matrix ─────────────────────────────────────────────


class TestLoadMatrix:
    def test_loads_valid_matrix(self, tmp_path):
        """load_matrix parses a valid behavior matrix YAML."""
        matrix = tmp_path / "matrix.yml"
        matrix.write_text(yaml.dump({
            "capabilities": {
                "test_cap": {
                    "depth_1": [
                        {"id": "TC-001", "action": "Do X", "expected": "Y"},
                        {"id": "TC-002", "action": "Do Z", "expected": "W"},
                    ],
                    "depth_2": [
                        {"id": "TC-2-001", "action": "Do XZ", "expected": "YW"},
                    ],
                },
            },
        }))
        cells, all_ids = load_matrix(matrix)
        assert "test_cap" in cells
        assert cells["test_cap"]["depth_1"] == ["TC-001", "TC-002"]
        assert cells["test_cap"]["depth_2"] == ["TC-2-001"]
        assert all_ids == {"TC-001", "TC-002", "TC-2-001"}

    def test_handles_empty_capabilities(self, tmp_path):
        """load_matrix handles empty capabilities dict."""
        matrix = tmp_path / "matrix.yml"
        matrix.write_text(yaml.dump({"capabilities": {}}))
        cells, all_ids = load_matrix(matrix)
        assert cells == {}
        assert all_ids == set()

    def test_handles_missing_depth(self, tmp_path):
        """load_matrix handles capability with missing depth levels."""
        matrix = tmp_path / "matrix.yml"
        matrix.write_text(yaml.dump({
            "capabilities": {
                "partial": {
                    "depth_1": [{"id": "P-001", "action": "A", "expected": "B"}],
                    # depth_2 and depth_3 missing
                },
            },
        }))
        cells, all_ids = load_matrix(matrix)
        assert cells["partial"]["depth_1"] == ["P-001"]
        assert cells["partial"]["depth_2"] == []
        assert cells["partial"]["depth_3"] == []
        assert all_ids == {"P-001"}

    def test_handles_none_capabilities(self, tmp_path):
        """load_matrix handles capabilities: null."""
        matrix = tmp_path / "matrix.yml"
        matrix.write_text("capabilities:\n")
        cells, all_ids = load_matrix(matrix)
        assert cells == {}
        assert all_ids == set()

    def test_handles_entries_without_id(self, tmp_path):
        """load_matrix skips entries that have no id field."""
        matrix = tmp_path / "matrix.yml"
        matrix.write_text(yaml.dump({
            "capabilities": {
                "cap": {
                    "depth_1": [
                        {"id": "C-001", "action": "A", "expected": "B"},
                        {"action": "No ID", "expected": "Skip me"},
                    ],
                },
            },
        }))
        cells, all_ids = load_matrix(matrix)
        assert cells["cap"]["depth_1"] == ["C-001"]
        assert all_ids == {"C-001"}

    def test_loads_default_path(self):
        """load_matrix with no path loads the project matrix."""
        cells, all_ids = load_matrix()
        assert len(all_ids) > 0
        assert any("DL-" in i for i in all_ids)


# ── scan_test_files ─────────────────────────────────────────


class TestScanTestFiles:
    def test_finds_matrix_references(self):
        """scan_test_files finds Matrix: references in test files."""
        covered = scan_test_files()
        # We know test_generate.py has Matrix: DL-001 etc.
        assert "DL-001" in covered
        assert "PG-001" in covered

    def test_finds_multiple_ids_on_one_line(self, tmp_path, monkeypatch):
        """scan_test_files parses comma-separated IDs."""
        # Create a fake test directory structure
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        test_file = tests_dir / "test_fake.py"
        test_file.write_text(
            '# Matrix: AA-001, AA-002\n'
            'def test_something():\n'
            '    pass\n'
        )
        # Monkeypatch PROJECT_ROOT to use tmp_path
        monkeypatch.setattr(matrix_mod, "PROJECT_ROOT", tmp_path)
        covered = scan_test_files()
        assert "AA-001" in covered
        assert "AA-002" in covered


# ── report ──────────────────────────────────────────────────


class TestReport:
    def test_report_full_coverage(self, capsys):
        """report shows 100% when all cells are covered."""
        cells = {"cap1": {"depth_1": ["A-001", "A-002"], "depth_2": [], "depth_3": []}}
        covered = {"A-001", "A-002"}
        all_ids = {"A-001", "A-002"}
        pct = report(cells, covered, all_ids)
        assert pct == 100.0
        captured = capsys.readouterr()
        assert "100%" in captured.out
        assert "TOTAL" in captured.out

    def test_report_partial_coverage(self, capsys):
        """report shows correct percentage for partial coverage."""
        cells = {"cap1": {"depth_1": ["A-001", "A-002"], "depth_2": [], "depth_3": []}}
        covered = {"A-001"}
        all_ids = {"A-001", "A-002"}
        pct = report(cells, covered, all_ids)
        assert pct == 50.0
        captured = capsys.readouterr()
        assert "50%" in captured.out

    def test_report_zero_coverage(self, capsys):
        """report shows 0% when nothing is covered."""
        cells = {"cap1": {"depth_1": ["A-001"], "depth_2": [], "depth_3": []}}
        covered = set()
        all_ids = {"A-001"}
        pct = report(cells, covered, all_ids)
        assert pct == 0.0

    def test_report_unknown_refs(self, capsys):
        """report flags IDs found in tests but not in matrix."""
        cells = {"cap1": {"depth_1": ["A-001"], "depth_2": [], "depth_3": []}}
        covered = {"A-001", "UNKNOWN-99"}
        all_ids = {"A-001"}
        report(cells, covered, all_ids)
        captured = capsys.readouterr()
        assert "Unknown matrix references" in captured.out
        assert "UNKNOWN-99" in captured.out

    def test_report_empty_cells(self, capsys):
        """report handles empty cells gracefully."""
        cells = {}
        covered = set()
        all_ids = set()
        pct = report(cells, covered, all_ids)
        assert pct == 0

    def test_report_multiple_capabilities(self, capsys):
        """report shows per-capability breakdown."""
        cells = {
            "alpha": {"depth_1": ["A-001"], "depth_2": [], "depth_3": []},
            "beta": {"depth_1": ["B-001", "B-002"], "depth_2": [], "depth_3": []},
        }
        covered = {"A-001", "B-001"}
        all_ids = {"A-001", "B-001", "B-002"}
        pct = report(cells, covered, all_ids)
        captured = capsys.readouterr()
        assert "alpha" in captured.out
        assert "beta" in captured.out
        # Total: 2/3 covered = 67%
        assert abs(pct - 66.67) < 1


# ── main (CLI) ──────────────────────────────────────────────


class TestMain:
    def test_main_succeeds_with_default_threshold(self):
        """main() exits 0 with threshold=0 (default)."""
        # Just verify it doesn't crash with no args
        main(["--threshold", "0"])

    def test_main_fails_with_impossible_threshold(self):
        """main() exits 1 when threshold is higher than actual coverage."""
        with pytest.raises(SystemExit) as exc_info:
            main(["--threshold", "101"])
        assert exc_info.value.code == 1

    def test_main_custom_matrix(self, tmp_path):
        """main() accepts a custom matrix path."""
        matrix = tmp_path / "test_matrix.yml"
        matrix.write_text(yaml.dump({
            "capabilities": {
                "simple": {
                    "depth_1": [{"id": "S-001", "action": "A", "expected": "B"}],
                },
            },
        }))
        # Won't find any coverage → 0%, threshold 0 → OK
        main(["--matrix", str(matrix), "--threshold", "0"])

    def test_main_with_high_threshold_fails(self, tmp_path):
        """main() exits 1 when coverage is below threshold."""
        matrix = tmp_path / "test_matrix.yml"
        matrix.write_text(yaml.dump({
            "capabilities": {
                "simple": {
                    "depth_1": [{"id": "ZZZZ-001", "action": "A", "expected": "B"}],
                },
            },
        }))
        with pytest.raises(SystemExit) as exc_info:
            main(["--matrix", str(matrix), "--threshold", "100"])
        assert exc_info.value.code == 1


# ── molecule verify.yml scanning ────────────────────────


class TestMatrixMoleculeVerify:
    """Test scanning of molecule verify.yml files for Matrix: IDs."""

    def test_finds_matrix_ids_in_verify_yml(self, tmp_path, monkeypatch):
        """scan_test_files finds Matrix: references in molecule verify.yml."""
        # Create a fake project structure with a molecule verify.yml
        roles_dir = tmp_path / "roles" / "test_role" / "molecule" / "default"
        roles_dir.mkdir(parents=True)
        verify_yml = roles_dir / "verify.yml"
        verify_yml.write_text(
            "---\n"
            "# Matrix: MOL-001, MOL-002\n"
            "- name: Verify\n"
            "  hosts: all\n"
            "  tasks:\n"
            "    - name: Check service\n"
            "      # Matrix: MOL-003\n"
            "      ansible.builtin.command: systemctl status test\n",
        )
        # Also create a tests dir (even if empty)
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        monkeypatch.setattr(matrix_mod, "PROJECT_ROOT", tmp_path)
        covered = scan_test_files()
        assert "MOL-001" in covered
        assert "MOL-002" in covered
        assert "MOL-003" in covered

    def test_no_verify_files_returns_only_test_refs(self, tmp_path, monkeypatch):
        """scan_test_files works when no molecule verify.yml files exist."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        test_file = tests_dir / "test_example.py"
        test_file.write_text("# Matrix: EX-001\ndef test_one(): pass\n")

        monkeypatch.setattr(matrix_mod, "PROJECT_ROOT", tmp_path)
        covered = scan_test_files()
        assert "EX-001" in covered


# ── file read error ─────────────────────────────────────


class TestMatrixFileReadError:
    """Test with files that cause OSError on read."""

    def test_oserror_skips_file_gracefully(self, tmp_path, monkeypatch):
        """scan_test_files skips files that raise OSError on read."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        # Create a valid test file
        good_file = tests_dir / "test_good.py"
        good_file.write_text("# Matrix: GOOD-001\ndef test_ok(): pass\n")

        # Create a file that will cause a read error (a directory named *.py)
        # Instead, monkeypatch Path.read_text to fail for specific files
        original_read_text = Path.read_text

        def patched_read_text(self_path, *args, **kwargs):
            if self_path.name == "test_bad.py":
                raise OSError("Permission denied")
            return original_read_text(self_path, *args, **kwargs)

        bad_file = tests_dir / "test_bad.py"
        bad_file.write_text("# Matrix: BAD-001\ndef test_bad(): pass\n")

        monkeypatch.setattr(matrix_mod, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(Path, "read_text", patched_read_text)

        covered = scan_test_files()
        # Good file should be found, bad file should be skipped
        assert "GOOD-001" in covered
        assert "BAD-001" not in covered


# ── threshold pass ──────────────────────────────────────


class TestMatrixThresholdPass:
    """Test with coverage above threshold → exit 0."""

    def test_threshold_pass_with_full_coverage(self, tmp_path, monkeypatch):
        """main() exits 0 when coverage meets the threshold."""
        # Create a matrix with one cell
        matrix = tmp_path / "test_matrix.yml"
        matrix.write_text(yaml.dump({
            "capabilities": {
                "my_cap": {
                    "depth_1": [{"id": "MY-001", "action": "A", "expected": "B"}],
                },
            },
        }))

        # Create a test file that covers that cell
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        test_file = tests_dir / "test_cover.py"
        test_file.write_text("# Matrix: MY-001\ndef test_covered(): pass\n")

        monkeypatch.setattr(matrix_mod, "PROJECT_ROOT", tmp_path)

        # Should NOT raise SystemExit (exit 0)
        main(["--matrix", str(matrix), "--threshold", "100"])

    def test_threshold_pass_with_zero_threshold(self, tmp_path, monkeypatch):
        """main() exits 0 with threshold=0 even if nothing is covered."""
        matrix = tmp_path / "test_matrix.yml"
        matrix.write_text(yaml.dump({
            "capabilities": {
                "cap": {
                    "depth_1": [{"id": "ZZZ-001", "action": "A", "expected": "B"}],
                },
            },
        }))

        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        monkeypatch.setattr(matrix_mod, "PROJECT_ROOT", tmp_path)

        # threshold=0 should always pass
        main(["--matrix", str(matrix), "--threshold", "0"])

    def test_threshold_pass_partial_coverage(self, tmp_path, monkeypatch):
        """main() exits 0 when coverage exceeds a non-100% threshold."""
        matrix = tmp_path / "test_matrix.yml"
        matrix.write_text(yaml.dump({
            "capabilities": {
                "cap": {
                    "depth_1": [
                        {"id": "PC-001", "action": "A", "expected": "B"},
                        {"id": "PC-002", "action": "C", "expected": "D"},
                    ],
                },
            },
        }))

        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        test_file = tests_dir / "test_partial.py"
        test_file.write_text("# Matrix: PC-001\ndef test_one(): pass\n")

        monkeypatch.setattr(matrix_mod, "PROJECT_ROOT", tmp_path)

        # 50% coverage, threshold 40% → should pass
        main(["--matrix", str(matrix), "--threshold", "40"])


# ── MATRIX_REF_RE regex ────────────────────────────────


MATRIX_REF_RE = matrix_mod.MATRIX_REF_RE


class TestMatrixRefRegex:
    """Test the MATRIX_REF_RE regex pattern directly."""

    def test_simple_match(self):
        """Regex matches a simple # Matrix: XX-001 pattern."""
        m = MATRIX_REF_RE.search("# Matrix: DL-001")
        assert m is not None
        assert m.group(1) == "DL-001"

    def test_comma_separated_ids(self):
        """Regex captures comma-separated IDs as a single group."""
        m = MATRIX_REF_RE.search("# Matrix: DL-001, DL-002, DL-003")
        assert m is not None
        assert m.group(1) == "DL-001, DL-002, DL-003"

    def test_extra_spaces_after_hash(self):
        """Regex tolerates extra spaces between # and Matrix."""
        m = MATRIX_REF_RE.search("#   Matrix: GP-005")
        assert m is not None
        assert m.group(1) == "GP-005"

    def test_no_space_after_hash(self):
        """Regex matches when there is no space after #."""
        m = MATRIX_REF_RE.search("#Matrix: NP-001")
        assert m is not None
        assert m.group(1) == "NP-001"

    def test_extra_spaces_after_colon(self):
        """Regex tolerates extra spaces after the colon."""
        m = MATRIX_REF_RE.search("# Matrix:   VM-001")
        assert m is not None
        assert m.group(1).strip() == "VM-001"

    def test_no_match_without_hash(self):
        """Regex does not match without the # prefix."""
        m = MATRIX_REF_RE.search("Matrix: DL-001")
        assert m is None

    def test_no_match_on_random_text(self):
        """Regex does not match random text."""
        m = MATRIX_REF_RE.search("some random text without matrix ref")
        assert m is None

    def test_id_with_underscores(self):
        """Regex matches IDs containing underscores."""
        m = MATRIX_REF_RE.search("# Matrix: MY_CAP-001")
        assert m is not None
        assert m.group(1) == "MY_CAP-001"

    def test_id_with_numbers_only_suffix(self):
        """Regex matches IDs like AB-123."""
        m = MATRIX_REF_RE.search("# Matrix: AB-123")
        assert m is not None
        assert m.group(1) == "AB-123"

    def test_multiple_matches_in_text(self):
        """finditer returns all Matrix: references in multi-line text."""
        text = "# Matrix: AA-001\nsome code\n# Matrix: BB-002\n"
        matches = list(MATRIX_REF_RE.finditer(text))
        assert len(matches) == 2
        assert matches[0].group(1) == "AA-001"
        assert matches[1].group(1) == "BB-002"

    def test_inline_comment_match(self):
        """Regex matches Matrix: ref in an inline comment."""
        m = MATRIX_REF_RE.search("    # Matrix: PP-001")
        assert m is not None
        assert m.group(1) == "PP-001"

    def test_comma_without_spaces(self):
        """Regex matches comma-separated IDs without spaces."""
        m = MATRIX_REF_RE.search("# Matrix: X-001,X-002")
        assert m is not None
        assert m.group(1) == "X-001,X-002"

    def test_depth_2_id(self):
        """Regex matches depth-2 IDs like DL-2-001."""
        m = MATRIX_REF_RE.search("# Matrix: DL-2-001")
        assert m is not None
        assert m.group(1) == "DL-2-001"

    def test_depth_3_id(self):
        """Regex matches depth-3 IDs like GP-3-001."""
        m = MATRIX_REF_RE.search("# Matrix: GP-3-001")
        assert m is not None
        assert m.group(1) == "GP-3-001"


# ── load_matrix edge cases ──────────────────────────────


class TestLoadMatrixEdgeCases:
    """Additional edge cases for load_matrix."""

    def test_multiple_capabilities(self, tmp_path):
        """load_matrix handles many capabilities with all depth levels."""
        matrix = tmp_path / "matrix.yml"
        matrix.write_text(yaml.dump({
            "capabilities": {
                "cap_a": {
                    "depth_1": [{"id": "A-001", "action": "A1", "expected": "E1"}],
                    "depth_2": [{"id": "A-2-001", "action": "A2", "expected": "E2"}],
                    "depth_3": [{"id": "A-3-001", "action": "A3", "expected": "E3"}],
                },
                "cap_b": {
                    "depth_1": [{"id": "B-001", "action": "B1", "expected": "E1"}],
                    "depth_2": [],
                    "depth_3": [],
                },
                "cap_c": {
                    "depth_1": [],
                    "depth_2": [{"id": "C-2-001", "action": "C2", "expected": "E2"}],
                    "depth_3": [],
                },
            },
        }))
        cells, all_ids = load_matrix(matrix)
        assert len(cells) == 3
        assert all_ids == {"A-001", "A-2-001", "A-3-001", "B-001", "C-2-001"}

    def test_empty_depth_list(self, tmp_path):
        """load_matrix handles empty depth list correctly."""
        matrix = tmp_path / "matrix.yml"
        matrix.write_text(yaml.dump({
            "capabilities": {
                "cap": {
                    "depth_1": [],
                    "depth_2": [],
                    "depth_3": [],
                },
            },
        }))
        cells, all_ids = load_matrix(matrix)
        assert cells["cap"]["depth_1"] == []
        assert cells["cap"]["depth_2"] == []
        assert cells["cap"]["depth_3"] == []
        assert all_ids == set()

    def test_null_depth_value(self, tmp_path):
        """load_matrix handles depth: null (None) gracefully."""
        matrix = tmp_path / "matrix.yml"
        matrix.write_text(
            "capabilities:\n"
            "  cap:\n"
            "    depth_1:\n"
            "    depth_2:\n"
            "    depth_3:\n"
        )
        cells, all_ids = load_matrix(matrix)
        assert cells["cap"]["depth_1"] == []
        assert cells["cap"]["depth_2"] == []
        assert cells["cap"]["depth_3"] == []
        assert all_ids == set()

    def test_all_entries_without_id(self, tmp_path):
        """load_matrix returns empty list when all entries lack an id."""
        matrix = tmp_path / "matrix.yml"
        matrix.write_text(yaml.dump({
            "capabilities": {
                "cap": {
                    "depth_1": [
                        {"action": "A", "expected": "B"},
                        {"action": "C", "expected": "D"},
                    ],
                },
            },
        }))
        cells, all_ids = load_matrix(matrix)
        assert cells["cap"]["depth_1"] == []
        assert all_ids == set()

    def test_entries_with_empty_string_id(self, tmp_path):
        """load_matrix skips entries with empty string as id."""
        matrix = tmp_path / "matrix.yml"
        matrix.write_text(yaml.dump({
            "capabilities": {
                "cap": {
                    "depth_1": [
                        {"id": "", "action": "A", "expected": "B"},
                        {"id": "OK-001", "action": "C", "expected": "D"},
                    ],
                },
            },
        }))
        cells, all_ids = load_matrix(matrix)
        # empty string is falsy, so it should be skipped
        assert "OK-001" in all_ids
        assert "" not in all_ids

    def test_many_entries_in_single_depth(self, tmp_path):
        """load_matrix handles a large number of entries in one depth."""
        entries = [{"id": f"BIG-{i:03d}", "action": f"Act {i}", "expected": f"Exp {i}"}
                   for i in range(50)]
        matrix = tmp_path / "matrix.yml"
        matrix.write_text(yaml.dump({
            "capabilities": {
                "big_cap": {
                    "depth_1": entries,
                },
            },
        }))
        cells, all_ids = load_matrix(matrix)
        assert len(cells["big_cap"]["depth_1"]) == 50
        assert len(all_ids) == 50
        assert "BIG-000" in all_ids
        assert "BIG-049" in all_ids

    def test_extra_fields_in_entry_ignored(self, tmp_path):
        """load_matrix ignores extra fields in entries (e.g., deterministic)."""
        matrix = tmp_path / "matrix.yml"
        matrix.write_text(yaml.dump({
            "capabilities": {
                "cap": {
                    "depth_1": [
                        {"id": "EF-001", "action": "A", "expected": "B",
                         "deterministic": True, "notes": "extra"},
                    ],
                },
            },
        }))
        cells, all_ids = load_matrix(matrix)
        assert cells["cap"]["depth_1"] == ["EF-001"]
        assert all_ids == {"EF-001"}

    def test_capability_with_extra_keys_ignored(self, tmp_path):
        """load_matrix only processes depth_1/2/3, ignoring description etc."""
        matrix = tmp_path / "matrix.yml"
        matrix.write_text(yaml.dump({
            "capabilities": {
                "cap": {
                    "description": "Some description",
                    "depth_1": [{"id": "EK-001", "action": "A", "expected": "B"}],
                },
            },
        }))
        cells, all_ids = load_matrix(matrix)
        assert "EK-001" in all_ids
        # Only depth_1, depth_2, depth_3 keys should be in the cells
        assert "depth_1" in cells["cap"]
        assert "depth_2" in cells["cap"]
        assert "depth_3" in cells["cap"]
        assert "description" not in cells["cap"]

    def test_duplicate_ids_across_capabilities(self, tmp_path):
        """load_matrix with duplicate IDs across capabilities: set deduplicates."""
        matrix = tmp_path / "matrix.yml"
        matrix.write_text(yaml.dump({
            "capabilities": {
                "cap_a": {
                    "depth_1": [{"id": "DUP-001", "action": "A", "expected": "B"}],
                },
                "cap_b": {
                    "depth_1": [{"id": "DUP-001", "action": "C", "expected": "D"}],
                },
            },
        }))
        cells, all_ids = load_matrix(matrix)
        # DUP-001 appears in both lists
        assert cells["cap_a"]["depth_1"] == ["DUP-001"]
        assert cells["cap_b"]["depth_1"] == ["DUP-001"]
        # But all_ids is a set, so only one entry
        assert all_ids == {"DUP-001"}

    def test_duplicate_ids_within_same_depth(self, tmp_path):
        """load_matrix preserves duplicate IDs in the list but deduplicates in the set."""
        matrix = tmp_path / "matrix.yml"
        matrix.write_text(yaml.dump({
            "capabilities": {
                "cap": {
                    "depth_1": [
                        {"id": "SAME-001", "action": "A", "expected": "B"},
                        {"id": "SAME-001", "action": "C", "expected": "D"},
                    ],
                },
            },
        }))
        cells, all_ids = load_matrix(matrix)
        # list has duplicates
        assert cells["cap"]["depth_1"] == ["SAME-001", "SAME-001"]
        # set does not
        assert all_ids == {"SAME-001"}

    def test_file_not_found_raises(self, tmp_path):
        """load_matrix raises FileNotFoundError for nonexistent path."""
        with pytest.raises(FileNotFoundError):
            load_matrix(tmp_path / "nonexistent.yml")

    def test_only_depth_3_populated(self, tmp_path):
        """load_matrix handles capability with only depth_3 populated."""
        matrix = tmp_path / "matrix.yml"
        matrix.write_text(yaml.dump({
            "capabilities": {
                "deep": {
                    "depth_3": [{"id": "D3-001", "action": "A", "expected": "B"}],
                },
            },
        }))
        cells, all_ids = load_matrix(matrix)
        assert cells["deep"]["depth_1"] == []
        assert cells["deep"]["depth_2"] == []
        assert cells["deep"]["depth_3"] == ["D3-001"]
        assert all_ids == {"D3-001"}

    def test_id_values_are_strings(self, tmp_path):
        """load_matrix handles numeric id values (YAML might parse as int)."""
        matrix = tmp_path / "matrix.yml"
        # Use raw YAML to ensure id is parsed as integer
        matrix.write_text(
            "capabilities:\n"
            "  cap:\n"
            "    depth_1:\n"
            "      - id: 123\n"
            "        action: A\n"
            "        expected: B\n"
        )
        cells, all_ids = load_matrix(matrix)
        # The id is truthy (123), so it gets added
        assert 123 in all_ids or "123" in all_ids

    def test_real_matrix_has_expected_capabilities(self):
        """The real behavior_matrix.yml contains expected capability keys."""
        cells, all_ids = load_matrix()
        expected_caps = [
            "domain_lifecycle", "psot_generator", "gpu_policy",
            "network_policies", "vm_support", "privileged_policy",
            "firewall_modes", "infra_directory", "ephemeral_lifecycle",
            "image_management", "ai_access_policy",
        ]
        for cap in expected_caps:
            assert cap in cells, f"Missing capability: {cap}"

    def test_real_matrix_all_ids_have_consistent_format(self):
        """Real matrix IDs follow the XX-NNN or XX-N-NNN pattern."""
        import re
        id_pattern = re.compile(r"^[A-Z]{2}-(\d+-)?(\d+)$")
        _, all_ids = load_matrix()
        for cell_id in all_ids:
            # All IDs should be strings
            assert isinstance(cell_id, str), f"ID {cell_id} is not a string"
            assert id_pattern.match(cell_id), f"ID {cell_id} does not match pattern"

    def test_real_matrix_no_empty_capabilities(self):
        """Real matrix: every capability has at least one ID."""
        cells, _ = load_matrix()
        for cap_name, depths in cells.items():
            total_ids = sum(len(ids) for ids in depths.values())
            assert total_ids > 0, f"Capability {cap_name} has no IDs"


# ── scan_test_files edge cases ──────────────────────────


class TestScanTestFilesEdgeCases:
    """Additional edge cases for scan_test_files."""

    def test_empty_test_directory(self, tmp_path, monkeypatch):
        """scan_test_files returns empty set when no test files exist."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        monkeypatch.setattr(matrix_mod, "PROJECT_ROOT", tmp_path)
        covered = scan_test_files()
        assert covered == set()

    def test_test_file_without_matrix_refs(self, tmp_path, monkeypatch):
        """scan_test_files returns empty set for files without Matrix: refs."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        test_file = tests_dir / "test_no_matrix.py"
        test_file.write_text(
            "def test_something():\n"
            "    assert True\n"
        )
        monkeypatch.setattr(matrix_mod, "PROJECT_ROOT", tmp_path)
        covered = scan_test_files()
        assert covered == set()

    def test_multiple_test_files(self, tmp_path, monkeypatch):
        """scan_test_files aggregates IDs from multiple test files."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_a.py").write_text("# Matrix: FA-001\ndef test_a(): pass\n")
        (tests_dir / "test_b.py").write_text("# Matrix: FB-001, FB-002\ndef test_b(): pass\n")
        (tests_dir / "test_c.py").write_text("# Matrix: FC-001\ndef test_c(): pass\n")
        monkeypatch.setattr(matrix_mod, "PROJECT_ROOT", tmp_path)
        covered = scan_test_files()
        assert covered == {"FA-001", "FB-001", "FB-002", "FC-001"}

    def test_same_id_in_multiple_files(self, tmp_path, monkeypatch):
        """scan_test_files deduplicates IDs found in multiple files."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_x.py").write_text("# Matrix: SHARED-001\ndef test_x(): pass\n")
        (tests_dir / "test_y.py").write_text("# Matrix: SHARED-001\ndef test_y(): pass\n")
        monkeypatch.setattr(matrix_mod, "PROJECT_ROOT", tmp_path)
        covered = scan_test_files()
        assert covered == {"SHARED-001"}

    def test_matrix_ref_in_docstring(self, tmp_path, monkeypatch):
        """scan_test_files finds Matrix: references in docstrings."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        test_file = tests_dir / "test_doc.py"
        test_file.write_text(
            'def test_something():\n'
            '    """Test for # Matrix: DOC-001"""\n'
            '    pass\n'
        )
        monkeypatch.setattr(matrix_mod, "PROJECT_ROOT", tmp_path)
        covered = scan_test_files()
        assert "DOC-001" in covered

    def test_non_py_files_in_tests_ignored(self, tmp_path, monkeypatch):
        """scan_test_files only scans *.py files in tests/."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        # This .txt file should not be scanned
        (tests_dir / "notes.txt").write_text("# Matrix: TXT-001\n")
        # This .yml file should not match the tests/*.py glob
        (tests_dir / "data.yml").write_text("# Matrix: YML-001\n")
        monkeypatch.setattr(matrix_mod, "PROJECT_ROOT", tmp_path)
        covered = scan_test_files()
        assert "TXT-001" not in covered
        assert "YML-001" not in covered

    def test_multiple_refs_on_separate_lines(self, tmp_path, monkeypatch):
        """scan_test_files finds references on separate lines in one file."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        test_file = tests_dir / "test_multi.py"
        test_file.write_text(
            "# Matrix: ML-001\n"
            "def test_a(): pass\n"
            "\n"
            "# Matrix: ML-002\n"
            "def test_b(): pass\n"
            "\n"
            "# Matrix: ML-003\n"
            "def test_c(): pass\n"
        )
        monkeypatch.setattr(matrix_mod, "PROJECT_ROOT", tmp_path)
        covered = scan_test_files()
        assert covered == {"ML-001", "ML-002", "ML-003"}

    def test_molecule_verify_multiple_roles(self, tmp_path, monkeypatch):
        """scan_test_files finds refs in multiple molecule verify.yml files."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        for role_name, mol_id in [("role_a", "MRA-001"), ("role_b", "MRB-001")]:
            mol_dir = tmp_path / "roles" / role_name / "molecule" / "default"
            mol_dir.mkdir(parents=True)
            (mol_dir / "verify.yml").write_text(f"# Matrix: {mol_id}\n- name: Verify\n")

        monkeypatch.setattr(matrix_mod, "PROJECT_ROOT", tmp_path)
        covered = scan_test_files()
        assert "MRA-001" in covered
        assert "MRB-001" in covered

    def test_molecule_verify_non_default_scenario(self, tmp_path, monkeypatch):
        """scan_test_files finds refs in non-default molecule scenarios."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        # Create a molecule scenario other than "default"
        mol_dir = tmp_path / "roles" / "my_role" / "molecule" / "custom_scenario"
        mol_dir.mkdir(parents=True)
        (mol_dir / "verify.yml").write_text("# Matrix: CS-001\n- name: Verify custom\n")

        monkeypatch.setattr(matrix_mod, "PROJECT_ROOT", tmp_path)
        covered = scan_test_files()
        assert "CS-001" in covered

    def test_no_tests_dir_no_roles_dir(self, tmp_path, monkeypatch):
        """scan_test_files handles missing tests/ and roles/ dirs gracefully."""
        # tmp_path has neither tests/ nor roles/
        monkeypatch.setattr(matrix_mod, "PROJECT_ROOT", tmp_path)
        covered = scan_test_files()
        assert covered == set()

    def test_comma_separated_with_extra_spaces(self, tmp_path, monkeypatch):
        """scan_test_files handles comma-separated IDs with varying spaces."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        test_file = tests_dir / "test_spaces.py"
        test_file.write_text("# Matrix: SP-001,  SP-002,SP-003,   SP-004\n")
        monkeypatch.setattr(matrix_mod, "PROJECT_ROOT", tmp_path)
        covered = scan_test_files()
        assert "SP-001" in covered
        assert "SP-002" in covered
        assert "SP-003" in covered
        assert "SP-004" in covered

    def test_scan_ignores_non_test_py_naming(self, tmp_path, monkeypatch):
        """scan_test_files matches *.py glob, including non-test_ prefixed files."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        # conftest.py is *.py but not test_*
        (tests_dir / "conftest.py").write_text("# Matrix: CF-001\n")
        # helper.py is also *.py
        (tests_dir / "helper.py").write_text("# Matrix: HLP-001\n")
        monkeypatch.setattr(matrix_mod, "PROJECT_ROOT", tmp_path)
        covered = scan_test_files()
        assert "CF-001" in covered
        assert "HLP-001" in covered


# ── report formatting details ──────────────────────────


class TestReportFormatting:
    """Test report output formatting details."""

    def test_report_header_contains_columns(self, capsys):
        """report output has the expected column headers."""
        cells = {"cap": {"depth_1": ["X-001"], "depth_2": [], "depth_3": []}}
        report(cells, set(), {"X-001"})
        captured = capsys.readouterr()
        assert "Capability" in captured.out
        assert "Depth" in captured.out
        assert "Total" in captured.out
        assert "Covered" in captured.out
        assert "%" in captured.out

    def test_report_contains_separator_lines(self, capsys):
        """report output has dash separator lines."""
        cells = {"cap": {"depth_1": ["X-001"], "depth_2": [], "depth_3": []}}
        report(cells, set(), {"X-001"})
        captured = capsys.readouterr()
        assert "-" * 60 in captured.out

    def test_report_depth_label_formatting(self, capsys):
        """report formats depth_1 as 'depth 1' (replaces underscore with space)."""
        cells = {
            "cap": {
                "depth_1": ["D1-001"],
                "depth_2": ["D2-001"],
                "depth_3": ["D3-001"],
            },
        }
        report(cells, set(), {"D1-001", "D2-001", "D3-001"})
        captured = capsys.readouterr()
        assert "depth 1" in captured.out
        assert "depth 2" in captured.out
        assert "depth 3" in captured.out

    def test_report_skips_empty_depth_rows(self, capsys):
        """report does not print rows for depth levels with no IDs."""
        cells = {"cap": {"depth_1": ["X-001"], "depth_2": [], "depth_3": []}}
        report(cells, set(), {"X-001"})
        captured = capsys.readouterr()
        # depth 2 and depth 3 are empty, should not appear
        assert "depth 2" not in captured.out
        assert "depth 3" not in captured.out

    def test_report_no_unknown_refs_section_when_none(self, capsys):
        """report omits unknown refs section when all refs are valid."""
        cells = {"cap": {"depth_1": ["X-001"], "depth_2": [], "depth_3": []}}
        report(cells, {"X-001"}, {"X-001"})
        captured = capsys.readouterr()
        assert "Unknown matrix references" not in captured.out

    def test_report_multiple_unknown_refs_sorted(self, capsys):
        """report lists multiple unknown refs in sorted order."""
        cells = {"cap": {"depth_1": ["X-001"], "depth_2": [], "depth_3": []}}
        covered = {"X-001", "ZZZ-003", "AAA-001", "MMM-002"}
        all_ids = {"X-001"}
        report(cells, covered, all_ids)
        captured = capsys.readouterr()
        assert "Unknown matrix references" in captured.out
        # Check sorted order
        out = captured.out
        aaa_pos = out.index("AAA-001")
        mmm_pos = out.index("MMM-002")
        zzz_pos = out.index("ZZZ-003")
        assert aaa_pos < mmm_pos < zzz_pos

    def test_report_capabilities_sorted(self, capsys):
        """report prints capabilities in sorted order."""
        cells = {
            "zebra": {"depth_1": ["Z-001"], "depth_2": [], "depth_3": []},
            "alpha": {"depth_1": ["A-001"], "depth_2": [], "depth_3": []},
            "middle": {"depth_1": ["M-001"], "depth_2": [], "depth_3": []},
        }
        covered = set()
        all_ids = {"Z-001", "A-001", "M-001"}
        report(cells, covered, all_ids)
        captured = capsys.readouterr()
        alpha_pos = captured.out.index("alpha")
        middle_pos = captured.out.index("middle")
        zebra_pos = captured.out.index("zebra")
        assert alpha_pos < middle_pos < zebra_pos

    def test_report_total_row_always_present(self, capsys):
        """report always prints a TOTAL row, even with zero cells."""
        cells = {}
        report(cells, set(), set())
        captured = capsys.readouterr()
        assert "TOTAL" in captured.out

    def test_report_returns_float(self, capsys):
        """report returns a float percentage."""
        cells = {"cap": {"depth_1": ["X-001", "X-002"], "depth_2": [], "depth_3": []}}
        pct = report(cells, {"X-001"}, {"X-001", "X-002"})
        assert isinstance(pct, (int, float))
        assert pct == 50.0

    def test_report_exact_percentage_1_of_3(self, capsys):
        """report calculates 1/3 coverage correctly (33.33...)."""
        cells = {"cap": {"depth_1": ["X-001", "X-002", "X-003"], "depth_2": [], "depth_3": []}}
        pct = report(cells, {"X-001"}, {"X-001", "X-002", "X-003"})
        assert abs(pct - 33.333) < 1

    def test_report_coverage_across_depths(self, capsys):
        """report counts IDs across all depth levels for total."""
        cells = {
            "cap": {
                "depth_1": ["D1-001"],
                "depth_2": ["D2-001"],
                "depth_3": ["D3-001"],
            },
        }
        covered = {"D1-001", "D3-001"}
        all_ids = {"D1-001", "D2-001", "D3-001"}
        pct = report(cells, covered, all_ids)
        # 2 out of 3 = 66.67%
        assert abs(pct - 66.67) < 1

    def test_report_coverage_only_counts_known_ids(self, capsys):
        """report percentage only counts IDs from the matrix, not unknown refs."""
        cells = {"cap": {"depth_1": ["X-001", "X-002"], "depth_2": [], "depth_3": []}}
        # covered includes an unknown ref, but percentage should be 1/2 = 50%
        covered = {"X-001", "PHANTOM-999"}
        all_ids = {"X-001", "X-002"}
        pct = report(cells, covered, all_ids)
        assert pct == 50.0

    def test_report_single_cell_fully_covered(self, capsys):
        """report handles single cell with 100% coverage."""
        cells = {"single": {"depth_1": ["ONLY-001"], "depth_2": [], "depth_3": []}}
        pct = report(cells, {"ONLY-001"}, {"ONLY-001"})
        assert pct == 100.0
        captured = capsys.readouterr()
        assert "100%" in captured.out

    def test_report_many_capabilities_count(self, capsys):
        """report handles many capabilities with mixed coverage."""
        cells = {}
        all_ids = set()
        covered = set()
        for i in range(10):
            cap_name = f"cap_{i:02d}"
            ids = [f"C{i:02d}-{j:03d}" for j in range(5)]
            cells[cap_name] = {"depth_1": ids, "depth_2": [], "depth_3": []}
            all_ids.update(ids)
            if i % 2 == 0:  # Cover every other capability
                covered.update(ids)
        pct = report(cells, covered, all_ids)
        # 5 caps fully covered out of 10 = 50%
        assert pct == 50.0


# ── main CLI additional tests ──────────────────────────


class TestMainAdditional:
    """Additional tests for the main CLI function."""

    def test_main_exact_threshold_match(self, tmp_path, monkeypatch):
        """main() exits 0 when coverage exactly equals threshold."""
        matrix = tmp_path / "test_matrix.yml"
        matrix.write_text(yaml.dump({
            "capabilities": {
                "cap": {
                    "depth_1": [
                        {"id": "ET-001", "action": "A", "expected": "B"},
                        {"id": "ET-002", "action": "C", "expected": "D"},
                    ],
                },
            },
        }))
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_et.py").write_text("# Matrix: ET-001\ndef test(): pass\n")
        monkeypatch.setattr(matrix_mod, "PROJECT_ROOT", tmp_path)
        # 50% coverage, threshold 50% → should pass (>= not >)
        main(["--matrix", str(matrix), "--threshold", "50"])

    def test_main_threshold_slightly_above_coverage_fails(self, tmp_path, monkeypatch):
        """main() exits 1 when threshold is slightly above coverage."""
        matrix = tmp_path / "test_matrix.yml"
        matrix.write_text(yaml.dump({
            "capabilities": {
                "cap": {
                    "depth_1": [
                        {"id": "SA-001", "action": "A", "expected": "B"},
                        {"id": "SA-002", "action": "C", "expected": "D"},
                    ],
                },
            },
        }))
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_sa.py").write_text("# Matrix: SA-001\ndef test(): pass\n")
        monkeypatch.setattr(matrix_mod, "PROJECT_ROOT", tmp_path)
        # 50% coverage, threshold 51% → should fail
        with pytest.raises(SystemExit) as exc_info:
            main(["--matrix", str(matrix), "--threshold", "51"])
        assert exc_info.value.code == 1

    def test_main_output_contains_ok_message(self, tmp_path, monkeypatch, capsys):
        """main() prints OK message when coverage meets threshold."""
        matrix = tmp_path / "test_matrix.yml"
        matrix.write_text(yaml.dump({
            "capabilities": {
                "cap": {
                    "depth_1": [{"id": "OK-001", "action": "A", "expected": "B"}],
                },
            },
        }))
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_ok.py").write_text("# Matrix: OK-001\ndef test(): pass\n")
        monkeypatch.setattr(matrix_mod, "PROJECT_ROOT", tmp_path)
        main(["--matrix", str(matrix), "--threshold", "0"])
        captured = capsys.readouterr()
        assert "OK:" in captured.out

    def test_main_output_contains_fail_message(self, tmp_path, monkeypatch, capsys):
        """main() prints FAIL message when coverage is below threshold."""
        matrix = tmp_path / "test_matrix.yml"
        matrix.write_text(yaml.dump({
            "capabilities": {
                "cap": {
                    "depth_1": [{"id": "FAIL-001", "action": "A", "expected": "B"}],
                },
            },
        }))
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        monkeypatch.setattr(matrix_mod, "PROJECT_ROOT", tmp_path)
        with pytest.raises(SystemExit):
            main(["--matrix", str(matrix), "--threshold", "100"])
        captured = capsys.readouterr()
        assert "FAIL:" in captured.out

    def test_main_no_args_uses_defaults(self, capsys):
        """main() with no arguments uses default matrix and threshold 0."""
        main([])
        captured = capsys.readouterr()
        assert "OK:" in captured.out

    def test_main_empty_matrix(self, tmp_path, monkeypatch, capsys):
        """main() handles an empty matrix (0 IDs) gracefully."""
        matrix = tmp_path / "test_matrix.yml"
        matrix.write_text(yaml.dump({"capabilities": {}}))
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        monkeypatch.setattr(matrix_mod, "PROJECT_ROOT", tmp_path)
        # 0 out of 0 → 0%, threshold 0 → OK
        main(["--matrix", str(matrix), "--threshold", "0"])
        captured = capsys.readouterr()
        assert "TOTAL" in captured.out

    def test_main_multiple_capabilities_threshold_check(self, tmp_path, monkeypatch):
        """main() correctly aggregates coverage across multiple capabilities."""
        matrix = tmp_path / "test_matrix.yml"
        matrix.write_text(yaml.dump({
            "capabilities": {
                "alpha": {
                    "depth_1": [{"id": "AL-001", "action": "A", "expected": "B"}],
                },
                "beta": {
                    "depth_1": [
                        {"id": "BE-001", "action": "C", "expected": "D"},
                        {"id": "BE-002", "action": "E", "expected": "F"},
                    ],
                },
            },
        }))
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_mc.py").write_text(
            "# Matrix: AL-001\n"
            "# Matrix: BE-001\n"
            "def test(): pass\n"
        )
        monkeypatch.setattr(matrix_mod, "PROJECT_ROOT", tmp_path)
        # 2 out of 3 = 66.67%
        main(["--matrix", str(matrix), "--threshold", "66"])
        # Should pass since 66.67 >= 66

    def test_main_threshold_float_precision(self, tmp_path, monkeypatch):
        """main() handles float threshold values correctly."""
        matrix = tmp_path / "test_matrix.yml"
        matrix.write_text(yaml.dump({
            "capabilities": {
                "cap": {
                    "depth_1": [
                        {"id": "FP-001", "action": "A", "expected": "B"},
                        {"id": "FP-002", "action": "C", "expected": "D"},
                        {"id": "FP-003", "action": "E", "expected": "F"},
                    ],
                },
            },
        }))
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_fp.py").write_text("# Matrix: FP-001\ndef test(): pass\n")
        monkeypatch.setattr(matrix_mod, "PROJECT_ROOT", tmp_path)
        # 1/3 = 33.33%, threshold 33.33 → should pass
        main(["--matrix", str(matrix), "--threshold", "33.33"])


# ── integration with real matrix ────────────────────────


class TestRealMatrixIntegration:
    """Integration tests using the actual behavior_matrix.yml."""

    def test_real_matrix_loads_without_error(self):
        """The real behavior_matrix.yml loads without any error."""
        cells, all_ids = load_matrix()
        assert isinstance(cells, dict)
        assert isinstance(all_ids, set)

    def test_real_matrix_has_minimum_id_count(self):
        """The real matrix has a substantial number of IDs (>100)."""
        _, all_ids = load_matrix()
        assert len(all_ids) >= 100

    def test_real_matrix_depth_1_populated(self):
        """Every capability in the real matrix has at least one depth_1 ID."""
        cells, _ = load_matrix()
        for cap_name, depths in cells.items():
            assert len(depths["depth_1"]) > 0, f"{cap_name} has empty depth_1"

    def test_real_scan_returns_set(self):
        """scan_test_files returns a set of strings."""
        covered = scan_test_files()
        assert isinstance(covered, set)
        for item in covered:
            assert isinstance(item, str)

    def test_real_report_produces_output(self, capsys):
        """Running report on real matrix produces meaningful output."""
        cells, all_ids = load_matrix()
        covered = scan_test_files()
        pct = report(cells, covered, all_ids)
        captured = capsys.readouterr()
        assert len(captured.out) > 100  # meaningful output
        assert "TOTAL" in captured.out
        assert isinstance(pct, (int, float))
        assert 0 <= pct <= 100

    def test_real_matrix_id_uniqueness_within_capability(self):
        """Within each capability, IDs should be unique (no duplicates in lists)."""
        cells, _ = load_matrix()
        for cap_name, depths in cells.items():
            for depth_name, ids in depths.items():
                assert len(ids) == len(set(ids)), (
                    f"Duplicate IDs in {cap_name}/{depth_name}: {ids}"
                )

    def test_real_matrix_id_uniqueness_global(self):
        """All IDs across the entire real matrix should be unique."""
        cells, all_ids = load_matrix()
        total_ids = []
        for cap_name, depths in cells.items():
            for depth_name, ids in depths.items():
                total_ids.extend(ids)
        assert len(total_ids) == len(set(total_ids)), "Global duplicate IDs found"

    def test_real_matrix_id_prefix_consistency(self):
        """IDs within a capability should share the same prefix."""
        cells, _ = load_matrix()
        # Known prefix mapping from the matrix
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
        for cap_name, expected_prefix in prefix_map.items():
            if cap_name in cells:
                for depth_name, ids in cells[cap_name].items():
                    for cell_id in ids:
                        assert cell_id.startswith(expected_prefix + "-"), (
                            f"ID {cell_id} in {cap_name} doesn't start with {expected_prefix}-"
                        )
