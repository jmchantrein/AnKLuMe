"""Implémentation de `anklume network rules` et `anklume network deploy`."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import typer

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
