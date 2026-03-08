"""Tests de la commande anklume init."""

import pytest

from anklume.cli._init import run_init


class TestInit:
    def test_creates_structure(self, tmp_path):
        project = tmp_path / "test-project"

        run_init(str(project))

        assert (project / "anklume.yml").exists()
        assert (project / "domains" / "pro.yml").exists()
        assert (project / "policies.yml").exists()
        assert (project / "ansible_roles_custom" / ".gitkeep").exists()

    def test_anklume_yml_has_schema_version(self, tmp_path):
        project = tmp_path / "test-project"

        run_init(str(project))
        content = (project / "anklume.yml").read_text()

        assert "schema_version: 1" in content

    def test_anklume_yml_no_project_field(self, tmp_path):
        project = tmp_path / "test-project"

        run_init(str(project))
        content = (project / "anklume.yml").read_text()

        assert "project:" not in content

    def test_anklume_yml_has_nesting(self, tmp_path):
        project = tmp_path / "test-project"

        run_init(str(project))
        content = (project / "anklume.yml").read_text()

        assert "nesting:" in content
        assert "prefix: true" in content

    def test_english_creates_work_domain(self, tmp_path):
        project = tmp_path / "test-project"

        run_init(str(project), lang="en")

        assert (project / "domains" / "work.yml").exists()
        assert not (project / "domains" / "pro.yml").exists()

    def test_french_creates_pro_domain(self, tmp_path):
        project = tmp_path / "test-project"

        run_init(str(project), lang="fr")

        assert (project / "domains" / "pro.yml").exists()

    def test_non_empty_dir_fails(self, tmp_path):
        import typer

        project = tmp_path / "test-project"
        project.mkdir()
        (project / "somefile").touch()

        with pytest.raises(typer.Exit):
            run_init(str(project))

    def test_existing_anklume_yml_exits(self, tmp_path, monkeypatch):
        import typer

        monkeypatch.chdir(tmp_path)
        (tmp_path / "anklume.yml").write_text("existing")

        with pytest.raises(typer.Exit):
            run_init(".")

    def test_dot_creates_in_cwd(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        run_init(".")

        assert (tmp_path / "anklume.yml").exists()
        assert (tmp_path / "domains").is_dir()

    def test_parsable_by_engine(self, tmp_path):
        """Le projet créé par init est parsable par le moteur."""
        from anklume.engine.parser import parse_project

        project = tmp_path / "test-project"
        run_init(str(project))

        infra = parse_project(project)

        assert infra.config.schema_version == 1
        assert len(infra.domains) == 2  # pro + ai-tools
        assert "ai-tools" in infra.domains
        assert infra.policies == []
