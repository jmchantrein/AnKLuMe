"""anklume migrate — migration de schema_version."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from anklume.engine.models import SCHEMA_VERSION
from anklume.engine.parser import ParseError, parse_project

console = Console()


def run_migrate(project_dir: str = ".") -> None:
    """Vérifier et migrer le schema_version du projet."""
    project = Path(project_dir).resolve()

    try:
        infra = parse_project(project)
    except ParseError as e:
        console.print(f"[red]Erreur :[/red] {e}")
        raise typer.Exit(1) from None

    current = infra.config.schema_version
    target = SCHEMA_VERSION

    if current == target:
        console.print(f"[green]Projet déjà à jour[/green] (schema_version {target})")
        return

    if current > target:
        console.print(
            f"[red]schema_version {current} est plus récent que la version "
            f"supportée ({target}).[/red]\n"
            f"Mettre à jour anklume ou vérifier le fichier."
        )
        raise typer.Exit(1)

    # current < target : placeholder pour les futures migrations
    console.print(
        f"[yellow]Migration de schema_version {current} vers {target}[/yellow]"
    )
    console.print("[dim]Aucune migration automatique disponible pour le moment.[/dim]")
