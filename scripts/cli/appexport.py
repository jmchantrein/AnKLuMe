"""anklume app — export container apps to host desktop."""

from typing import Annotated

import typer

from scripts.cli._completions import complete_instance
from scripts.cli._helpers import run_script

app = typer.Typer(name="app", help="Export container applications to host desktop.")


@app.command()
def export(
    instance: Annotated[str, typer.Argument(help="Instance name", autocompletion=complete_instance)],
    application: Annotated[str, typer.Argument(help="Application name (e.g. firefox)")],
) -> None:
    """Export a container app as a host .desktop entry."""
    run_script("export-app.sh", "export", instance, application)


@app.command("list")
def list_(
    instance: Annotated[
        str | None,
        typer.Argument(
            help="Instance (all if omitted)",
            autocompletion=complete_instance,
        ),
    ] = None,
) -> None:
    """List exported apps."""
    args = ["list"]
    if instance:
        args.append(instance)
    run_script("export-app.sh", *args)


@app.command()
def remove(
    instance: Annotated[str, typer.Argument(help="Instance name", autocompletion=complete_instance)],
    application: Annotated[str, typer.Argument(help="Application name to remove")],
) -> None:
    """Remove an exported app."""
    run_script("export-app.sh", "remove", instance, application)
