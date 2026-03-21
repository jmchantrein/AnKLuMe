"""Tests CLI Phase 17 — enregistrement des commandes disp, setup, clipboard."""

from __future__ import annotations

from typer.testing import CliRunner

from anklume.cli import app

runner = CliRunner()


class TestDispCommand:
    """Vérifie que la commande disp est enregistrée."""

    def test_disp_registered(self):
        """La commande disp existe."""
        result = runner.invoke(app, ["disp", "--help"])
        assert result.exit_code == 0
        assert "jetable" in result.output

    def test_disp_list_option(self):
        """L'option --list est disponible."""
        result = runner.invoke(app, ["disp", "--help"])
        assert "--list" in result.output

    def test_disp_cleanup_option(self):
        """L'option --cleanup est disponible."""
        result = runner.invoke(app, ["disp", "--help"])
        assert "--cleanup" in result.output


class TestSetupCommand:
    """Vérifie que les commandes setup sont enregistrées."""

    def test_setup_import_registered(self):
        """La commande setup import existe."""
        result = runner.invoke(app, ["setup", "import", "--help"])
        assert result.exit_code == 0
        assert "Importer" in result.output or "import" in result.output.lower()


class TestClipboardCommand:
    """Vérifie que la commande instance clipboard est enregistrée."""

    def test_clipboard_registered(self):
        """La commande instance clipboard existe."""
        result = runner.invoke(app, ["instance", "clipboard", "--help"])
        assert result.exit_code == 0
        assert "presse-papiers" in result.output.lower() or "clipboard" in result.output.lower()

    def test_clipboard_default_is_push(self):
        """Le comportement par défaut est push (hôte → conteneur)."""
        result = runner.invoke(app, ["instance", "clipboard", "--help"])
        assert "hôte → conteneur" in result.output

    def test_clipboard_pull_option(self):
        """L'option --pull est disponible."""
        result = runner.invoke(app, ["instance", "clipboard", "--help"])
        assert "--pull" in result.output
