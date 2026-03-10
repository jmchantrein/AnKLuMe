"""Implémentation de `anklume console`."""

from __future__ import annotations

import typer

from anklume.cli._common import load_infra
from anklume.engine.console import (
    SESSION_NAME,
    build_console_config,
    kill_session,
    launch_console,
)
from anklume.engine.incus_driver import IncusDriver


def run_console(
    domain: str | None = None,
    detach: bool = False,
    kill: bool = False,
    dedicated: bool = False,
    status_color: str = "terminal",
) -> None:
    """Lance une console tmux colorée par domaine."""
    driver = IncusDriver()
    infra = load_infra()

    config = build_console_config(infra, driver, domain=domain)
    config.status_color = status_color
    config.dedicated = dedicated

    if not config.windows:
        typer.echo("Aucune instance running trouvée.")
        return

    window_count = len(config.windows)
    pane_count = sum(len(panes) for panes in config.windows.values())
    typer.echo(
        f"Console {config.session_name} : {window_count} fenêtre(s), {pane_count} panneau(x)"
    )

    launch_console(config, detach=detach, kill=kill)


def run_console_kill(domain: str | None = None) -> None:
    """Tue la session tmux anklume."""
    name = f"{SESSION_NAME}-{domain}" if domain else SESSION_NAME
    if kill_session(name):
        typer.echo(f"Session '{name}' tuée.")
    else:
        typer.echo(f"Pas de session '{name}' active.")
