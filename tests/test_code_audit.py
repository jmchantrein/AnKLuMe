"""Tests for scripts/code-audit.py — codebase audit report."""

import json
import sys
from pathlib import Path

import pytest

# Import the module under test
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import importlib

code_audit = importlib.import_module("code-audit")


@pytest.fixture()
def fake_project(tmp_path):
    """Create a minimal project structure for testing."""
    # Scripts
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "generate.py").write_text(
        "#!/usr/bin/env python3\n"
        "# Generator\n"
        "import sys\n"
        "\n"
        "def main():\n"
        "    pass\n"
        "\n"
        "def helper():\n"
        "    pass\n"
    )
    (scripts_dir / "snap.sh").write_text(
        "#!/usr/bin/env bash\n"
        "# Snapshot manager\n"
        "set -euo pipefail\n"
        'echo "hello"\n'
    )
    (scripts_dir / "untested.py").write_text(
        "# No test exists for this\n"
        "def orphan():\n"
        "    pass\n"
    )

    # Tests
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_generate.py").write_text(
        "import pytest\n"
        "\n"
        "def test_basic():\n"
        "    assert True\n"
        "\n"
        "def test_another():\n"
        "    assert True\n"
    )
    (tests_dir / "test_snap.py").write_text(
        "def test_snap():\n"
        "    pass\n"
    )

    # Roles
    roles_dir = tmp_path / "roles"
    (roles_dir / "base_system" / "tasks").mkdir(parents=True)
    (roles_dir / "base_system" / "tasks" / "main.yml").write_text(
        "---\n"
        "- name: Install packages\n"
        "  apt:\n"
        "    name: vim\n"
    )
    (roles_dir / "incus_network" / "tasks").mkdir(parents=True)
    (roles_dir / "incus_network" / "tasks" / "main.yml").write_text(
        "---\n" + "- name: Task\n  debug: msg=ok\n" * 120  # Large role (241 lines)
    )

    # Top-level YAML
    (tmp_path / "site.yml").write_text("---\n- hosts: all\n  roles: []\n")

    # Fake code-analysis.sh
    (scripts_dir / "code-analysis.sh").write_text(
        "#!/usr/bin/env bash\n"
        'echo "=== Dead Code Detection ==="\n'
        'echo "No dead code found."\n'
    )
    (scripts_dir / "code-analysis.sh").chmod(0o755)

    return tmp_path


class TestCollectFileMetrics:
    def test_counts_python_impl(self, fake_project):
        categories = code_audit.collect_file_metrics(fake_project)
        assert categories["python_impl"]["lines"] > 0
        names = [e["path"] for e in categories["python_impl"]["files"]]
        assert any("generate.py" in n for n in names)

    def test_counts_python_tests(self, fake_project):
        categories = code_audit.collect_file_metrics(fake_project)
        assert categories["python_test"]["lines"] > 0
        names = [e["path"] for e in categories["python_test"]["files"]]
        assert any("test_generate.py" in n for n in names)

    def test_counts_shell(self, fake_project):
        categories = code_audit.collect_file_metrics(fake_project)
        assert categories["shell"]["lines"] > 0

    def test_counts_roles(self, fake_project):
        categories = code_audit.collect_file_metrics(fake_project)
        assert categories["yaml_roles"]["lines"] > 0

    def test_counts_yaml_config(self, fake_project):
        categories = code_audit.collect_file_metrics(fake_project)
        assert categories["yaml_config"]["lines"] > 0


class TestComputeTestRatios:
    def test_ratios_with_matching_tests(self, fake_project):
        categories = code_audit.collect_file_metrics(fake_project)
        ratios = code_audit.compute_test_ratios(categories)
        assert "generate" in ratios
        assert ratios["generate"]["impl_lines"] > 0
        assert ratios["generate"]["test_lines"] > 0
        assert ratios["generate"]["ratio"] > 0

    def test_module_without_test(self, fake_project):
        categories = code_audit.collect_file_metrics(fake_project)
        ratios = code_audit.compute_test_ratios(categories)
        assert "untested" in ratios
        assert ratios["untested"]["test_lines"] == 0
        assert ratios["untested"]["ratio"] == 0


class TestFindUntestedScripts:
    def test_finds_untested_python(self, fake_project):
        untested = code_audit.find_untested_scripts(fake_project)
        assert any("untested.py" in s for s in untested)

    def test_tested_scripts_excluded(self, fake_project):
        untested = code_audit.find_untested_scripts(fake_project)
        assert not any("generate.py" in s for s in untested)


class TestMeasureRoles:
    def test_roles_sorted_by_size(self, fake_project):
        roles = code_audit.measure_roles(fake_project)
        assert len(roles) == 2
        # incus_network is larger (80 repeated tasks)
        assert roles[0]["name"] == "incus_network"
        assert roles[0]["lines"] > roles[1]["lines"]

    def test_simplification_candidate_flagged(self, fake_project):
        roles = code_audit.measure_roles(fake_project)
        large_role = next(r for r in roles if r["name"] == "incus_network")
        assert large_role["simplification_candidate"] is True

    def test_small_role_not_flagged(self, fake_project):
        roles = code_audit.measure_roles(fake_project)
        small_role = next(r for r in roles if r["name"] == "base_system")
        assert small_role["simplification_candidate"] is False


class TestBuildReport:
    def test_report_structure(self, fake_project):
        report = code_audit.build_report(fake_project)
        assert "summary" in report
        assert "line_counts" in report
        assert "test_ratios" in report
        assert "untested_scripts" in report
        assert "roles" in report
        assert "dead_code" in report

    def test_summary_fields(self, fake_project):
        report = code_audit.build_report(fake_project)
        s = report["summary"]
        assert "total_implementation_lines" in s
        assert "total_test_lines" in s
        assert "total_role_lines" in s
        assert "overall_test_to_impl_ratio" in s
        assert s["total_implementation_lines"] > 0

    def test_json_serializable(self, fake_project):
        report = code_audit.build_report(fake_project)
        # Should not raise
        output = json.dumps(report, default=str)
        parsed = json.loads(output)
        assert parsed["summary"]["total_implementation_lines"] > 0


class TestPrintReport:
    def test_prints_without_error(self, fake_project, capsys):
        report = code_audit.build_report(fake_project)
        code_audit.print_report(report)
        captured = capsys.readouterr()
        assert "anklume Code Audit Report" in captured.out
        assert "SUMMARY" in captured.out
        assert "ROLES BY SIZE" in captured.out


class TestCountLines:
    def test_count_lines(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("# comment\ncode\n\nmore_code\n")
        assert code_audit.count_lines(f) == 2  # Only non-comment, non-empty

    def test_count_lines_raw(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("# comment\ncode\n\nmore_code\n")
        assert code_audit.count_lines_raw(f) == 4

    def test_missing_file(self, tmp_path):
        assert code_audit.count_lines(tmp_path / "nope.py") == 0
        assert code_audit.count_lines_raw(tmp_path / "nope.py") == 0
