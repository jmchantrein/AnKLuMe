"""Commande CLI : anklume resource show."""

from __future__ import annotations

from pathlib import Path

import typer

from anklume.engine.parser import ParseError, parse_project
from anklume.engine.resources import (
    ResourceAllocation,
    compute_resource_allocation,
    detect_hardware,
)
from anklume.engine.validator import validate


def run_resource_show(project_dir: str) -> None:
    """Affiche l'allocation de ressources calculée."""
    path = Path(project_dir)
    try:
        infra = parse_project(path)
    except ParseError as e:
        typer.echo(f"Erreur : {e}", err=True)
        raise typer.Exit(1) from None

    result = validate(infra)
    if not result.valid:
        for err in result.errors:
            typer.echo(f"⚠ {err}", err=True)

    if infra.config.resource_policy is None:
        typer.echo("Aucune resource_policy configurée dans anklume.yml")
        raise typer.Exit(0) from None

    hardware = detect_hardware()
    allocations = compute_resource_allocation(infra, hardware)

    if not allocations:
        typer.echo("Aucune instance active.")
        raise typer.Exit(0) from None

    # Hardware
    mem_gb = round(hardware.memory_bytes / 1024**3, 1)
    typer.echo(f"Hardware : {hardware.cpu_threads} threads, {mem_gb} GB RAM")

    policy = infra.config.resource_policy
    typer.echo(f"Mode : {policy.mode}, CPU : {policy.cpu_mode}, Mémoire : {policy.memory_enforce}")
    typer.echo()

    # Tableau
    _print_table(allocations)


def _print_table(allocations: list[ResourceAllocation]) -> None:
    """Affiche le tableau des allocations."""
    header = f"{'Instance':<30} {'CPU':<15} {'Mémoire':<15} {'Source':<10}"
    typer.echo(header)
    typer.echo("─" * len(header))

    for a in allocations:
        cpu = f"{a.cpu_value} ({a.cpu_key.split('.')[-1]})"
        mem = f"{a.memory_value} ({a.memory_key.split('.')[-1]})"
        typer.echo(f"{a.instance_name:<30} {cpu:<15} {mem:<15} {a.source:<10}")
