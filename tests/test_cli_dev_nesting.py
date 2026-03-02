"""Tests for anklume dev nesting command — --behave flag."""

from unittest.mock import patch

import pytest

typer = pytest.importorskip("typer")
from typer.testing import CliRunner  # noqa: E402

from scripts.cli.dev import app  # noqa: E402

runner = CliRunner()


class TestNestingCommand:
    def test_help_shows_behave(self):
        result = runner.invoke(app, ["nesting", "--help"])
        assert result.exit_code == 0
        assert "--behave" in result.output

    @patch("scripts.cli.dev.run_script")
    def test_behave_passed_to_script(self, mock_run):
        result = runner.invoke(app, ["nesting", "--behave", "--dry-run"])
        assert result.exit_code == 0
        args = mock_run.call_args[0]
        assert "test-nesting.sh" in args[0]
        rest = list(args[1:])
        assert "--behave" in rest
        assert "--dry-run" in rest

    @patch("scripts.cli.dev.run_script")
    def test_full_and_behave(self, mock_run):
        result = runner.invoke(app, ["nesting", "--full", "--behave", "--dry-run"])
        assert result.exit_code == 0
        args = list(mock_run.call_args[0][1:])
        assert "--full" in args
        assert "--behave" in args

    @patch("scripts.cli.dev.run_script")
    def test_without_behave(self, mock_run):
        result = runner.invoke(app, ["nesting", "--dry-run"])
        assert result.exit_code == 0
        args = list(mock_run.call_args[0][1:])
        assert "--behave" not in args
