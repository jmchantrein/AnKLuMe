"""Tests for anklume mode accessibility and learn-incus commands."""

import pytest

typer = pytest.importorskip("typer")
from typer.testing import CliRunner  # noqa: E402

from scripts.cli.mode import app  # noqa: E402

runner = CliRunner()


class TestLearnIncus:
    def test_learn_incus_on(self, tmp_path, monkeypatch):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        (tmp_path / ".anklume").mkdir()
        result = runner.invoke(app, ["learn-incus", "on"])
        assert result.exit_code == 0
        assert "on" in result.output
        assert (tmp_path / ".anklume" / "learn_incus").read_text().strip() == "on"

    def test_learn_incus_off(self, tmp_path, monkeypatch):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        (tmp_path / ".anklume").mkdir()
        result = runner.invoke(app, ["learn-incus", "off"])
        assert result.exit_code == 0
        assert "off" in result.output

    def test_learn_incus_invalid(self, tmp_path, monkeypatch):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        result = runner.invoke(app, ["learn-incus", "maybe"])
        assert result.exit_code == 1

    def test_learn_incus_show(self, tmp_path, monkeypatch):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        result = runner.invoke(app, ["learn-incus"])
        assert result.exit_code == 0
        assert "off" in result.output  # default when file missing


class TestAccessibility:
    def test_show_default(self, tmp_path, monkeypatch):
        monkeypatch.setattr("scripts.accessibility._SETTINGS_PATH", tmp_path / "a11y.yml")
        result = runner.invoke(app, ["accessibility", "--show"])
        assert result.exit_code == 0
        assert "default" in result.output

    def test_set_palette(self, tmp_path, monkeypatch):
        monkeypatch.setattr("scripts.accessibility._SETTINGS_PATH", tmp_path / "a11y.yml")
        result = runner.invoke(app, ["accessibility", "--palette", "colorblind-deutan"])
        assert result.exit_code == 0
        assert "updated" in result.output

    def test_invalid_palette(self, tmp_path, monkeypatch):
        monkeypatch.setattr("scripts.accessibility._SETTINGS_PATH", tmp_path / "a11y.yml")
        result = runner.invoke(app, ["accessibility", "--palette", "neon"])
        assert result.exit_code == 1

    def test_set_tmux_coloring(self, tmp_path, monkeypatch):
        monkeypatch.setattr("scripts.accessibility._SETTINGS_PATH", tmp_path / "a11y.yml")
        result = runner.invoke(app, ["accessibility", "--tmux-coloring", "title-only"])
        assert result.exit_code == 0

    def test_set_dyslexia(self, tmp_path, monkeypatch):
        monkeypatch.setattr("scripts.accessibility._SETTINGS_PATH", tmp_path / "a11y.yml")
        result = runner.invoke(app, ["accessibility", "--dyslexia"])
        assert result.exit_code == 0

    def test_help_shows_options(self):
        result = runner.invoke(app, ["accessibility", "--help"])
        assert result.exit_code == 0
        assert "--palette" in result.output
        assert "--dyslexia" in result.output
