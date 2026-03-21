"""Tests pour le mécanisme de plugin discovery CLI."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import typer
from typer.testing import CliRunner

from anklume.cli import _builtin_names, _discover_plugins, app

runner = CliRunner()


class TestBuiltinNames:
    """Les noms réservés sont dérivés des commandes enregistrées."""

    def test_builtin_names_not_empty(self):
        """Le set de noms réservés n'est pas vide."""
        assert len(_builtin_names()) > 10

    def test_core_commands_in_builtin(self):
        """Les commandes core sont bien dans les noms réservés."""
        names = _builtin_names()
        for name in ("apply", "init", "status", "destroy", "doctor"):
            assert name in names

    def test_builtin_names_matches_registered(self):
        """Les noms dérivés correspondent aux commandes réellement enregistrées."""
        names = _builtin_names()
        # Vérifier qu'on a au moins les groupes principaux
        for expected in ("apply", "dev", "instance", "domain", "snapshot", "network"):
            assert expected in names, f"{expected} manquant dans _builtin_names()"


class TestDiscoverPlugins:
    """Tests pour _discover_plugins()."""

    def test_no_plugins_installed(self):
        """Pas de crash si entry_points lève une exception."""
        with patch("importlib.metadata.entry_points", side_effect=ImportError):
            _discover_plugins()

    def test_plugin_load_failure_graceful(self):
        """Un plugin qui plante au chargement ne casse pas la CLI."""
        mock_ep = MagicMock()
        mock_ep.name = "broken_plugin"
        mock_ep.load.side_effect = ImportError("module introuvable")

        with patch("importlib.metadata.entry_points", return_value=[mock_ep]):
            _discover_plugins()

        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0

    def test_plugin_conflicts_with_builtin(self):
        """Un plugin nommé comme une commande intégrée est ignoré."""
        mock_ep = MagicMock()
        mock_ep.name = "apply"
        mock_ep.load.return_value = typer.Typer(help="Fake plugin")

        with patch("importlib.metadata.entry_points", return_value=[mock_ep]):
            _discover_plugins()

        result = runner.invoke(app, ["apply", "--help"])
        assert result.exit_code == 0
        assert "Déployer" in result.output

    def test_plugin_registers_typer_app(self):
        """Un plugin valide est ajouté comme sous-commande."""
        plugin = typer.Typer(help="Mon plugin de test")

        @plugin.command("hello")
        def hello():
            typer.echo("Plugin OK")

        mock_ep = MagicMock()
        mock_ep.name = "testplugin"
        mock_ep.load.return_value = plugin

        # Snapshot pour cleanup
        groups_before = list(app.registered_groups)

        with patch("importlib.metadata.entry_points", return_value=[mock_ep]):
            _discover_plugins()

        result = runner.invoke(app, ["testplugin", "hello"])
        assert result.exit_code == 0
        assert "Plugin OK" in result.output

        # Cleanup : retirer le plugin ajouté
        app.registered_groups[:] = groups_before

    def test_entry_points_exception_handled(self):
        """Si entry_points() lève une exception, pas de crash."""
        with patch(
            "importlib.metadata.entry_points",
            side_effect=RuntimeError("broken metadata"),
        ):
            _discover_plugins()

        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
