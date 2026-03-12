"""Tests CLI Phase 19 — registration commandes + CI/CD + MkDocs (§31-34)."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# §31 — CI/CD GitHub Actions
# ---------------------------------------------------------------------------


class TestCICD:
    """Vérification du workflow GitHub Actions."""

    def test_ci_yml_exists(self) -> None:
        assert (ROOT / ".github" / "workflows" / "ci.yml").is_file()

    def test_ci_yml_valid_yaml(self) -> None:
        data = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
        assert isinstance(data, dict)

    def test_ci_has_lint_job(self) -> None:
        data = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
        assert "lint" in data.get("jobs", {})

    def test_ci_has_test_job(self) -> None:
        data = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
        assert "test" in data.get("jobs", {})

    def test_ci_has_build_job(self) -> None:
        data = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
        assert "build" in data.get("jobs", {})

    def test_ci_has_shellcheck_job(self) -> None:
        data = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
        assert "shellcheck" in data.get("jobs", {})

    def test_ci_triggers_on_push_and_pr(self) -> None:
        data = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
        triggers = data.get("on", data.get(True, []))
        assert "push" in triggers or True in triggers  # yaml True == on
        assert "pull_request" in triggers or True in triggers


# ---------------------------------------------------------------------------
# §34 — MkDocs
# ---------------------------------------------------------------------------


class TestMkDocs:
    """Vérification de la configuration MkDocs."""

    def test_mkdocs_yml_exists(self) -> None:
        assert (ROOT / "mkdocs.yml").is_file()

    def test_mkdocs_yml_valid_yaml(self) -> None:
        data = yaml.load((ROOT / "mkdocs.yml").read_text(), Loader=yaml.BaseLoader)  # noqa: S506
        assert isinstance(data, dict)

    def test_mkdocs_has_site_name(self) -> None:
        data = yaml.load((ROOT / "mkdocs.yml").read_text(), Loader=yaml.BaseLoader)  # noqa: S506
        assert "site_name" in data

    def test_mkdocs_has_theme(self) -> None:
        data = yaml.load((ROOT / "mkdocs.yml").read_text(), Loader=yaml.BaseLoader)  # noqa: S506
        assert "theme" in data

    def test_mkdocs_has_nav(self) -> None:
        data = yaml.load((ROOT / "mkdocs.yml").read_text(), Loader=yaml.BaseLoader)  # noqa: S506
        assert "nav" in data

    def test_index_md_exists(self) -> None:
        assert (ROOT / "docs" / "index.md").is_file()

    def test_nav_references_existing_files(self) -> None:
        data = yaml.load((ROOT / "mkdocs.yml").read_text(), Loader=yaml.BaseLoader)  # noqa: S506
        nav = data.get("nav", [])

        def check_nav(items: list) -> None:
            for entry in items:
                if isinstance(entry, str):
                    assert (ROOT / "docs" / entry).is_file(), f"Manquant : {entry}"
                elif isinstance(entry, dict):
                    for _label, value in entry.items():
                        if isinstance(value, str):
                            assert (ROOT / "docs" / value).is_file(), f"Manquant : {value}"
                        elif isinstance(value, list):
                            check_nav(value)

        check_nav(nav)


# ---------------------------------------------------------------------------
# §33 — CLI telemetry registration
# ---------------------------------------------------------------------------


class TestTelemetryCLI:
    """Vérification de l'enregistrement des commandes telemetry."""

    def test_telemetry_app_registered(self) -> None:
        from anklume.cli import app

        names = [g.name for g in app.registered_groups]
        assert "telemetry" in names

    def test_telemetry_on_command_exists(self) -> None:
        from anklume.cli import telemetry_app

        commands = [c.name for c in telemetry_app.registered_commands]
        assert "on" in commands

    def test_telemetry_off_command_exists(self) -> None:
        from anklume.cli import telemetry_app

        commands = [c.name for c in telemetry_app.registered_commands]
        assert "off" in commands

    def test_telemetry_status_command_exists(self) -> None:
        from anklume.cli import telemetry_app

        commands = [c.name for c in telemetry_app.registered_commands]
        assert "status" in commands


# ---------------------------------------------------------------------------
# §33 — CLI telemetry functions
# ---------------------------------------------------------------------------


class TestTelemetryCLIFunctions:
    """Fonctions CLI telemetry dans _telemetry.py."""

    def test_run_telemetry_on_importable(self) -> None:
        from anklume.cli._telemetry import run_telemetry_on

        assert callable(run_telemetry_on)

    def test_run_telemetry_off_importable(self) -> None:
        from anklume.cli._telemetry import run_telemetry_off

        assert callable(run_telemetry_off)

    def test_run_telemetry_status_importable(self) -> None:
        from anklume.cli._telemetry import run_telemetry_status

        assert callable(run_telemetry_status)
