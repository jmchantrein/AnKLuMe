"""Exécution des tests Molecule pour les rôles Ansible."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import typer

from anklume.provisioner import BUILTIN_ROLES_DIR


def _get_roles_with_molecule() -> list[Path]:
    """Liste les rôles ayant un scénario Molecule."""
    roles = []
    for role_dir in sorted(BUILTIN_ROLES_DIR.iterdir()):
        if (role_dir / "molecule" / "default" / "molecule.yml").is_file():
            roles.append(role_dir)
    return roles


def run_molecule(
    role: str = "",
    scenario: str = "default",
    command: str = "test",
) -> None:
    """Lance Molecule sur un ou tous les rôles."""
    roles = _get_roles_with_molecule()

    if not roles:
        typer.echo("Aucun rôle avec scénario Molecule trouvé.")
        raise typer.Exit(1)

    if role:
        matching = [r for r in roles if r.name == role]
        if not matching:
            available = ", ".join(r.name for r in roles)
            typer.echo(f"Rôle '{role}' introuvable. Disponibles : {available}")
            raise typer.Exit(1)
        roles = matching

    failed: list[str] = []

    for role_dir in roles:
        typer.echo(f"\n{'=' * 60}")
        typer.echo(f"  Molecule {command} — {role_dir.name}")
        typer.echo(f"{'=' * 60}\n")

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "molecule",
                command,
                "--scenario-name",
                scenario,
            ],
            cwd=str(role_dir),
        )

        if result.returncode != 0:
            failed.append(role_dir.name)

    if failed:
        typer.echo(f"\nÉchecs Molecule : {', '.join(failed)}")
        raise typer.Exit(1)

    typer.echo(f"\nTous les tests Molecule passent ({len(roles)} rôles).")
