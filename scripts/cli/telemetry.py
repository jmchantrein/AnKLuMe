"""anklume telemetry — anonymous usage telemetry."""

import typer

from scripts.cli._helpers import run_make

app = typer.Typer(name="telemetry", help="Anonymous usage telemetry.")


@app.command()
def on() -> None:
    """Enable telemetry collection."""
    run_make("telemetry-on")


@app.command()
def off() -> None:
    """Disable telemetry collection."""
    run_make("telemetry-off")


@app.command()
def status() -> None:
    """Show telemetry status."""
    run_make("telemetry-status")


@app.command()
def clear() -> None:
    """Clear collected telemetry data."""
    run_make("telemetry-clear")


@app.command()
def report() -> None:
    """Show telemetry report."""
    run_make("telemetry-report")
