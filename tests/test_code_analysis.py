"""Tests for scripts/code-analysis.sh — static code analysis."""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = PROJECT_ROOT / "scripts" / "code-analysis.sh"


def run_analysis(args, **kwargs):
    """Run code-analysis.sh with given args."""
    return subprocess.run(
        ["bash", str(SCRIPT)] + args,
        capture_output=True, text=True,
        cwd=str(PROJECT_ROOT),
        timeout=60,
        **kwargs,
    )


# ── dead-code subcommand ──────────────────────────────


@pytest.mark.skipif(not shutil.which("vulture"), reason="vulture not installed")
class TestDeadCode:
    def test_dead_code_runs(self):
        """dead-code subcommand runs and produces output."""
        result = run_analysis(["dead-code"])
        assert "Dead Code Detection" in result.stdout
        assert "Dead code analysis complete" in result.stdout

    def test_dead_code_vulture_section(self):
        """dead-code includes Python (vulture) section."""
        result = run_analysis(["dead-code"])
        assert "Python (vulture)" in result.stdout

    def test_dead_code_shell_section(self):
        """dead-code includes Shell (shellcheck) section."""
        result = run_analysis(["dead-code"])
        assert "Shell (shellcheck" in result.stdout


# ── call-graph subcommand ─────────────────────────────


class TestCallGraph:
    def test_call_graph_generates_dot(self, tmp_path):
        """call-graph produces a DOT file."""
        run_analysis(["call-graph", "--output-dir", str(tmp_path)])
        dot_file = tmp_path / "call-graph.dot"
        assert dot_file.exists()
        content = dot_file.read_text()
        assert "digraph" in content

    def test_call_graph_includes_functions(self, tmp_path):
        """call-graph DOT file contains function names from scripts/."""
        run_analysis(["call-graph", "--output-dir", str(tmp_path)])
        dot_file = tmp_path / "call-graph.dot"
        assert dot_file.exists()
        content = dot_file.read_text()
        # generate.py has well-known functions
        assert "generate" in content


# ── dep-graph subcommand ──────────────────────────────


class TestDepGraph:
    def test_dep_graph_handles_missing_graphviz(self):
        """dep-graph fails gracefully without graphviz."""
        result = run_analysis(["dep-graph"])
        combined = result.stdout + result.stderr
        # Either succeeds or warns about graphviz
        assert "Dependency Graph" in combined


# ── all subcommand ────────────────────────────────────


class TestAll:
    def test_all_runs_all_tools(self, tmp_path):
        """all subcommand runs dead-code, call-graph, and dep-graph."""
        result = run_analysis(["all", "--output-dir", str(tmp_path)])
        combined = result.stdout + result.stderr
        assert "Dead Code Detection" in combined
        assert "Call Graph Generation" in combined
        assert "Dependency Graph Generation" in combined


# ── argument handling ─────────────────────────────────


class TestArguments:
    def test_help_flag(self):
        """--help shows usage information."""
        result = run_analysis(["--help"])
        assert result.returncode == 0
        assert "Usage:" in result.stdout
        assert "dead-code" in result.stdout

    def test_no_args_error(self):
        """No arguments produces an error."""
        result = run_analysis([])
        assert result.returncode != 0
        assert "Subcommand required" in result.stderr

    def test_unknown_arg_error(self):
        """Unknown argument produces an error."""
        result = run_analysis(["--bogus"])
        assert result.returncode != 0
        assert "Unknown argument" in result.stderr

    def test_output_dir_option(self, tmp_path):
        """--output-dir creates reports in specified directory."""
        out = tmp_path / "custom-reports"
        run_analysis(["call-graph", "--output-dir", str(out)])
        assert out.exists()
        assert (out / "call-graph.dot").exists()


# ── shellcheck validation ────────────────────────────


class TestScriptQuality:
    @pytest.mark.skipif(not shutil.which("shellcheck"), reason="shellcheck not installed")
    def test_shellcheck_clean(self):
        """code-analysis.sh passes shellcheck."""
        result = subprocess.run(
            ["shellcheck", str(SCRIPT)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"shellcheck errors:\n{result.stdout}"

    def test_script_executable(self):
        """code-analysis.sh is executable."""
        mode = os.stat(SCRIPT).st_mode
        assert mode & stat.S_IXUSR, "Script should be executable"
