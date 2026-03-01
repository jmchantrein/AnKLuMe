"""anklume learn — interactive learning platform commands."""

from typing import Annotated

import typer

from scripts.cli._helpers import PROJECT_ROOT, run_cmd, run_script

app = typer.Typer(
    name="learn",
    help="Interactive learning platform (guide + labs).",
)


@app.command()
def start(
    port: Annotated[int, typer.Option(help="Server port")] = 8890,
    host: Annotated[str, typer.Option(help="Bind address")] = "127.0.0.1",
) -> None:
    """Start the learning platform."""
    run_cmd([
        "python3",
        str(PROJECT_ROOT / "scripts" / "platform_server.py"),
        "--port", str(port),
        "--host", host,
    ])


@app.command()
def setup() -> None:
    """Create the anklume-learn container and demo infrastructure."""
    run_script("learn-setup.sh")


@app.command()
def teardown() -> None:
    """Destroy the anklume-learn container and learn project."""
    run_script("learn-setup.sh", "teardown")
