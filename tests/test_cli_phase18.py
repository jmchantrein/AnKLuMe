"""Tests CLI Phase 18 — registration des commandes."""

from __future__ import annotations

from typer.testing import CliRunner

from anklume.cli import app

runner = CliRunner()


class TestTorCLI:
    """Tests pour les commandes tor."""

    def test_tor_group_registered(self):
        """Le groupe 'tor' est enregistré."""
        result = runner.invoke(app, ["tor", "--help"])
        assert result.exit_code == 0

    def test_tor_status_registered(self):
        """La commande 'tor status' est enregistrée."""
        result = runner.invoke(app, ["tor", "status", "--help"])
        assert result.exit_code == 0


class TestConsoleCLI:
    """Tests pour la commande console."""

    def test_console_registered(self):
        """La commande 'console' est enregistrée."""
        result = runner.invoke(app, ["console", "--help"])
        assert result.exit_code == 0

    def test_console_detach_option(self):
        """L'option --detach est disponible."""
        result = runner.invoke(app, ["console", "--help"])
        assert "--detach" in result.output


class TestDoctorCLI:
    """Tests pour la commande doctor."""

    def test_doctor_registered(self):
        """La commande 'doctor' est enregistrée."""
        result = runner.invoke(app, ["doctor", "--help"])
        assert result.exit_code == 0

    def test_doctor_fix_option(self):
        """L'option --fix est disponible."""
        result = runner.invoke(app, ["doctor", "--help"])
        assert "--fix" in result.output

    def test_doctor_json_option(self):
        """L'option --json est disponible."""
        result = runner.invoke(app, ["doctor", "--help"])
        assert "--json" in result.output
