"""anklume setup — initialization and configuration."""

import typer

from scripts.cli._helpers import run_make, run_script

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
