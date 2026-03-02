"""anklume stt — Speech-to-Text service management."""

from typing import Annotated

import typer

from scripts.cli._helpers import run_script

app = typer.Typer(name="stt", help="STT service (Speaches/Whisper) management.")


@app.command()
def status() -> None:
    """Show STT service status, health, and VRAM usage."""
    run_script("stt-diag.sh", "status")


@app.command()
def restart() -> None:
    """Restart STT: unload Ollama models, restart Speaches."""
    run_script("stt-diag.sh", "restart")


@app.command()
def logs(
    lines: Annotated[
        int, typer.Option("--lines", "-n", help="Number of log lines")
    ] = 50,
) -> None:
    """Show recent STT service logs."""
    run_script("stt-diag.sh", "logs", str(lines))


@app.command()
def test() -> None:
    """Quick health check of STT endpoints."""
    run_script("stt-diag.sh", "test")
