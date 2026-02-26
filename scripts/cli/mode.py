"""anklume mode — switch CLI mode (user/student/dev)."""

import typer

from scripts.cli._helpers import console, get_mode

app = typer.Typer(name="mode", help="Switch CLI mode.", invoke_without_command=True)


@app.callback(invoke_without_command=True)
def show_mode(ctx: typer.Context) -> None:
    """Show or switch CLI mode."""
    if ctx.invoked_subcommand is None:
        current = get_mode()
        console.print(f"Current mode: [bold]{current}[/bold]")


def _set_mode(name: str) -> None:
    from pathlib import Path

    mode_dir = Path.home() / ".anklume"
    mode_dir.mkdir(parents=True, exist_ok=True)
    (mode_dir / "mode").write_text(name + "\n")
    console.print(f"Mode set to [bold]{name}[/bold].")


@app.command()
def user() -> None:
    """Standard mode (default)."""
    _set_mode("user")


@app.command()
def student() -> None:
    """Student mode (bilingual help)."""
    _set_mode("student")


@app.command()
def dev() -> None:
    """Developer mode (all targets visible)."""
    _set_mode("dev")
