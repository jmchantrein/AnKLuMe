"""anklume docs — documentation build and serve."""

import typer

from scripts.cli._helpers import run_make

app = typer.Typer(name="docs", help="Documentation (MkDocs Material).")


@app.command()
def build() -> None:
    """Build documentation site."""
    run_make("docs")


@app.command()
def serve() -> None:
    """Serve documentation locally with live reload."""
    run_make("docs-serve")
