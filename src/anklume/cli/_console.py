"""Implémentation de `anklume console`."""

from __future__ import annotations

import typer

from anklume.engine.console import build_console_config, launch_console
from anklume.engine.incus_driver import IncusDriver
from anklume.engine.parser import load_infrastructure


def run_console(domain: str | None = None, detach: bool = False) -> None:
    """Lance une console tmux colorée par domaine."""
    driver = IncusDriver()
    infra = load_infrastructure()

    config = build_console_config(infra, driver, domain=domain)

    if not config.windows:
        typer.echo("Aucune instance running trouvée.")
        return

    window_count = len(config.windows)
    pane_count = sum(len(panes) for panes in config.windows.values())
    typer.echo(
        f"Console {config.session_name} : "
        f"{window_count} fenêtre(s), {pane_count} panneau(x)"
    )

    launch_console(config, detach=detach)
