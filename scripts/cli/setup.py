"""anklume setup — initialization and configuration."""

from datetime import datetime
from pathlib import Path

import typer

from scripts.cli._helpers import console, run_make, run_script

app = typer.Typer(name="setup", help="Setup, initialization, and configuration.")


@app.command()
def init() -> None:
    """Install dependencies and Galaxy roles."""
    run_make("init")


@app.command()
def quickstart() -> None:
    """Guided first-time setup."""
    run_script("quickstart.sh")


@app.command()
def shares() -> None:
    """Create host directories for shared volumes."""
    run_make("shares")


@app.command("data-dirs")
def data_dirs() -> None:
    """Create host directories for persistent data."""
    run_make("data-dirs")


@app.command()
def hooks() -> None:
    """Install git hooks."""
    run_make("install-hooks")


@app.command("update-notifier")
def update_notifier() -> None:
    """Install update checker."""
    run_make("install-update-notifier")


@app.command("import")
def import_() -> None:
    """Generate infra.yml from existing Incus state."""
    run_script("import-infra.sh")


@app.command("export-images")
def export_images() -> None:
    """Export images for nested anklume instances."""
    run_make("export-images")


@app.command()
def production(
    off: bool = typer.Option(False, "--off", help="Remove production marker"),
) -> None:
    """Mark/unmark this instance as production (blocks git push)."""
    marker = Path("/etc/anklume/deployed")
    if off:
        if marker.exists():
            marker.unlink()
            console.print("[green]Production mode disabled.[/green]")
        else:
            console.print("[dim]Not in production mode.[/dim]")
    else:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(f"deployed={datetime.now().isoformat()}\n")
        console.print("[bold]Production mode enabled.[/bold]")
        console.print("[dim]git push blocked. Use --off to revert.[/dim]")
