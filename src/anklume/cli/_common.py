"""Utilitaires partagés pour les commandes CLI."""

from __future__ import annotations

from pathlib import Path

import typer

from anklume.engine.addressing import assign_addresses
from anklume.engine.models import Infrastructure
from anklume.engine.parser import ParseError, parse_project
from anklume.engine.validator import validate


def load_infra(project_dir: Path | None = None) -> Infrastructure:
    """Parse, valide et calcule l'adressage du projet courant."""
    try:
        infra = parse_project(project_dir or Path.cwd())
    except ParseError as e:
        typer.echo(f"Erreur de parsing : {e}", err=True)
        raise typer.Exit(1) from None

    result = validate(infra)
    if not result.valid:
        typer.echo(str(result), err=True)
        raise typer.Exit(1)

    assign_addresses(infra)
    return infra
