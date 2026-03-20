"""Implémentation des commandes `anklume network`."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import typer
import yaml

from anklume.cli._common import load_infra
from anklume.engine.nftables import generate_ruleset


def run_network_rules() -> None:
    """Génère et affiche les règles nftables sur stdout."""
    infra = load_infra()
    ruleset = generate_ruleset(infra)
    typer.echo(ruleset)


def run_network_deploy() -> None:
    """Applique les règles nftables sur l'hôte via nft -f."""
    if not shutil.which("nft"):
        typer.echo(
            "Erreur : nft introuvable. Installer nftables sur l'hôte.",
            err=True,
        )
        raise typer.Exit(1)

    infra = load_infra()
    ruleset = generate_ruleset(infra)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".nft", delete=False) as tmp:
        tmp.write(ruleset)
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            ["nft", "-f", tmp_path],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            typer.echo(f"Erreur nftables : {result.stderr.strip()}", err=True)
            raise typer.Exit(1)

        typer.echo("Règles nftables appliquées.")
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def run_network_status() -> None:
    """Affiche l'état réseau : bridges, IPs, nftables."""
    from anklume.engine.incus_driver import IncusDriver
    from anklume.engine.nesting import detect_nesting_context
    from anklume.engine.ops import compute_network_status

    infra = load_infra()
    driver = IncusDriver()
    ctx = detect_nesting_context()

    status = compute_network_status(infra, driver, nesting_context=ctx)

    if not status.networks:
        typer.echo("Aucun réseau déclaré.")
        return

    typer.echo(f"{'DOMAINE':<12s} {'BRIDGE':<15s} {'SUBNET':<18s} {'GATEWAY':<15s} {'ÉTAT'}")
    for net in status.networks:
        subnet = net.subnet or "-"
        gateway = net.gateway or "-"
        etat = "actif" if net.exists else "absent"
        typer.echo(f"{net.domain:<12s} {net.bridge:<15s} {subnet:<18s} {gateway:<15s} {etat}")

    if status.nftables_present:
        typer.echo(
            f"\nnftables : table inet anklume présente ({status.nftables_rule_count} règle(s))"
        )
    else:
        typer.echo("\nnftables : table inet anklume absente")

    # Afficher l'état du passthrough
    passthrough = infra.config.network_passthrough
    label = "activé" if passthrough else "désactivé"
    typer.echo(f"passthrough bridges externes : {label}")


def run_network_passthrough(enable: bool) -> None:
    """Active ou désactive le passthrough des bridges non-anklume."""
    config_path = Path.cwd() / "anklume.yml"
    if not config_path.exists():
        typer.echo("Erreur : anklume.yml introuvable.", err=True)
        raise typer.Exit(1)

    raw = yaml.safe_load(config_path.read_text()) or {}
    raw["network_passthrough"] = enable
    config_path.write_text(yaml.dump(raw, default_flow_style=False, sort_keys=False))

    label = "activé" if enable else "désactivé"
    typer.echo(f"Passthrough bridges externes {label}.")
    typer.echo("Appliquer avec : anklume network deploy")
