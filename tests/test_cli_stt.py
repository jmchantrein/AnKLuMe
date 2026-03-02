"""Tests for the STT diagnostics CLI and script."""

import shutil
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestSTTScript:
    """Test stt-diag.sh script."""

    script_path = PROJECT_ROOT / "scripts" / "stt-diag.sh"

    def test_script_exists(self):
        assert self.script_path.is_file()

    def test_script_executable(self):
        assert self.script_path.stat().st_mode & 0o111

    def test_script_uses_bash(self):
        first_line = self.script_path.read_text().splitlines()[0]
        assert first_line == "#!/usr/bin/env bash"

    def test_script_has_set_euo_pipefail(self):
        text = self.script_path.read_text()
        assert "set -euo pipefail" in text

    def test_script_accepts_status_command(self):
        text = self.script_path.read_text()
        assert "cmd_status" in text

    def test_script_accepts_restart_command(self):
        text = self.script_path.read_text()
        assert "cmd_restart" in text

    def test_script_accepts_logs_command(self):
        text = self.script_path.read_text()
        assert "cmd_logs" in text

    def test_script_accepts_test_command(self):
        text = self.script_path.read_text()
        assert "cmd_test" in text

    def test_script_unloads_ollama_on_restart(self):
        """Restart should unload Ollama models before restarting Speaches."""
        text = self.script_path.read_text()
        assert "keep_alive" in text
        assert "Unloading" in text

    @pytest.mark.skipif(
        not shutil.which("shellcheck"),
        reason="shellcheck not installed",
    )
    def test_shellcheck(self):
        import subprocess
        result = subprocess.run(
            ["shellcheck", str(self.script_path)],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, result.stdout


class TestSTTCLI:
    """Test CLI commands."""

    def test_stt_commands_registered(self):
        from scripts.cli.stt import app

        callback_names = [
            cmd.callback.__name__ if cmd.callback else cmd.name
            for cmd in app.registered_commands
        ]
        assert "status" in callback_names
        assert "restart" in callback_names
        assert "logs" in callback_names
        assert "test" in callback_names

    def test_stt_app_name(self):
        from scripts.cli.stt import app

        assert app.info.name == "stt"

    def test_stt_app_in_main(self):
        """stt should be registered as a command group."""
        from scripts.cli import app

        group_names = []
        for grp in app.registered_groups:
            if grp.typer_instance and grp.typer_instance.info:
                group_names.append(grp.typer_instance.info.name)
        assert "stt" in group_names

    def test_logs_has_lines_option(self):
        """logs command should accept --lines option."""
        import inspect

        from scripts.cli.stt import logs
        sig = inspect.signature(logs)
        assert "lines" in sig.parameters
