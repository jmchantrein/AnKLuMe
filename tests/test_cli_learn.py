"""Tests for scripts/cli/learn.py — learn CLI commands."""

from unittest.mock import patch

import pytest

typer = pytest.importorskip("typer")
from typer.testing import CliRunner  # noqa: E402

from scripts.cli.learn import app  # noqa: E402

runner = CliRunner()


class TestLearnStart:
    @patch("scripts.cli.learn.run_cmd")
    def test_start_default_args(self, mock_run):
        result = runner.invoke(app, ["start"])
        assert result.exit_code == 0
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert any("platform_server.py" in str(a) for a in args)
        assert "--port" in args
        assert "8890" in args
        assert "--host" in args
        assert "127.0.0.1" in args

    @patch("scripts.cli.learn.run_cmd")
    def test_start_custom_port(self, mock_run):
        result = runner.invoke(app, ["start", "--port", "9000"])
        assert result.exit_code == 0
        args = mock_run.call_args[0][0]
        assert "9000" in args

    @patch("scripts.cli.learn.run_cmd")
    def test_start_custom_host(self, mock_run):
        result = runner.invoke(app, ["start", "--host", "0.0.0.0"])
        assert result.exit_code == 0
        args = mock_run.call_args[0][0]
        assert "0.0.0.0" in args


class TestLearnSetup:
    @patch("scripts.cli.learn.run_script")
    def test_setup_calls_script(self, mock_run):
        result = runner.invoke(app, ["setup"])
        assert result.exit_code == 0
        mock_run.assert_called_once_with("learn-setup.sh")


class TestLearnTeardown:
    @patch("scripts.cli.learn.run_script")
    def test_teardown_calls_script(self, mock_run):
        result = runner.invoke(app, ["teardown"])
        assert result.exit_code == 0
        mock_run.assert_called_once_with("learn-setup.sh", "teardown")


class TestAppStructure:
    def test_app_has_three_commands(self):
        # Typer app should have start, setup, teardown
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "start" in result.output
        assert "setup" in result.output
        assert "teardown" in result.output

    def test_app_name(self):
        assert app.info.name == "learn"

    def test_app_help_text(self):
        result = runner.invoke(app, ["--help"])
        assert "learning platform" in result.output.lower()
