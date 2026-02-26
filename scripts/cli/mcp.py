"""anklume mcp — MCP (Model Context Protocol) services."""

from typing import Annotated

import typer

from scripts.cli._helpers import run_make

app = typer.Typer(name="mcp", help="MCP (Model Context Protocol) services.")


@app.command("list")
def list_() -> None:
    """List available MCP tools."""
    run_make("mcp-list")


@app.command()
def call(
    tool: Annotated[str, typer.Argument(help="MCP tool name to call")],
) -> None:
    """Call an MCP tool."""
    run_make("mcp-call", f"TOOL={tool}")
