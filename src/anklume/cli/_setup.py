"""Implémentation de `anklume setup import`."""

from __future__ import annotations

from pathlib import Path

import typer

from anklume.engine.import_infra import import_infrastructure
from anklume.engine.incus_driver import IncusDriver, IncusError


def run_setup_import(output_dir: str = ".") -> None:
    """Scanne Incus et génère les fichiers domaine."""
    driver = IncusDriver()

    try:
        result = import_infrastructure(driver, Path(output_dir))
    except IncusError as e:
        typer.echo(f"Erreur : {e}", err=True)
        raise typer.Exit(1) from None

    if not result.domains:
        typer.echo("Aucun projet Incus trouvé (hors default).")
        return

    typer.echo(f"Projets scannés : {len(result.domains)}")
    for domain in result.domains:
        inst_count = len(domain.instances)
        net = domain.network or "aucun"
        typer.echo(f"  {domain.project} : {inst_count} instance(s), réseau {net}")

    typer.echo("\nFichiers générés :")
    for f in result.files_written:
        typer.echo(f"  {f}")
