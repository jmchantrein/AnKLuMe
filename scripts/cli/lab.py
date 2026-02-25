"""anklume lab — educational labs."""

from typing import Annotated

import typer

from scripts.cli._completions import complete_lab
from scripts.cli._helpers import run_script

app = typer.Typer(name="lab", help="Educational labs and guided exercises.")


@app.command("list")
def list_() -> None:
    """List available labs."""
    run_script("lab-runner.sh", "list")


@app.command()
def start(
    lab: Annotated[str, typer.Argument(help="Lab ID (e.g. 01)", autocompletion=complete_lab)],
) -> None:
    """Start a lab, display first step."""
    run_script("lab-runner.sh", "start", lab)


@app.command()
def check(
    lab: Annotated[str, typer.Argument(help="Lab ID", autocompletion=complete_lab)],
) -> None:
    """Validate current step of a lab."""
    run_script("lab-runner.sh", "check", lab)


@app.command()
def hint(
    lab: Annotated[str, typer.Argument(help="Lab ID", autocompletion=complete_lab)],
) -> None:
    """Show hint for the current step."""
    run_script("lab-runner.sh", "hint", lab)


@app.command()
def reset(
    lab: Annotated[str, typer.Argument(help="Lab ID", autocompletion=complete_lab)],
) -> None:
    """Reset lab progress."""
    run_script("lab-runner.sh", "reset", lab)


@app.command()
def solution(
    lab: Annotated[str, typer.Argument(help="Lab ID", autocompletion=complete_lab)],
) -> None:
    """Show solution (marks lab as assisted)."""
    run_script("lab-runner.sh", "solution", lab)
