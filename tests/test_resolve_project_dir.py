"""Tests pour cli/_common.py — resolve_project_dir."""

from __future__ import annotations

from pathlib import Path

from anklume.cli._common import DEFAULT_INFRA_DIR, resolve_project_dir


class TestResolveProjectDir:
    """Tests pour resolve_project_dir."""

    def test_env_var_override(self, tmp_path, monkeypatch):
        """ANKLUME_INFRA_DIR prend la priorité."""
        custom_dir = tmp_path / "custom-infra"
        custom_dir.mkdir()
        monkeypatch.setenv("ANKLUME_INFRA_DIR", str(custom_dir))

        result = resolve_project_dir()
        assert result == custom_dir.resolve()

    def test_env_var_with_tilde(self, monkeypatch):
        """ANKLUME_INFRA_DIR avec ~ est expandé."""
        monkeypatch.setenv("ANKLUME_INFRA_DIR", "~/my-infra")

        result = resolve_project_dir()
        assert "~" not in str(result)
        assert result == (Path.home() / "my-infra").resolve()

    def test_cwd_with_anklume_yml(self, tmp_path, monkeypatch):
        """Si anklume.yml existe dans cwd, utiliser cwd."""
        monkeypatch.delenv("ANKLUME_INFRA_DIR", raising=False)
        (tmp_path / "anklume.yml").write_text("schema_version: 1\n")
        monkeypatch.chdir(tmp_path)

        result = resolve_project_dir()
        assert result == tmp_path

    def test_default_dir(self, tmp_path, monkeypatch):
        """Sans env var ni anklume.yml dans cwd → ~/anklume-infra."""
        monkeypatch.delenv("ANKLUME_INFRA_DIR", raising=False)
        monkeypatch.chdir(tmp_path)  # tmp_path n'a pas anklume.yml

        result = resolve_project_dir()
        assert result == DEFAULT_INFRA_DIR

    def test_env_var_beats_cwd(self, tmp_path, monkeypatch):
        """ANKLUME_INFRA_DIR est prioritaire même si cwd a anklume.yml."""
        (tmp_path / "anklume.yml").write_text("schema_version: 1\n")
        monkeypatch.chdir(tmp_path)

        custom_dir = tmp_path / "override"
        custom_dir.mkdir()
        monkeypatch.setenv("ANKLUME_INFRA_DIR", str(custom_dir))

        result = resolve_project_dir()
        assert result == custom_dir.resolve()
