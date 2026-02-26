"""anklume backup — instance backup and restore."""

from typing import Annotated

import typer

from scripts.cli._completions import complete_instance
from scripts.cli._helpers import run_make

app = typer.Typer(name="backup", help="Instance backup and restore.")


@app.command()
def create(
    instance: Annotated[str, typer.Argument(help="Instance to backup", autocompletion=complete_instance)],
) -> None:
    """Create a full backup of an instance."""
    run_make("backup", f"I={instance}")


@app.command()
def restore(
    instance: Annotated[str, typer.Argument(help="Instance to restore", autocompletion=complete_instance)],
) -> None:
    """Restore an instance from backup."""
    run_make("restore-backup", f"I={instance}")
