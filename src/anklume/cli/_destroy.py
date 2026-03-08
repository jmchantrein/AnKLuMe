"""Implémentation de `anklume destroy`."""

from __future__ import annotations

import typer

from anklume.cli._common import load_infra
from anklume.engine.destroy import DestroyResult, destroy
from anklume.engine.incus_driver import IncusDriver
from anklume.engine.nesting import detect_nesting_context


def run_destroy(*, force: bool = False) -> None:
    """Pipeline destroy : parse → validate → destroy."""
    infra = load_infra()
    driver = IncusDriver()
    ctx = detect_nesting_context()

    result = destroy(infra, driver, force=force, nesting_context=ctx)
    _print_result(result, force=force)

    if not result.success:
        raise typer.Exit(1)


def _print_result(result: DestroyResult, *, force: bool) -> None:
    """Affiche le résultat de la destruction."""
    if not result.actions and not result.skipped:
        typer.echo("Rien à détruire.")
        return

    for action in result.executed:
        typer.echo(f"  {action.detail}")

    for name, reason in result.skipped:
        typer.echo(f"  [protégée] {name} ({reason})")

    deleted = result.instances_deleted
    skipped = len(result.skipped)
    errors = len(result.errors)

    parts = [f"{deleted} instance(s) supprimée(s)"]
    if skipped:
        parts.append(f"{skipped} protégée(s)")
    parts.append(f"{errors} erreur(s)")
    typer.echo(f"\n{', '.join(parts)}.")

    for action, msg in result.errors:
        typer.echo(f"  ✗ {action.target} : {msg}", err=True)
