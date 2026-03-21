"""Tests d'autocomplétion CLI — vérifie que toutes les commandes sont proposées.

Simule le mécanisme de completion bash de Click/Typer pour valider
que l'autocomplétion fonctionne pour 'anklume' et 'ank' (même binaire).
"""

from __future__ import annotations

import pathlib

import pytest
import typer.main
from click.shell_completion import ShellComplete

from anklume.cli import app

# ============================================================
# Helpers
# ============================================================

# L'app Click est construite une seule fois (le résultat est déterministe)
_click_app = typer.main.get_command(app)


def _get_completions(args: list[str], incomplete: str = "") -> list[str]:
    """Simule la complétion bash pour une ligne de commande donnée."""
    comp = ShellComplete(_click_app, {}, "anklume", "complete_bash")
    items = comp.get_completions(args, incomplete)
    return [item.value for item in items]


# ============================================================
# Commandes de premier niveau
# ============================================================

# Toutes les commandes et groupes attendus au premier niveau
EXPECTED_TOP_LEVEL = {
    # Commandes directes (pas de sous-commandes)
    "status",
    "destroy",
    "disp",
    "doctor",
    "tui",
    "rollback",
    "migrate",
    # Groupes de sous-commandes
    "init",
    "apply",
    "dev",
    "instance",
    "domain",
    "snapshot",
    "network",
    "ai",
    "stt",
    "llm",
    "setup",
    "tor",
    "resource",
    "workspace",
    "console",
}


class TestTopLevelCompletion:
    def test_all_commands_present(self) -> None:
        completions = set(_get_completions([]))
        missing = EXPECTED_TOP_LEVEL - completions
        assert not missing, f"Commandes manquantes en completion : {missing}"

    def test_no_unexpected_commands(self) -> None:
        completions = set(_get_completions([]))
        unexpected = completions - EXPECTED_TOP_LEVEL
        assert not unexpected, f"Commandes inattendues en completion : {unexpected}"

    def test_partial_completion(self) -> None:
        completions = _get_completions([], "in")
        assert "init" in completions
        assert "instance" in completions

    def test_partial_d(self) -> None:
        completions = _get_completions([], "d")
        assert "destroy" in completions
        assert "dev" in completions
        assert "disp" in completions
        assert "doctor" in completions
        assert "domain" in completions


# ============================================================
# anklume init — 'showcase' en completion
# ============================================================


class TestInitCompletion:
    def test_showcase_and_simple_proposed(self) -> None:
        completions = _get_completions(["init"])
        assert "showcase" in completions
        assert "simple" in completions

    def test_showcase_partial(self) -> None:
        completions = _get_completions(["init"], "sh")
        assert "showcase" in completions
        assert "simple" not in completions

    def test_simple_partial(self) -> None:
        completions = _get_completions(["init"], "si")
        assert "simple" in completions
        assert "showcase" not in completions


# ============================================================
# Sous-commandes des groupes
# ============================================================

EXPECTED_SUBCOMMANDS = {
    "init": {"showcase", "simple"},
    "apply": {"all", "domain"},
    "dev": {"setup", "lint", "test", "env", "test-real", "molecule"},
    "instance": {"list", "exec", "info", "gui", "clipboard"},
    "domain": {"list", "check", "exec", "status"},
    "snapshot": {"create", "list", "restore", "delete", "rollback"},
    "network": {"rules", "deploy", "status"},
    "ai": {"status", "flush", "switch", "test"},
    "stt": {"setup", "start", "stop", "status"},
    "llm": {"status", "bench", "sanitize"},
    "setup": {"import", "aliases", "gui"},
    "tor": {"status"},
    "resource": {"show"},
    "workspace": {"load", "status", "grid"},
    "console": {"kill"},
}


class TestSubcommandCompletion:
    def test_all_subcommands_present(self) -> None:
        for group, expected in EXPECTED_SUBCOMMANDS.items():
            completions = set(_get_completions([group]))
            missing = expected - completions
            assert not missing, f"Sous-commandes manquantes pour '{group}' : {missing}"

    def test_apply_partial(self) -> None:
        completions = _get_completions(["apply"], "a")
        assert "all" in completions

    def test_dev_partial(self) -> None:
        completions = _get_completions(["dev"], "t")
        assert "test" in completions
        assert "test-real" in completions


# ============================================================
# Vérification du script de completion bash
# ============================================================

_COMPLETION_SCRIPT = pathlib.Path.home() / ".bash_completions" / "anklume.sh"


class TestBashCompletionScript:
    """Vérifie que le script .bash_completions/anklume.sh couvre ank."""

    def test_completion_script_covers_ank(self) -> None:
        """Le script de completion doit enregistrer 'ank' en plus de 'anklume'."""
        if not _COMPLETION_SCRIPT.exists():
            pytest.skip("~/.bash_completions/anklume.sh absent (CI)")
        content = _COMPLETION_SCRIPT.read_text()
        assert "complete" in content
        assert "ank" in content, "Le script de completion doit couvrir l'alias 'ank'"

    def test_completion_function_uses_anklume_binary(self) -> None:
        """La fonction de completion doit appeler 'anklume', pas '$1'."""
        if not _COMPLETION_SCRIPT.exists():
            pytest.skip("~/.bash_completions/anklume.sh absent (CI)")
        content = _COMPLETION_SCRIPT.read_text()
        assert "_ANKLUME_COMPLETE=complete_bash anklume" in content
        assert "$1" not in content, (
            "La fonction de completion ne doit pas utiliser $1 (ne fonctionne pas avec l'alias ank)"
        )
