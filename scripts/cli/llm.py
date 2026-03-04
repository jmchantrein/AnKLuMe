"""anklume llm — LLM backend management."""

import sys
from pathlib import Path
from typing import Annotated

import typer

from scripts.cli._helpers import console, run_make, run_script

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


@app.command()
def sanitize(
    text: Annotated[str | None, typer.Option("--text", "-t", help="Text to sanitize (or stdin)")] = None,
    file: Annotated[Path | None, typer.Option("--file", "-f", help="File to sanitize")] = None,
    patterns: Annotated[Path | None, typer.Option("--patterns", "-p", help="Custom patterns file")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="JSON output with redaction details")] = False,
) -> None:
    """Dry-run sanitizer: show what would be redacted without sending."""
    from scripts.sanitizer_dryrun import apply_patterns, format_diff, load_patterns

    pat = load_patterns(str(patterns) if patterns else None)
    if not pat:
        console.print("[red]No patterns found.[/red]")
        raise typer.Exit(1)

    # Read input
    if file:
        input_text = file.read_text()
    elif text:
        input_text = text
    elif not sys.stdin.isatty():
        input_text = sys.stdin.read()
    else:
        console.print("[red]Provide text as argument, --file, or stdin.[/red]")
        raise typer.Exit(1)

    sanitized, redactions = apply_patterns(input_text, pat)

    if json_output:
        import json
        console.print_json(json.dumps({
            "original": input_text,
            "sanitized": sanitized,
            "redactions": redactions,
            "count": len(redactions),
        }))
    else:
        console.print(format_diff(input_text, sanitized, redactions))


@app.command("patterns")
def patterns_cmd(
    category: Annotated[str | None, typer.Argument(help="Filter by category")] = None,
    test: Annotated[str | None, typer.Option("--test", "-t", help="Test string against patterns")] = None,
) -> None:
    """List sanitization patterns or test a string against them."""
    from rich.table import Table

    from scripts.sanitizer_dryrun import apply_patterns, load_patterns, pattern_stats

    pat = load_patterns()
    if not pat:
        console.print("[red]No patterns found.[/red]")
        raise typer.Exit(1)

    if test:
        sanitized, redactions = apply_patterns(test, pat)
        if redactions:
            table = Table(title="Matching Patterns")
            table.add_column("Category")
            table.add_column("Pattern")
            table.add_column("Matched")
            table.add_column("Replacement")
            for r in redactions:
                table.add_row(r["category"], r["name"], r["original"], r["replacement"])
            console.print(table)
        else:
            console.print("[green]No patterns matched.[/green]")
        return

    # List patterns
    filtered = pat if not category else [p for p in pat if p["category"] == category]
    if not filtered:
        console.print(f"[yellow]No patterns in category '{category}'.[/yellow]")
        raise typer.Exit(1)

    stats = pattern_stats(pat)
    console.print(f"[bold]{len(pat)} patterns in {len(stats)} categories[/bold]\n")

    table = Table(title="Sanitization Patterns")
    table.add_column("Category")
    table.add_column("Name")
    table.add_column("Description")
    table.add_column("Regex", overflow="fold")
    for p in filtered:
        table.add_row(p["category"], p["name"], p["description"], p["pattern"])
    console.print(table)
