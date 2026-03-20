"""Implémentation des commandes `anklume snapshot`."""

from __future__ import annotations

import typer

from anklume.cli._common import load_infra
from anklume.engine.incus_driver import IncusDriver, IncusError
from anklume.engine.snapshot import (
    create_auto_snapshots,
    list_all_snapshots,
    resolve_instance_project,
    rollback_pre_apply,
    rollback_snapshot,
)
from anklume.engine.snapshot import (
    create_snapshot as _create_snapshot,
)
from anklume.engine.snapshot import (
    restore_snapshot as _restore_snapshot,
)


def run_snapshot_create(
    instance: str | None = None,
    name: str | None = None,
) -> None:
    """Crée des snapshots manuels."""
    infra = load_infra()
    driver = IncusDriver()

    if instance:
        project = resolve_instance_project(infra, instance)
        if not project:
            typer.echo(f"Instance inconnue : {instance}", err=True)
            raise typer.Exit(1)

        try:
            snap_name = _create_snapshot(driver, instance, project, name=name)
            typer.echo(f"  {instance} : {snap_name}")
        except IncusError as e:
            typer.echo(f"  {instance} : erreur — {e}", err=True)
            raise typer.Exit(1) from None
    else:
        if name:
            typer.echo("--name requiert un nom d'instance.", err=True)
            raise typer.Exit(1)
        created = create_auto_snapshots(driver, infra, "snap")
        for inst_name, _project, snap_name in created:
            typer.echo(f"  {inst_name} : {snap_name}")
        typer.echo(f"\n{len(created)} snapshot(s) créé(s).")


def run_snapshot_list(instance: str | None = None) -> None:
    """Liste les snapshots."""
    infra = load_infra()
    driver = IncusDriver()

    snapshots = list_all_snapshots(driver, infra, instance_name=instance)

    if not snapshots:
        typer.echo("Aucun snapshot trouvé.")
        return

    for inst_name, snaps in snapshots.items():
        if not snaps:
            continue
        typer.echo(f"{inst_name}:")
        for s in snaps:
            date_str = f"  ({s.created_at})" if s.created_at else ""
            typer.echo(f"  {s.name}{date_str}")


def run_snapshot_restore(instance: str, snapshot: str) -> None:
    """Restaure un snapshot."""
    infra = load_infra()
    driver = IncusDriver()

    project = resolve_instance_project(infra, instance)
    if not project:
        typer.echo(f"Instance inconnue : {instance}", err=True)
        raise typer.Exit(1)

    try:
        _restore_snapshot(driver, instance, project, snapshot)
        typer.echo(f"Snapshot '{snapshot}' restauré sur {instance}.")
    except IncusError as e:
        typer.echo(f"Erreur de restauration : {e}", err=True)
        raise typer.Exit(1) from None


def run_snapshot_delete(instance: str, snapshot: str) -> None:
    """Supprime un snapshot."""
    infra = load_infra()
    driver = IncusDriver()

    project = resolve_instance_project(infra, instance)
    if not project:
        typer.echo(f"Instance inconnue : {instance}", err=True)
        raise typer.Exit(1)

    try:
        driver.snapshot_delete(instance, project, snapshot)
        typer.echo(f"Snapshot '{snapshot}' supprimé de {instance}.")
    except IncusError as e:
        typer.echo(f"Erreur de suppression : {e}", err=True)
        raise typer.Exit(1) from None


def run_snapshot_rollback(instance: str, snapshot: str) -> None:
    """Rollback destructif : restaure + supprime les snapshots postérieurs."""

    infra = load_infra()
    driver = IncusDriver()

    project = resolve_instance_project(infra, instance)
    if not project:
        typer.echo(f"Instance inconnue : {instance}", err=True)
        raise typer.Exit(1)

    try:
        deleted_count = rollback_snapshot(driver, instance, project, snapshot)
        typer.echo(f"Restauration de '{snapshot}' sur {instance}.")
        typer.echo(f"{deleted_count} snapshot(s) postérieur(s) supprimé(s).")
    except IncusError as e:
        typer.echo(f"Erreur de rollback : {e}", err=True)
        raise typer.Exit(1) from None


def run_rollback(dry_run: bool = False) -> None:
    """Rollback global : restaure les snapshots anklume-pre-* les plus récents."""
    infra = load_infra()
    driver = IncusDriver()

    prefix = "[dry-run] " if dry_run else ""

    restored = rollback_pre_apply(driver, infra, dry_run=dry_run)

    if not restored:
        typer.echo(f"{prefix}Aucun snapshot anklume-pre-* trouvé.")
        return

    for inst_name, project, snap_name in restored:
        typer.echo(f"{prefix}  {inst_name} ({project}) → {snap_name}")

    typer.echo(f"\n{prefix}{len(restored)} instance(s) restaurée(s).")
