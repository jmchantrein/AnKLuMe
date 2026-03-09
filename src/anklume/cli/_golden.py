"""Implémentation de `anklume golden`."""

from __future__ import annotations

import typer

from anklume.engine.golden import create_golden, delete_golden, list_golden
from anklume.engine.incus_driver import IncusDriver, IncusError
from anklume.engine.parser import load_infrastructure


def run_golden_create(instance: str, alias: str | None = None) -> None:
    """Publie une instance comme golden image."""
    driver = IncusDriver()
    infra = load_infrastructure()

    try:
        result = create_golden(driver, infra, instance, alias=alias)
    except ValueError as e:
        typer.echo(f"Erreur : {e}", err=True)
        raise typer.Exit(1) from None
    except IncusError as e:
        typer.echo(f"Erreur Incus : {e}", err=True)
        raise typer.Exit(1) from None

    size_mb = result.size // (1024 * 1024) if result.size else 0
    fp_short = result.fingerprint[:8] if result.fingerprint else "?"
    typer.echo(f"Image {result.alias} créée (fingerprint: {fp_short}, {size_mb} Mo)")


def run_golden_list() -> None:
    """Liste les golden images."""
    driver = IncusDriver()

    images = list_golden(driver)

    if not images:
        typer.echo("Aucune golden image.")
        return

    typer.echo(f"{'ALIAS':<30s} {'FINGERPRINT':<12s} {'TAILLE':<10s}")
    for img in images:
        fp_short = img.fingerprint[:8] if img.fingerprint else "?"
        size_mb = img.size // (1024 * 1024) if img.size else 0
        typer.echo(f"{img.alias:<30s} {fp_short:<12s} {size_mb} Mo")

    typer.echo(f"\n{len(images)} golden image(s)")


def run_golden_delete(alias: str) -> None:
    """Supprime une golden image."""
    driver = IncusDriver()

    try:
        delete_golden(driver, alias)
    except ValueError as e:
        typer.echo(f"Erreur : {e}", err=True)
        raise typer.Exit(1) from None
    except IncusError as e:
        typer.echo(f"Erreur Incus : {e}", err=True)
        raise typer.Exit(1) from None

    typer.echo(f"Image {alias} supprimée.")
