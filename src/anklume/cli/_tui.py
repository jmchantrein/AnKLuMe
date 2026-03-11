"""Commande CLI pour le TUI interactif."""

from __future__ import annotations

from pathlib import Path


def run_tui(project_dir: str) -> None:
    """Lance le TUI interactif."""
    try:
        from anklume.tui.app import AnklumeTUI
    except ImportError:
        import typer

        typer.echo(
            "Le TUI nécessite textual. Installer avec :\n"
            "  uv pip install textual",
            err=True,
        )
        raise typer.Exit(1) from None

    app = AnklumeTUI(project_dir=Path(project_dir))
    app.run()
