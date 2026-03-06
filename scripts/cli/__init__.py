"""anklume CLI — Docker-style command interface for anklume."""

from typing import Annotated

import typer

from scripts.cli._helpers import (
    console,
    get_mode,
    is_host,
    run_make,
    run_script,
)
from scripts.cli.ai import app as ai_app
from scripts.cli.appexport import app as appexport_app
from scripts.cli.backup import app as backup_app
from scripts.cli.desktop import app as desktop_app
from scripts.cli.dev import app as dev_app
from scripts.cli.docs_cmd import app as docs_app
from scripts.cli.domain import app as domain_app
from scripts.cli.golden import app as golden_app
from scripts.cli.instance import app as instance_app
from scripts.cli.lab import app as lab_app
from scripts.cli.learn import app as learn_app
from scripts.cli.live import app as live_app
from scripts.cli.llm import app as llm_app
from scripts.cli.mcp import app as mcp_app
from scripts.cli.mode import app as mode_app
from scripts.cli.network import app as network_app
from scripts.cli.portal import app as portal_app
from scripts.cli.setup import app as setup_app
from scripts.cli.snapshot import app as snapshot_app
from scripts.cli.stt import app as stt_app
from scripts.cli.system import app as system_app
from scripts.cli.telemetry import app as telemetry_app

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
def init(
    lang: Annotated[
        str, typer.Option("--lang", "-l", help="Language (en/fr)")
    ] = "en",
) -> None:
    """Create a starter infra.yml in the current directory."""
    from pathlib import Path

    infra_path = Path("infra.yml")
    if infra_path.exists():
        console.print(f"[yellow]infra.yml already exists at {infra_path.resolve()}[/yellow]")
        raise typer.Exit(0)

    if lang == "fr":
        content = (
            "# infra.yml — Source de verite de votre infrastructure\n"
            "# Modifiez ce fichier puis: anklume sync && anklume domain apply\n\n"
            "project_name: mon-infra\n\n"
            "global:\n"
            "  addressing:\n"
            "    base_octet: 10\n"
            "    zone_base: 100\n"
            '  default_os_image: "images:debian/13"\n\n'
            "domains:\n"
            "  pro:\n"
            '    description: "Espace professionnel"\n'
            "    trust_level: semi-trusted\n"
            "    machines:\n"
            "      pro-dev:\n"
            '        description: "Developpement"\n'
            "        type: lxc\n"
            "        roles: [base_system]\n\n"
            "  perso:\n"
            '    description: "Espace personnel"\n'
            "    trust_level: trusted\n"
            "    machines:\n"
            "      perso-desktop:\n"
            '        description: "Bureau personnel"\n'
            "        type: lxc\n"
            "        roles: [base_system]\n"
        )
    else:
        content = (
            "# infra.yml — Source of truth for your infrastructure\n"
            "# Edit this file then: anklume sync && anklume domain apply\n\n"
            "project_name: my-infra\n\n"
            "global:\n"
            "  addressing:\n"
            "    base_octet: 10\n"
            "    zone_base: 100\n"
            '  default_os_image: "images:debian/13"\n\n'
            "domains:\n"
            "  work:\n"
            '    description: "Professional workspace"\n'
            "    trust_level: semi-trusted\n"
            "    machines:\n"
            "      work-dev:\n"
            '        description: "Development"\n'
            "        type: lxc\n"
            "        roles: [base_system]\n\n"
            "  personal:\n"
            '    description: "Personal space"\n'
            "    trust_level: trusted\n"
            "    machines:\n"
            "      personal-desktop:\n"
            '        description: "Personal desktop"\n'
            "        type: lxc\n"
            "        roles: [base_system]\n"
        )

    infra_path.write_text(content)
    console.print(f"[green]Created {infra_path.resolve()}[/green]")


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
def doctor() -> None:
    """Diagnose infrastructure health."""
    run_script("doctor.sh")


@app.command("console")
def console_cmd() -> None:
    """Launch tmux console with domain-colored panes."""
    run_script("console.sh")


@app.command()
def gui() -> None:
    """Start the desktop environment."""
    import subprocess

    from scripts.cli._helpers import PROJECT_ROOT

    script = PROJECT_ROOT / "host" / "boot" / "desktop" / "start-desktop.sh"
    if not script.exists():
        console.print("[red]start-desktop.sh not found (not on live ISO?).[/red]")
        raise typer.Exit(1)
    try:
        subprocess.run(["bash", str(script)], check=True)
    except subprocess.CalledProcessError as e:
        raise typer.Exit(e.returncode) from None


@app.command()
def connect() -> None:
    """Connect to anklume-instance (host only)."""
    import subprocess

    if not is_host():
        console.print("[yellow]Already inside a container.[/yellow]")
        raise typer.Exit(0)
    try:
        subprocess.run(
            ["incus", "exec", "anklume-instance", "--", "bash", "-l"],
            check=True,
        )
    except subprocess.CalledProcessError as e:
        raise typer.Exit(e.returncode) from None


@app.command()
def dashboard() -> None:
    """Open web dashboard."""
    run_make("dashboard")


# ── Register command groups ────────────────────────────────

_mode = get_mode()

# Essential groups (always visible)
app.add_typer(domain_app)
app.add_typer(lab_app)
app.add_typer(learn_app)
app.add_typer(mode_app)

# Standard groups (hidden in student mode for simplicity)
_standard = (
    instance_app, snapshot_app, network_app, portal_app,
    appexport_app, desktop_app, llm_app, stt_app, system_app,
    setup_app, backup_app, ai_app, docs_app,
)
for _grp in _standard:
    if _mode == "student":
        _grp.info.hidden = True
    app.add_typer(_grp)

# dev-only groups: hidden in user/student mode
if _mode == "dev":
    dev_app.info.hidden = False
app.add_typer(dev_app)

for _dev_only in (telemetry_app, live_app, golden_app, mcp_app):
    if _mode != "dev":
        _dev_only.info.hidden = True
    app.add_typer(_dev_only)
