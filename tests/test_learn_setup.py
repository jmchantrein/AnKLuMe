"""Tests for scripts/learn-setup.sh — shell script structure validation."""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path("scripts/learn-setup.sh")


@pytest.mark.skipif(
    not SCRIPT.exists(),
    reason="learn-setup.sh not found",
)
class TestLearnSetupSyntax:
    def test_script_exists(self):
        assert SCRIPT.exists()

    def test_bash_syntax_check(self):
        result = subprocess.run(
            ["bash", "-n", str(SCRIPT)],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    @pytest.mark.skipif(
        not shutil.which("shellcheck"),
        reason="shellcheck not available",
    )
    def test_shellcheck(self):
        result = subprocess.run(
            ["shellcheck", "-S", "warning", str(SCRIPT)],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, f"shellcheck: {result.stdout}"

    def test_has_set_euo_pipefail(self):
        content = SCRIPT.read_text()
        assert "set -euo pipefail" in content

    def test_has_shebang(self):
        content = SCRIPT.read_text()
        assert content.startswith("#!/usr/bin/env bash")

    def test_has_teardown_function(self):
        content = SCRIPT.read_text()
        assert "do_teardown()" in content

    def test_has_setup_function(self):
        content = SCRIPT.read_text()
        assert "do_setup()" in content

    def test_has_check_incus_function(self):
        content = SCRIPT.read_text()
        assert "check_incus()" in content

    def test_has_project_exists_function(self):
        content = SCRIPT.read_text()
        assert "project_exists()" in content

    def test_has_container_exists_function(self):
        content = SCRIPT.read_text()
        assert "container_exists()" in content

    def test_has_container_running_function(self):
        content = SCRIPT.read_text()
        assert "container_running()" in content

    def test_uses_learn_project(self):
        content = SCRIPT.read_text()
        assert 'LEARN_PROJECT="learn"' in content

    def test_uses_correct_port(self):
        content = SCRIPT.read_text()
        assert "LEARN_PORT=8890" in content

    def test_uses_debian_image(self):
        content = SCRIPT.read_text()
        assert 'IMAGE="images:debian/13"' in content

    def test_creates_demo_instances(self):
        content = SCRIPT.read_text()
        assert "learn-web" in content
        assert "learn-db" in content

    def test_case_statement_handles_teardown(self):
        content = SCRIPT.read_text()
        assert "teardown)" in content

    def test_case_statement_handles_setup_default(self):
        content = SCRIPT.read_text()
        assert "setup|*)" in content

    def test_under_200_lines(self):
        lines = SCRIPT.read_text().splitlines()
        assert len(lines) <= 200, f"Script has {len(lines)} lines (max 200)"
