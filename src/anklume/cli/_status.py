"""Implémentation de `anklume status`."""

from __future__ import annotations

import typer

from anklume.cli._common import load_infra
from anklume.engine.incus_driver import IncusDriver
from anklume.engine.nesting import detect_nesting_context
from anklume.engine.status import InfraStatus, compute_status


def run_status() -> None:
    """Affiche l'état de l'infrastructure : déclaré vs réel."""
    infra = load_infra()
    driver = IncusDriver()
    ctx = detect_nesting_context()

    status = compute_status(infra, driver, nesting_context=ctx)
    _print_status(status)


def _print_status(status: InfraStatus) -> None:
    """Affiche le tableau de status."""
    if not status.domains:
        typer.echo("Aucun domaine activé.")
        return

    for ds in status.domains:
        typer.echo(f"\n{ds.name}:")
        proj = "oui" if ds.project_exists else "non"
        net = "oui" if ds.network_exists else "non"
        typer.echo(f"  Projet : {proj}    Réseau : {net}")

        for inst in ds.instances:
            if inst.synced:
                tag = "[ok]"
            elif inst.state == "Stopped":
                tag = "[arrêtée]"
            else:
                tag = "[absente]"

            typer.echo(f"  {inst.name:<20s} {inst.machine_type:<5s} {inst.state:<10s} {tag}")

    typer.echo(
        f"\nRésumé : {status.projects_found}/{status.projects_total} projets, "
        f"{status.networks_found}/{status.networks_total} réseaux, "
        f"{status.instances_running}/{status.instances_total} instances running"
    )
