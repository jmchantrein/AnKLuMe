"""anklume golden — golden image management."""

from typing import Annotated

import typer

from scripts.cli._helpers import run_make

app = typer.Typer(name="golden", help="Pre-built golden image management.")


@app.command()
def create(
    instance: Annotated[str, typer.Argument(help="Source instance name")],
) -> None:
    """Create a golden image from an instance."""
    run_make("golden-create", f"I={instance}")


@app.command()
def derive(
    image: Annotated[str, typer.Argument(help="Golden image name")],
    name: Annotated[str, typer.Argument(help="New instance name")],
) -> None:
    """Create a new instance from a golden image."""
    run_make("golden-derive", f"IMAGE={image}", f"NAME={name}")


@app.command("list")
def list_() -> None:
    """List available golden images."""
    run_make("golden-list")


@app.command()
def publish(
    image: Annotated[str, typer.Argument(help="Golden image to publish")],
) -> None:
    """Publish a golden image to a remote."""
    run_make("golden-publish", f"IMAGE={image}")
