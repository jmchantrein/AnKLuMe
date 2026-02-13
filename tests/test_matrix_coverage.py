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
