"""Sync command implementation — generate Ansible files from infra.yml."""

import sys
from pathlib import Path

import typer

from scripts.cli._helpers import PROJECT_ROOT, console


def run_sync(dry_run: bool = False, clean: bool = False) -> None:
    """Generate/update Ansible files from infra.yml."""
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    from generate import (  # noqa: E402
        detect_orphans,
        enrich_infra,
        generate,
        get_warnings,
        load_infra,
        validate,
    )

    infra_path = str(PROJECT_ROOT / "infra.yml")
    if (PROJECT_ROOT / "infra").is_dir():
        infra_path = str(PROJECT_ROOT / "infra")

    try:
        infra = load_infra(infra_path)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None

    errors = validate(infra)
    if errors:
        console.print("[red]Validation errors:[/red]")
        for err in errors:
            console.print(f"  - {err}")
        raise typer.Exit(1)

    try:
        enrich_infra(infra)
    except ValueError as e:
        console.print(f"[red]Enrichment error:[/red] {e}")
        raise typer.Exit(1) from None

    post_errors = validate(infra, check_host_subnets=False)
    if post_errors:
        console.print("[red]Post-enrichment errors:[/red]")
        for err in post_errors:
            console.print(f"  - {err}")
        raise typer.Exit(1)

    for w in get_warnings(infra):
        console.print(f"[yellow]WARNING:[/yellow] {w}")

    domains = infra.get("domains") or {}
    enabled = sum(
        1 for d in domains.values()
        if d.get("enabled", True) is not False
    )
    prefix = "[DRY-RUN] " if dry_run else ""
    console.print(f"{prefix}Generating files for {enabled} domain(s)...")

    written = generate(infra, str(PROJECT_ROOT), dry_run)
    for fp in written:
        label = "Would write" if dry_run else "Written"
        console.print(f"  {prefix}{label}: {fp}")

    orphans = detect_orphans(infra, str(PROJECT_ROOT))
    if orphans:
        console.print(f"\nOrphan files ({len(orphans)}):")
        for filepath, is_protected in orphans:
            if is_protected:
                console.print(
                    f"  [red]PROTECTED[/red] (ephemeral=false): {filepath}"
                )
            else:
                console.print(f"  ORPHAN: {filepath}")
        if clean and not dry_run:
            for filepath, is_protected in orphans:
                if is_protected:
                    console.print(f"  Skipped (protected): {filepath}")
                else:
                    Path(filepath).unlink()
                    console.print(f"  Deleted: {filepath}")

    if not dry_run:
        console.print(
            "\nDone. Run [bold]anklume dev lint[/bold] to validate."
        )
