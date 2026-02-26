"""anklume ai — AI tools and agent management."""

from typing import Annotated

import typer

from scripts.cli._completions import complete_domain
from scripts.cli._helpers import run_make

app = typer.Typer(name="ai", help="AI tools, agents, and LLM operations.")


@app.command()
def switch(
    domain: Annotated[str, typer.Argument(help="Domain to grant AI access", autocompletion=complete_domain)],
) -> None:
    """Switch exclusive AI access to a domain."""
    run_make("ai-switch", f"D={domain}")


@app.command()
def test(
    role: Annotated[str | None, typer.Option("--role", "-r", help="Test a specific role")] = None,
) -> None:
    """AI-assisted testing."""
    if role:
        run_make("ai-test", f"R={role}")
    else:
        run_make("ai-test")


@app.command()
def develop() -> None:
    """AI-assisted development session."""
    run_make("ai-develop")


@app.command()
def improve() -> None:
    """AI-assisted code improvement."""
    run_make("ai-improve")


@app.command()
def claude(
    resume: Annotated[bool, typer.Option("--resume", help="Resume previous session")] = False,
    audit: Annotated[bool, typer.Option("--audit", help="Run in audit mode")] = False,
) -> None:
    """Launch Claude Code session on host."""
    args = []
    if resume:
        args.append("RESUME=1")
    if audit:
        args.append("AUDIT=1")
    run_make("claude-host", *args)


@app.command("agent-setup")
def agent_setup() -> None:
    """Setup agent runner infrastructure."""
    run_make("agent-setup")


@app.command("agent-fix")
def agent_fix() -> None:
    """Run agent auto-fix cycle."""
    run_make("agent-fix")


@app.command("agent-develop")
def agent_develop() -> None:
    """Start agent development session."""
    run_make("agent-develop")


@app.command("mine-experiences")
def mine_experiences() -> None:
    """Mine agent experiences for improvement."""
    run_make("mine-experiences")
