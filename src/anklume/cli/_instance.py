"""Implémentation de `anklume instance list`, `exec`, `info`."""

from __future__ import annotations

import typer

from anklume.cli._common import load_infra
from anklume.engine.incus_driver import IncusDriver, IncusError
from anklume.engine.nesting import detect_nesting_context
from anklume.engine.ops import InstanceInfo, get_instance_info, list_instances
from anklume.engine.snapshot import resolve_instance_project


def run_instance_list() -> None:
    """Affiche le tableau de toutes les instances."""
    infra = load_infra()
    driver = IncusDriver()
    ctx = detect_nesting_context()

    instances = list_instances(infra, driver, nesting_context=ctx)

    if not instances:
        typer.echo("Aucune instance déclarée.")
        return

    typer.echo(
        f"{'NOM':<25s} {'DOMAINE':<12s} {'TYPE':<5s} {'ÉTAT':<10s} {'IP'}"
    )
    for inst in instances:
        ip = inst.ip or "-"
        typer.echo(
            f"{inst.name:<25s} {inst.domain:<12s} {inst.machine_type:<5s} "
            f"{inst.state:<10s} {ip}"
        )

    running = sum(1 for i in instances if i.state == "Running")
    stopped = sum(1 for i in instances if i.state == "Stopped")
    absent = sum(1 for i in instances if i.state == "Absent")
    parts = [f"{len(instances)} instance(s)"]
    if running:
        parts.append(f"{running} active(s)")
    if stopped:
        parts.append(f"{stopped} arrêtée(s)")
    if absent:
        parts.append(f"{absent} absente(s)")
    typer.echo(f"\n{' — '.join(parts)}")


def run_instance_exec(instance: str, cmd: list[str]) -> None:
    """Exécute une commande dans une instance."""
    infra = load_infra()
    driver = IncusDriver()

    project = resolve_instance_project(infra, instance)
    if not project:
        typer.echo(f"Instance inconnue : {instance}", err=True)
        raise typer.Exit(1)

    try:
        result = driver.instance_exec(instance, project, cmd)
        if result.stdout:
            typer.echo(result.stdout, nl=False)
        if result.stderr:
            typer.echo(result.stderr, nl=False, err=True)
    except IncusError as e:
        typer.echo(f"Erreur : {e}", err=True)
        raise typer.Exit(1) from None


def run_instance_info(instance: str) -> None:
    """Affiche les détails d'une instance."""
    infra = load_infra()
    driver = IncusDriver()
    ctx = detect_nesting_context()

    info = get_instance_info(infra, driver, instance, nesting_context=ctx)
    if info is None:
        typer.echo(f"Instance inconnue : {instance}", err=True)
        raise typer.Exit(1)

    _print_instance_info(info)


def _print_instance_info(info: InstanceInfo) -> None:
    """Affiche les détails formatés d'une instance."""
    typer.echo(info.name)
    typer.echo(f"  Domaine     : {info.domain}")
    typer.echo(f"  Type        : {info.machine_type}")
    typer.echo(f"  État        : {info.state}")
    typer.echo(f"  IP          : {info.ip or '-'}")
    typer.echo(f"  Trust level : {info.trust_level}")
    typer.echo(f"  GPU         : {'oui' if info.gpu else 'non'}")
    typer.echo(f"  Rôles       : {', '.join(info.roles) or 'aucun'}")
    typer.echo(f"  Profils     : {', '.join(info.profiles)}")
    typer.echo(f"  Éphémère    : {'oui' if info.ephemeral else 'non'}")

    if info.snapshots:
        typer.echo(f"  Snapshots   : {', '.join(info.snapshots)}")
    else:
        typer.echo("  Snapshots   : aucun")
