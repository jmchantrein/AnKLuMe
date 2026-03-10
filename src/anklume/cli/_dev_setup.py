"""Implémentation de `anklume dev setup`."""

from __future__ import annotations

from pathlib import Path

import typer

from anklume.engine.dev_setup import run_dev_setup


def run_dev_setup_cmd() -> None:
    """Prépare l'environnement de développement anklume."""
    # Trouver la racine du projet (remonte jusqu'à trouver pyproject.toml)
    project_root = _find_project_root()
    if not project_root:
        typer.echo("Impossible de trouver la racine du projet (pyproject.toml).", err=True)
        raise typer.Exit(1)

    typer.echo(f"Préparation de l'environnement de développement ({project_root})...\n")

    report = run_dev_setup(project_root=project_root)

    status_icons = {"ok": "✓", "warning": "⚠", "error": "✗"}

    for step in report.steps:
        icon = status_icons.get(step.status, "?")
        suffix = " (déjà fait)" if step.skipped else ""
        typer.echo(f"{icon} {step.name:<25s} {step.message}{suffix}")

    typer.echo(
        f"\nRésultat : {report.ok_count} ok, "
        f"{report.warning_count} warning, "
        f"{report.error_count} erreur"
    )

    if not report.success:
        raise typer.Exit(1)


def _find_project_root() -> Path | None:
    """Remonte l'arborescence pour trouver pyproject.toml."""
    current = Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    return None
