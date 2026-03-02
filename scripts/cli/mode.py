"""anklume mode — switch CLI mode (user/student/dev) and accessibility settings."""

from pathlib import Path
from typing import Annotated

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


@app.command("learn-incus")
def learn_incus(
    state: Annotated[str, typer.Argument(help="on or off")] = "",
) -> None:
    """Toggle Incus command display (learning mode)."""
    mode_dir = Path.home() / ".anklume"
    learn_file = mode_dir / "learn_incus"

    if not state:
        # Show current state
        try:
            current = learn_file.read_text().strip()
        except FileNotFoundError:
            current = "off"
        console.print(f"Incus learning mode: [bold]{current}[/bold]")
        return

    if state not in ("on", "off"):
        console.print("[red]Must be 'on' or 'off'[/red]")
        raise typer.Exit(1)

    mode_dir.mkdir(parents=True, exist_ok=True)
    learn_file.write_text(state + "\n")
    # Reset the cache so changes take effect immediately
    from scripts.cli import _helpers
    _helpers._learn_incus_cache = None

    console.print(f"Incus learning mode: [bold]{state}[/bold]")
    if state == "on":
        console.print("[dim]All incus commands will be shown before execution.[/dim]")


@app.command()
def accessibility(
    palette: Annotated[
        str | None,
        typer.Option(
            "--palette", "-p",
            help="Color palette: default, colorblind-deutan, colorblind-protan, colorblind-tritan, high-contrast",
        ),
    ] = None,
    tmux_coloring: Annotated[
        str | None,
        typer.Option("--tmux-coloring", help="Tmux coloring: full or title-only"),
    ] = None,
    dyslexia: Annotated[
        bool | None,
        typer.Option("--dyslexia/--no-dyslexia", help="Enable/disable dyslexia-friendly mode"),
    ] = None,
    show: Annotated[
        bool,
        typer.Option("--show", help="Show current accessibility settings"),
    ] = False,
) -> None:
    """Configure accessibility settings (colors, dyslexia mode)."""
    from scripts.accessibility import load_accessibility, save_accessibility

    settings = load_accessibility()

    if show or (palette is None and tmux_coloring is None and dyslexia is None):
        console.print("[bold]Accessibility settings:[/bold]")
        console.print(f"  Palette: [cyan]{settings['color_palette']}[/cyan]")
        console.print(f"  Tmux coloring: [cyan]{settings['tmux_coloring']}[/cyan]")
        console.print(f"  Dyslexia mode: [cyan]{settings['dyslexia_mode']}[/cyan]")
        return

    valid_palettes = ("default", "colorblind-deutan", "colorblind-protan", "colorblind-tritan", "high-contrast")
    if palette is not None:
        if palette not in valid_palettes:
            console.print(f"[red]Invalid palette.[/red] Choose from: {', '.join(valid_palettes)}")
            raise typer.Exit(1)
        settings["color_palette"] = palette

    if tmux_coloring is not None:
        if tmux_coloring not in ("full", "title-only"):
            console.print("[red]Invalid tmux-coloring.[/red] Choose: full, title-only")
            raise typer.Exit(1)
        settings["tmux_coloring"] = tmux_coloring

    if dyslexia is not None:
        settings["dyslexia_mode"] = dyslexia

    save_accessibility(settings)
    console.print("[green]Accessibility settings updated.[/green]")
