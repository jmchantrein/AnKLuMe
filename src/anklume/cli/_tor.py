"""Implémentation de `anklume tor`."""

from __future__ import annotations

import typer

from anklume.engine.parser import load_infrastructure
from anklume.engine.tor import find_tor_gateways, validate_tor_config


def run_tor_status() -> None:
    """Affiche l'état des passerelles Tor."""
    infra = load_infrastructure()

    # Validation
    errors = validate_tor_config(infra)
    for err in errors:
        typer.echo(f"⚠ {err}", err=True)

    # Détection
    gateways = find_tor_gateways(infra)

    if not gateways:
        typer.echo("Aucune passerelle Tor configurée.")
        return

    typer.echo(f"{'INSTANCE':<25s} {'DOMAINE':<15s} {'TRANS':<8s} {'DNS':<8s} {'SOCKS'}")
    for gw in gateways:
        typer.echo(
            f"{gw.instance:<25s} {gw.domain:<15s} "
            f"{gw.trans_port:<8d} {gw.dns_port:<8d} {gw.socks_port}"
        )

    typer.echo(f"\n{len(gateways)} passerelle(s) Tor")
