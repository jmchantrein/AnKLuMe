"""anklume llm — LLM backend management."""

from typing import Annotated

import typer

from scripts.cli._helpers import run_make, run_script

app = typer.Typer(name="llm", help="LLM backend management (Ollama).")


@app.command()
def status() -> None:
    """Show active LLM backend, model, and VRAM usage."""
    run_script("llm-switch.sh", "status")


@app.command()
def switch(
    model: Annotated[str | None, typer.Option("--model", "-m", help="Model to switch to")] = None,
) -> None:
    """Switch LLM model."""
    args = ["switch"]
    if model:
        args.extend(["--model", model])
    run_script("llm-switch.sh", *args)


@app.command()
def bench(
    model: Annotated[str | None, typer.Option("--model", "-m", help="Model to benchmark")] = None,
    compare: Annotated[bool, typer.Option("--compare", help="Compare multiple models")] = False,
) -> None:
    """Benchmark LLM inference speed."""
    args = []
    if model:
        args.extend([f"MODEL={model}"])
    if compare:
        args.append("COMPARE=1")
    run_script("llm-bench.sh", *args)


@app.command()
def dev() -> None:
    """Interactive LLM development assistant."""
    run_make("llm-dev")
