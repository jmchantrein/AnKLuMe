"""anklume snapshot — snapshot and restore operations."""

from typing import Annotated

import typer

from scripts.cli._completions import complete_instance
from scripts.cli._helpers import PROJECT_ROOT, run_cmd, run_script

app = typer.Typer(name="snapshot", help="Manage instance snapshots.")


@app.command()
def create(
    instance: Annotated[
        str | None,
        typer.Argument(
            help="Instance to snapshot (all if omitted)",
            autocompletion=complete_instance,
        ),
    ] = None,
    name: Annotated[str | None, typer.Option("--name", "-n", help="Snapshot name")] = None,
    domain: Annotated[str | None, typer.Option("--domain", "-d", help="Snapshot entire domain")] = None,
) -> None:
    """Create a snapshot."""
    cmd = ["ansible-playbook", str(PROJECT_ROOT / "snapshot.yml"), "-e", "snapshot_action=create"]
    if name:
        cmd.extend(["-e", f"snapshot_name={name}"])
    if domain:
        cmd.extend(["--limit", domain])
    elif instance:
        cmd.extend(["--limit", instance])
    run_cmd(cmd)


@app.command()
def restore(
    instance: Annotated[str, typer.Argument(help="Instance to restore", autocompletion=complete_instance)],
    name: Annotated[str, typer.Option("--name", "-n", help="Snapshot name to restore")],
) -> None:
    """Restore an instance from a snapshot."""
    run_cmd([
        "ansible-playbook", str(PROJECT_ROOT / "snapshot.yml"),
        "-e", "snapshot_action=restore",
        "-e", f"snapshot_name={name}",
        "--limit", instance,
    ])


@app.command("list")
def list_(
    instance: Annotated[
        str | None,
        typer.Argument(
            help="Instance (all if omitted)",
            autocompletion=complete_instance,
        ),
    ] = None,
) -> None:
    """List snapshots."""
    cmd = ["ansible-playbook", str(PROJECT_ROOT / "snapshot.yml"), "-e", "snapshot_action=list"]
    if instance:
        cmd.extend(["--limit", instance])
    run_cmd(cmd)


@app.command()
def delete(
    instance: Annotated[str, typer.Argument(help="Instance", autocompletion=complete_instance)],
    name: Annotated[str, typer.Option("--name", "-n", help="Snapshot name to delete")],
) -> None:
    """Delete a snapshot."""
    run_cmd([
        "ansible-playbook", str(PROJECT_ROOT / "snapshot.yml"),
        "-e", "snapshot_action=delete",
        "-e", f"snapshot_name={name}",
        "--limit", instance,
    ])


@app.command()
def rollback(
    timestamp: Annotated[str | None, typer.Option("--timestamp", "-t", help="Specific pre-apply timestamp")] = None,
    list_: Annotated[bool, typer.Option("--list", "-l", help="List available rollback points")] = False,
    cleanup: Annotated[bool, typer.Option("--cleanup", help="Clean up old rollback snapshots")] = False,
) -> None:
    """Restore the latest pre-apply snapshot."""
    if list_:
        run_script("snap.sh", "rollback", "--list")
        return
    if cleanup:
        run_script("snap.sh", "rollback", "--cleanup")
        return
    args = ["rollback"]
    if timestamp:
        args.extend(["--timestamp", timestamp])
    run_script("snap.sh", *args)
