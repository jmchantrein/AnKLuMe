"""Tests for the learn-incus mode in _helpers.py."""

from unittest.mock import MagicMock, patch

import pytest

typer = pytest.importorskip("typer")


class TestIsLearnIncus:
    def test_off_when_file_missing(self, tmp_path, monkeypatch):
        import scripts.cli._helpers as helpers
        helpers._learn_incus_cache = None
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        assert helpers.is_learn_incus() is False

    def test_on_when_file_says_on(self, tmp_path, monkeypatch):
        import scripts.cli._helpers as helpers
        helpers._learn_incus_cache = None
        anklume_dir = tmp_path / ".anklume"
        anklume_dir.mkdir()
        (anklume_dir / "learn_incus").write_text("on\n")
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        assert helpers.is_learn_incus() is True

    def test_off_when_file_says_off(self, tmp_path, monkeypatch):
        import scripts.cli._helpers as helpers
        helpers._learn_incus_cache = None
        anklume_dir = tmp_path / ".anklume"
        anklume_dir.mkdir()
        (anklume_dir / "learn_incus").write_text("off\n")
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        assert helpers.is_learn_incus() is False

    def test_cache_is_used(self, tmp_path, monkeypatch):
        import scripts.cli._helpers as helpers
        helpers._learn_incus_cache = True
        assert helpers.is_learn_incus() is True
        helpers._learn_incus_cache = None  # reset


class TestRunCmdLearnMode:
    def test_incus_command_prints_when_learn_on(self, capsys, monkeypatch):
        import scripts.cli._helpers as helpers
        helpers._learn_incus_cache = True

        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result):
            helpers.run_cmd(["incus", "list", "--format", "json"], capture=True)

        helpers._learn_incus_cache = None  # reset
        captured = capsys.readouterr()
        # Rich renders [dim][incus]...[/dim] — capsys sees rendered text
        assert "incus" in captured.out
        assert "incus list" in captured.out

    def test_non_incus_command_no_print(self, capsys, monkeypatch):
        import scripts.cli._helpers as helpers
        helpers._learn_incus_cache = True

        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result):
            helpers.run_cmd(["python3", "--version"], capture=True)

        helpers._learn_incus_cache = None  # reset
        captured = capsys.readouterr()
        assert "[incus]" not in captured.out

    def test_incus_no_print_when_learn_off(self, capsys, monkeypatch):
        import scripts.cli._helpers as helpers
        helpers._learn_incus_cache = False

        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result):
            helpers.run_cmd(["incus", "list"], capture=True)

        helpers._learn_incus_cache = None  # reset
        captured = capsys.readouterr()
        assert "[incus]" not in captured.out
