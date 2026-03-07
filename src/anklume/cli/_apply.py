"""Implémentation de `anklume apply all` et `anklume apply domain <nom>`."""

from __future__ import annotations

from pathlib import Path

import typer

from anklume.engine.addressing import assign_addresses
from anklume.engine.incus_driver import IncusDriver
from anklume.engine.parser import ParseError, parse_project
from anklume.engine.reconciler import ReconcileResult, reconcile
from anklume.engine.validator import validate


def run_apply(
    *,
    domain_name: str | None = None,
    dry_run: bool = False,
) -> None:
    """Exécute le pipeline apply : parse → validate → address → reconcile."""
    project_dir = Path.cwd()

    # 1. Parser
    try:
        infra = parse_project(project_dir)
    except ParseError as e:
        typer.echo(f"Erreur de parsing : {e}", err=True)
        raise typer.Exit(1) from None

    # 2. Filtrer un domaine spécifique si demandé
    if domain_name:
        if domain_name not in infra.domains:
            typer.echo(f"Domaine inconnu : {domain_name}", err=True)
            raise typer.Exit(1)
        infra.domains = {domain_name: infra.domains[domain_name]}

    # 3. Valider
    result = validate(infra)
    if not result.valid:
        typer.echo(str(result), err=True)
        raise typer.Exit(1)

    # 4. Adressage
    assign_addresses(infra)

    # 5. Réconcilier
    driver = IncusDriver()
    reconcile_result = reconcile(infra, driver, dry_run=dry_run)

    # 6. Afficher le résultat
    _print_result(reconcile_result, dry_run=dry_run)

    if not reconcile_result.success:
        raise typer.Exit(1)


def _print_result(result: ReconcileResult, *, dry_run: bool) -> None:
    """Affiche le résultat de la réconciliation."""
    prefix = "[dry-run] " if dry_run else ""

    if not result.actions:
        typer.echo(f"{prefix}Infrastructure à jour — rien à faire.")
        return

    for action in result.actions:
        symbol = "+" if action.verb == "create" else "▶" if action.verb == "start" else "•"
        typer.echo(f"{prefix}  {symbol} {action.detail}")

    if not dry_run:
        ok = len(result.executed)
        fail = len(result.errors)
        typer.echo(f"\n{ok} action(s) réussie(s), {fail} erreur(s).")

        for action, msg in result.errors:
            typer.echo(f"  ✗ {action.target} : {msg}", err=True)
