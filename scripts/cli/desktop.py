"""anklume desktop — KDE Plasma desktop integration."""

import typer

from scripts.cli._helpers import run_script

app = typer.Typer(name="desktop", help="KDE Plasma desktop integration.")


@app.command()
def apply() -> None:
    """Apply desktop configuration from infra.yml."""
    run_script("desktop-plugin.sh", "apply", "--engine=kde")


@app.command()
def reset() -> None:
    """Reset desktop configuration to defaults."""
    run_script("desktop-plugin.sh", "reset", "--engine=kde")


@app.command()
def plugins() -> None:
    """List available desktop plugins."""
    run_script("desktop-plugin.sh", "list")
