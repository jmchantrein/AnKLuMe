"""anklume system — Host system monitoring and management."""

from typing import Annotated

import typer

from scripts.cli._helpers import console

app = typer.Typer(name="system", help="Host system monitoring.")


@app.command()
def resources(
    output: Annotated[
        str, typer.Option("--output", "-o", help="Output: cli, web, tmux, all")
    ] = "cli",
    watch: Annotated[
        bool, typer.Option("--watch", "-w", help="Continuous refresh (2s)")
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="JSON output")
    ] = False,
) -> None:
    """Show host resource usage (CPU, RAM, disk, GPU/VRAM, LLM models)."""
    import time

    from scripts.host_resources import collect_all
    from scripts.host_resources_render import render_cli, render_tmux

    targets = output.split(",") if "," in output else [output]
    if "all" in targets:
        targets = ["cli", "web", "tmux"]

    while True:
        data = collect_all()

        if "cli" in targets:
            render_cli(data, json_output=json_output)
        if "tmux" in targets:
            render_tmux(data)
        if "web" in targets:
            from scripts.host_resources_render import render_dashboard_data
            console.print(render_dashboard_data(data))

        if not watch:
            break
        time.sleep(2)
