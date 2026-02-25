"""anklume portal — file transfer between host and instances."""

from typing import Annotated

import typer

from scripts.cli._completions import complete_instance
from scripts.cli._helpers import run_script

app = typer.Typer(name="portal", help="File transfer between host and instances.")


@app.command("open")
def open_(
    instance: Annotated[str, typer.Argument(help="Instance name", autocompletion=complete_instance)],
    path: Annotated[str, typer.Argument(help="File path inside the instance")],
) -> None:
    """Open a file from a container on the host."""
    run_script("file-portal.sh", "open", instance, path)


@app.command()
def push(
    instance: Annotated[str, typer.Argument(help="Target instance", autocompletion=complete_instance)],
    src: Annotated[str, typer.Argument(help="Source path on host")],
    dst: Annotated[str, typer.Argument(help="Destination path in instance")],
) -> None:
    """Push a file from the host to a container."""
    run_script("file-portal.sh", "push", instance, src, dst)


@app.command()
def pull(
    instance: Annotated[str, typer.Argument(help="Source instance", autocompletion=complete_instance)],
    src: Annotated[str, typer.Argument(help="Source path in instance")],
    dst: Annotated[str, typer.Argument(help="Destination path on host")],
) -> None:
    """Pull a file from a container to the host."""
    run_script("file-portal.sh", "pull", instance, src, dst)


@app.command("list")
def list_portals() -> None:
    """List configured file portals."""
    run_script("file-portal.sh", "list")
