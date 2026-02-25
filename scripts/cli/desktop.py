"""anklume desktop — desktop integration and theming."""

from typing import Annotated

import typer

from scripts.cli._helpers import run_script

app = typer.Typer(name="desktop", help="Desktop integration (Sway/Hyprland/i3 theming).")


@app.command()
def apply(
    engine: Annotated[str, typer.Option("--engine", "-e", help="Desktop engine")] = "sway",
) -> None:
    """Apply desktop configuration from infra.yml."""
    run_script("desktop-plugin.sh", "apply", f"--engine={engine}")


@app.command()
def reset(
    engine: Annotated[str, typer.Option("--engine", "-e", help="Desktop engine")] = "sway",
) -> None:
    """Reset desktop configuration to defaults."""
    run_script("desktop-plugin.sh", "reset", f"--engine={engine}")


@app.command()
def plugins() -> None:
    """List available desktop plugins."""
    run_script("desktop-plugin.sh", "list")
