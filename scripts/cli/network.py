"""anklume network — network isolation and rules."""

import typer

from scripts.cli._helpers import PROJECT_ROOT, console, run_cmd, run_script

app = typer.Typer(name="network", help="Network isolation and nftables rules.")


@app.command()
def status() -> None:
    """Check network health and bridge status."""
    run_script("doctor.sh", "CHECK=network")


@app.command()
def rules() -> None:
    """Generate nftables isolation rules (preview)."""
    run_cmd(["python3", str(PROJECT_ROOT / "scripts" / "nftables-gen.py"), str(PROJECT_ROOT / "infra.yml")])


@app.command()
def deploy() -> None:
    """Deploy nftables rules on the host. Must run FROM the host."""
    console.print("[yellow]This command must run on the host, not inside a container.[/yellow]")
    run_script("deploy-nftables.sh")
