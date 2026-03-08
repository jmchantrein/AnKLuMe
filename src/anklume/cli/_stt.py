"""Implémentation de `anklume stt setup` et `anklume stt status`."""

from __future__ import annotations

import os
import shutil

import typer

# Dépendances hôte requises pour le push-to-talk
STT_DEPENDENCIES: list[str] = [
    "pw-record",
    "wtype",
    "wl-copy",
    "kdotool",
    "jq",
    "notify-send",
]


def get_stt_config() -> dict[str, str]:
    """Retourne la configuration STT depuis les variables d'environnement."""
    return {
        "api_url": os.environ.get("STT_API_URL", "http://10.100.3.1:8000"),
        "model": os.environ.get("STT_MODEL", "base"),
        "language": os.environ.get("STT_LANGUAGE", "fr"),
    }


def check_stt_dependencies() -> list[str]:
    """Vérifie les dépendances hôte et retourne la liste des manquantes."""
    return [dep for dep in STT_DEPENDENCIES if shutil.which(dep) is None]


def run_stt_setup() -> None:
    """Installe les dépendances hôte et configure le raccourci KDE."""
    missing = check_stt_dependencies()

    if missing:
        typer.echo("Dépendances manquantes :")
        for dep in missing:
            typer.echo(f"  - {dep}")
        typer.echo("\nInstallez-les avec votre gestionnaire de paquets.")
        raise typer.Exit(1)

    typer.echo("Toutes les dépendances sont installées.")

    # Configuration du raccourci KDE Meta+S
    _setup_kde_shortcut()

    config = get_stt_config()
    typer.echo("\nConfiguration STT :")
    typer.echo(f"  API URL  : {config['api_url']}")
    typer.echo(f"  Modèle   : {config['model']}")
    typer.echo(f"  Langue   : {config['language']}")


def run_stt_status() -> None:
    """Affiche l'état du service STT et des dépendances."""
    from anklume.engine.ai import check_service_health

    config = get_stt_config()

    # Vérifier les dépendances
    missing = check_stt_dependencies()
    if missing:
        typer.echo("Dépendances manquantes :")
        for dep in missing:
            typer.echo(f"  - {dep}")
    else:
        typer.echo("Dépendances : OK")

    # Vérifier l'endpoint STT
    url = f"{config['api_url']}/v1/models"
    if check_service_health(url):
        typer.echo(f"Serveur STT : actif ({config['api_url']})")
    else:
        typer.echo(f"Serveur STT : injoignable ({config['api_url']})")


def _setup_kde_shortcut() -> None:
    """Configure le raccourci KDE Meta+S pour push-to-talk."""
    import subprocess

    script_path = shutil.which("push-to-talk.sh")
    if script_path is None:
        # Utiliser le chemin relatif au projet
        from pathlib import Path

        script_path = str(
            Path(__file__).parent.parent.parent.parent / "host" / "stt" / "push-to-talk.sh"
        )

    try:
        subprocess.run(
            [
                "kwriteconfig6",
                "--file",
                "kglobalshortcutsrc",
                "--group",
                "anklume-stt",
                "--key",
                "push-to-talk",
                f"{script_path},Meta+S,Push-to-talk STT",
            ],
            check=True,
        )
        typer.echo("Raccourci KDE Meta+S configuré.")
    except (FileNotFoundError, subprocess.CalledProcessError):
        typer.echo("Raccourci KDE : kwriteconfig6 indisponible, configurez manuellement.")
