"""anklume domain — manage infrastructure domains."""

from typing import Annotated

import typer
from rich.table import Table

from scripts.cli._completions import complete_domain
from scripts.cli._helpers import PROJECT_ROOT, console, load_infra_safe, run_cmd, run_make

app = typer.Typer(name="domain", help="Manage infrastructure domains.")


@app.command("list")
def list_() -> None:
    """List all domains from infra.yml."""
    infra = load_infra_safe()
    domains = infra.get("domains") or {}
    if not domains:
        console.print("[yellow]No domains defined in infra.yml.[/yellow]")
        raise typer.Exit(0)

    table = Table(title="Domains")
    table.add_column("Name", style="cyan")
    table.add_column("Trust Level", style="magenta")
    table.add_column("Enabled", style="green")
    table.add_column("Machines", justify="right")
    table.add_column("Description")

    for name, conf in domains.items():
        enabled = conf.get("enabled", True)
        trust = conf.get("trust_level", "-")
        machines = conf.get("machines") or {}
        table.add_row(
            name,
            str(trust),
            "yes" if enabled else "[red]no[/red]",
            str(len(machines)),
            conf.get("description", ""),
        )
    console.print(table)


@app.command()
def apply(
    domain: Annotated[
        str | None,
        typer.Argument(
            help="Domain to apply (all if omitted)",
            autocompletion=complete_domain,
        ),
    ] = None,
    all_: Annotated[
        bool, typer.Option("--all", help="Apply all domains")
    ] = False,
    tags: Annotated[
        str | None,
        typer.Option(
            "--tags", "-t",
            help="Ansible tags (infra, provision, llm, stt, ai, openclaw, base, images, code-sandbox)",
        ),
    ] = None,
) -> None:
    """Apply infrastructure for a domain (or all)."""
    cmd = ["ansible-playbook", str(PROJECT_ROOT / "site.yml")]
    if domain and not all_:
        cmd.extend(["--limit", domain])
    if tags:
        cmd.extend(["--tags", tags])
    run_cmd(cmd)


@app.command()
def check(
    domain: Annotated[
        str | None,
        typer.Argument(
            help="Domain to check (all if omitted)",
            autocompletion=complete_domain,
        ),
    ] = None,
) -> None:
    """Dry-run: preview changes without applying."""
    cmd = ["ansible-playbook", str(PROJECT_ROOT / "site.yml"), "--check", "--diff"]
    if domain:
        cmd.extend(["--limit", domain])
    run_cmd(cmd)


@app.command("exec")
def exec_(
    domain: Annotated[str, typer.Argument(help="Domain name", autocompletion=complete_domain)],
    command: Annotated[list[str], typer.Argument(help="Command to execute")],
) -> None:
    """Execute a command in all instances of a domain."""
    run_make("domain-exec", f"D={domain}", f"CMD={' '.join(command)}")


@app.command()
def status(
    domain: Annotated[str | None, typer.Argument(help="Domain to check", autocompletion=complete_domain)] = None,
) -> None:
    """Show running status of instances in a domain."""
    infra = load_infra_safe()
    domains = infra.get("domains") or {}

    targets = [domain] if domain else list(domains.keys())
    for d in targets:
        if d not in domains:
            console.print(f"[red]Unknown domain:[/red] {d}")
            raise typer.Exit(1)
        console.print(f"\n[bold cyan]{d}[/bold cyan]")
        # Use incus list with project filter
        project = d
        # Check for nesting prefix in group_vars
        gv = PROJECT_ROOT / "group_vars" / f"{d}.yml"
        if gv.is_file():
            import yaml

            with open(gv) as f:
                gvars = yaml.safe_load(f) or {}
            project = gvars.get("incus_project", d)
        run_cmd(["incus", "list", "--project", project, "--format", "table"], check=False)
