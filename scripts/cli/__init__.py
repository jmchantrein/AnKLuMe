"""anklume CLI — Docker-style command interface for anklume."""

from typing import Annotated

import typer

from scripts.cli._helpers import (
    console,
    get_mode,
    run_script,
)
from scripts.cli.appexport import app as appexport_app
from scripts.cli.desktop import app as desktop_app
from scripts.cli.dev import app as dev_app
from scripts.cli.domain import app as domain_app
from scripts.cli.instance import app as instance_app
from scripts.cli.lab import app as lab_app
from scripts.cli.llm import app as llm_app
from scripts.cli.network import app as network_app
from scripts.cli.portal import app as portal_app
from scripts.cli.snapshot import app as snapshot_app

__version__ = "0.1.0"

app = typer.Typer(
    name="anklume",
    help="Declarative infrastructure compartmentalization framework.",
    rich_markup_mode="rich",
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"anklume {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version", "-V",
            help="Show version",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = None,
) -> None:
    """anklume — QubesOS-like isolation with Ansible + Incus."""


# ── Top-level commands ─────────────────────────────────────


@app.command()
def sync(
    dry_run: Annotated[
        bool, typer.Option("--dry-run", "-n", help="Preview without writing")
    ] = False,
    clean: Annotated[
        bool, typer.Option("--clean", help="Remove orphan files")
    ] = False,
) -> None:
    """Generate/update Ansible files from infra.yml."""
    from scripts.cli._sync import run_sync

    run_sync(dry_run=dry_run, clean=clean)


@app.command()
def flush(
    force: Annotated[
        bool, typer.Option("--force", help="Force destruction")
    ] = False,
) -> None:
    """Destroy all anklume infrastructure."""
    if force:
        run_script("flush.sh", "FORCE=true")
    else:
        run_script("flush.sh")


@app.command()
def upgrade() -> None:
    """Safe framework update with conflict detection."""
    run_script("upgrade.sh")


@app.command()
def guide() -> None:
    """Interactive onboarding guide."""
    run_script("guide.sh")


@app.command()
def doctor() -> None:
    """Diagnose infrastructure health."""
    run_script("doctor.sh")


@app.command("console")
def console_cmd() -> None:
    """Launch tmux console with domain-colored panes."""
    run_script("console.sh")


# ── Register command groups ────────────────────────────────

app.add_typer(domain_app)
app.add_typer(instance_app)
app.add_typer(snapshot_app)
app.add_typer(network_app)
app.add_typer(portal_app)
app.add_typer(appexport_app)
app.add_typer(desktop_app)
app.add_typer(llm_app)
app.add_typer(lab_app)

# dev group: only visible in dev mode
if get_mode() == "dev":
    dev_app.info.hidden = False
app.add_typer(dev_app)
