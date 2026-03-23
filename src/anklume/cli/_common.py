"""Utilitaires partagés pour les commandes CLI."""

from __future__ import annotations

import os
from pathlib import Path

import typer

from anklume.engine.addressing import assign_addresses
from anklume.engine.models import Infrastructure
from anklume.engine.parser import ParseError, parse_project
from anklume.engine.validator import validate

#: Répertoire par défaut pour le projet d'infrastructure.
DEFAULT_INFRA_DIR = Path.home() / "anklume-infra"


def resolve_project_dir() -> Path:
    """Résout le répertoire du projet d'infrastructure.

    Ordre de résolution :
    1. Variable d'environnement ``ANKLUME_INFRA_DIR``
    2. Répertoire courant si ``anklume.yml`` y est présent (rétrocompat)
    3. ``~/anklume-infra`` par défaut
    """
    env = os.environ.get("ANKLUME_INFRA_DIR")
    if env:
        return Path(env).expanduser().resolve()

    cwd = Path.cwd()
    if (cwd / "anklume.yml").exists():
        return cwd

    return DEFAULT_INFRA_DIR


def load_infra(project_dir: Path | None = None) -> Infrastructure:
    """Parse, valide et calcule l'adressage du projet courant."""
    resolved = project_dir or resolve_project_dir()
    if not (resolved / "anklume.yml").exists():
        typer.echo(
            f"Projet introuvable dans {resolved}\nLancez d'abord : anklume init simple",
            err=True,
        )
        raise typer.Exit(1)
    try:
        infra = parse_project(resolved)
    except ParseError as e:
        typer.echo(f"Erreur de parsing : {e}", err=True)
        raise typer.Exit(1) from None

    result = validate(infra)
    if not result.valid:
        typer.echo(str(result), err=True)
        raise typer.Exit(1)

    assign_addresses(infra)
    return infra
