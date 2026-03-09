"""Implémentation de `anklume portal push/pull/list`."""

from __future__ import annotations

import typer

from anklume.cli._common import load_infra
from anklume.engine.incus_driver import IncusDriver, IncusError
from anklume.engine.portal import list_remote, pull_file, push_file


def run_portal_push(instance: str, local_path: str, remote_path: str) -> None:
    """Envoie un fichier vers une instance."""
    infra = load_infra()
    driver = IncusDriver()

    try:
        result = push_file(driver, infra, instance, local_path, remote_path)
        size_ko = result.size // 1024 or 1
        typer.echo(
            f"Envoyé : {result.local_path} → {result.instance}:{result.remote_path} ({size_ko} Ko)"
        )
    except FileNotFoundError as e:
        typer.echo(f"Erreur : {e}", err=True)
        raise typer.Exit(1) from None
    except ValueError as e:
        typer.echo(f"Erreur : {e}", err=True)
        raise typer.Exit(1) from None
    except IncusError as e:
        typer.echo(f"Erreur : {e}", err=True)
        raise typer.Exit(1) from None


def run_portal_pull(instance: str, remote_path: str, local_path: str) -> None:
    """Récupère un fichier depuis une instance."""
    infra = load_infra()
    driver = IncusDriver()

    try:
        result = pull_file(driver, infra, instance, remote_path, local_path)
        size_ko = result.size // 1024 or 1
        typer.echo(
            f"Récupéré : {result.instance}:{result.remote_path} → "
            f"{result.local_path} ({size_ko} Ko)"
        )
    except ValueError as e:
        typer.echo(f"Erreur : {e}", err=True)
        raise typer.Exit(1) from None
    except IncusError as e:
        typer.echo(f"Erreur : {e}", err=True)
        raise typer.Exit(1) from None


def run_portal_list(instance: str, path: str) -> None:
    """Liste les fichiers d'un répertoire distant."""
    infra = load_infra()
    driver = IncusDriver()

    try:
        entries = list_remote(driver, infra, instance, path)
    except ValueError as e:
        typer.echo(f"Erreur : {e}", err=True)
        raise typer.Exit(1) from None
    except IncusError as e:
        typer.echo(f"Erreur : {e}", err=True)
        raise typer.Exit(1) from None

    if not entries:
        typer.echo("Répertoire vide.")
        return

    typer.echo(f"{'NOM':<30s} {'TYPE':<12s} {'TAILLE':<10s} {'PERMISSIONS'}")
    for entry in entries:
        size = f"{entry.size}" if entry.size >= 0 else "-"
        type_fr = {
            "file": "fichier",
            "directory": "répertoire",
            "link": "lien",
        }.get(entry.entry_type, entry.entry_type)
        typer.echo(f"{entry.name:<30s} {type_fr:<12s} {size:<10s} {entry.permissions}")
