"""Implémentation de `anklume domain list`, `check`, `exec`, `status`."""

from __future__ import annotations

from pathlib import Path

import typer

from anklume.cli._common import load_infra
from anklume.engine.incus_driver import IncusDriver, IncusError
from anklume.engine.nesting import detect_nesting_context
from anklume.engine.ops import list_domains
from anklume.engine.parser import ParseError, parse_project
from anklume.engine.status import compute_status
from anklume.engine.validator import validate


def run_domain_list() -> None:
    """Affiche le tableau de tous les domaines."""
    infra = load_infra()
    domains = list_domains(infra)

    if not domains:
        typer.echo("Aucun domaine défini.")
        return

    typer.echo(
        f"{'NOM':<15s} {'ÉTAT':<10s} {'TRUST-LEVEL':<15s} {'MACHINES':>8s}  {'ÉPHÉMÈRE'}"
    )
    for d in domains:
        etat = "activé" if d.enabled else "désactivé"
        eph = "oui" if d.ephemeral else "non"
        typer.echo(
            f"{d.name:<15s} {etat:<10s} {d.trust_level:<15s} "
            f"{d.machine_count:>8d}  {eph}"
        )

    enabled = sum(1 for d in domains if d.enabled)
    disabled = len(domains) - enabled
    parts = [f"{len(domains)} domaine(s)", f"{enabled} activé(s)"]
    if disabled:
        parts.append(f"{disabled} désactivé(s)")
    typer.echo(f"\n{' — '.join(parts)}")


def run_domain_check(name: str) -> None:
    """Valide un domaine isolément."""
    project_dir = Path.cwd()
    domain_file = project_dir / "domains" / f"{name}.yml"

    if not domain_file.exists():
        typer.echo(f"Fichier introuvable : domains/{name}.yml", err=True)
        raise typer.Exit(1)

    try:
        infra = parse_project(project_dir)
    except ParseError as e:
        typer.echo(f"Erreur de parsing : {e}", err=True)
        raise typer.Exit(1) from None

    if name not in infra.domains:
        typer.echo(f"Domaine '{name}' absent après parsing.", err=True)
        raise typer.Exit(1)

    result = validate(infra)

    # Filtrer les erreurs de ce domaine
    domain_errors = [e for e in result.errors if name in e.location]
    if domain_errors:
        typer.echo(f"{name} : {len(domain_errors)} erreur(s)")
        for err in domain_errors:
            typer.echo(f"  {err}")
        raise typer.Exit(1)

    machine_count = len(infra.domains[name].machines)
    typer.echo(f"{name} : valide ({machine_count} machine(s))")


def run_domain_exec(name: str, cmd: list[str]) -> None:
    """Exécute une commande dans toutes les instances running d'un domaine."""
    infra = load_infra()
    driver = IncusDriver()

    if name not in infra.domains:
        typer.echo(f"Domaine inconnu : {name}", err=True)
        raise typer.Exit(1)

    domain = infra.domains[name]
    if not domain.enabled:
        typer.echo(f"Domaine '{name}' désactivé.", err=True)
        raise typer.Exit(1)

    errors = 0
    for machine in domain.sorted_machines:
        try:
            result = driver.instance_exec(machine.full_name, domain.name, cmd)
            typer.echo(f"{machine.full_name} : OK")
            if result.stdout:
                for line in result.stdout.strip().splitlines():
                    typer.echo(f"  {line}")
        except IncusError:
            typer.echo(f"{machine.full_name} : erreur")
            errors += 1

    if errors:
        raise typer.Exit(1)


def run_domain_status(name: str) -> None:
    """Affiche l'état détaillé d'un seul domaine."""
    infra = load_infra()
    driver = IncusDriver()
    ctx = detect_nesting_context()

    if name not in infra.domains:
        typer.echo(f"Domaine inconnu : {name}", err=True)
        raise typer.Exit(1)

    domain = infra.domains[name]
    if not domain.enabled:
        typer.echo(f"Domaine '{name}' désactivé.", err=True)
        raise typer.Exit(1)

    status = compute_status(infra, driver, nesting_context=ctx, domain_name=name)
    ds = next((d for d in status.domains if d.name == name), None)

    if ds is None:
        typer.echo(f"Domaine '{name}' absent du status.", err=True)
        raise typer.Exit(1)

    proj = "oui" if ds.project_exists else "non"
    net = "oui" if ds.network_exists else "non"
    typer.echo(f"\n{ds.name}:")
    typer.echo(f"  Projet : {proj}    Réseau : {net}")

    for inst in ds.instances:
        if inst.synced:
            tag = "[ok]"
        elif inst.state == "Stopped":
            tag = "[arrêtée]"
        else:
            tag = "[absente]"

        # Trouver l'IP déclarée
        machine = domain.machines.get(inst.name.removeprefix(f"{name}-"))
        ip = machine.ip if machine else "-"
        ip_str = ip or "-"

        typer.echo(
            f"  {inst.name:<20s} {inst.machine_type:<5s} {inst.state:<10s} "
            f"{ip_str:<15s} {tag}"
        )

    running = sum(1 for i in ds.instances if i.synced)
    typer.echo(f"\n{running}/{len(ds.instances)} instances running")
