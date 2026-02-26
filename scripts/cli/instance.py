"""anklume instance — manage individual instances."""

from typing import Annotated

import typer

from scripts.cli._completions import complete_domain, complete_instance
from scripts.cli._helpers import PROJECT_ROOT, console, load_infra_safe, run_cmd, run_make, run_script

app = typer.Typer(name="instance", help="Manage instances (containers and VMs).")


@app.command("list")
def list_(
    domain: Annotated[
        str | None,
        typer.Option(
            "--domain", "-d",
            help="Filter by domain",
            autocompletion=complete_domain,
        ),
    ] = None,
) -> None:
    """List running instances."""
    if domain:
        infra = load_infra_safe()
        domains = infra.get("domains") or {}
        if domain not in domains:
            console.print(f"[red]Unknown domain:[/red] {domain}")
            raise typer.Exit(1)
        import yaml

        gv = PROJECT_ROOT / "group_vars" / f"{domain}.yml"
        project = domain
        if gv.is_file():
            with open(gv) as f:
                gvars = yaml.safe_load(f) or {}
            project = gvars.get("incus_project", domain)
        run_cmd(["incus", "list", "--project", project, "--format", "table"], check=False)
    else:
        run_cmd(["incus", "list", "--all-projects", "--format", "table"], check=False)


@app.command()
def remove(
    name: Annotated[str, typer.Argument(help="Instance name", autocompletion=complete_instance)],
) -> None:
    """Remove an instance."""
    run_script("instance-remove.sh", f"I={name}")


@app.command("exec")
def exec_(
    name: Annotated[str, typer.Argument(help="Instance name", autocompletion=complete_instance)],
    command: Annotated[list[str], typer.Argument(help="Command to execute")],
) -> None:
    """Execute a command in an instance."""
    # Find the project for this instance
    infra = load_infra_safe()
    project = _find_project(infra, name)
    cmd = ["incus", "exec"]
    if project:
        cmd.extend(["--project", project])
    cmd.extend([name, "--"])
    cmd.extend(command)
    run_cmd(cmd, check=False)


@app.command()
def info(
    name: Annotated[str, typer.Argument(help="Instance name", autocompletion=complete_instance)],
) -> None:
    """Show detailed info for an instance."""
    infra = load_infra_safe()
    project = _find_project(infra, name)
    cmd = ["incus", "info"]
    if project:
        cmd.extend(["--project", project])
    cmd.append(name)
    run_cmd(cmd, check=False)


@app.command()
def disp(
    domain: Annotated[str, typer.Argument(help="Domain for the disposable container", autocompletion=complete_domain)],
) -> None:
    """Create a disposable container in a domain."""
    run_make("disp", f"D={domain}")


@app.command("clipboard")
def clipboard(
    direction: Annotated[str, typer.Argument(help="Direction: 'to' or 'from'")],
    instance: Annotated[str, typer.Argument(help="Instance name", autocompletion=complete_instance)],
) -> None:
    """Copy clipboard to/from an instance."""
    if direction == "to":
        run_make("clipboard-to", f"I={instance}")
    elif direction == "from":
        run_make("clipboard-from", f"I={instance}")
    else:
        console.print(f"[red]Invalid direction:[/red] {direction}. Use 'to' or 'from'.")
        raise typer.Exit(1)


def _find_project(infra: dict, instance_name: str) -> str | None:
    """Find the Incus project for a given instance name."""
    import yaml

    for dname, dconf in (infra.get("domains") or {}).items():
        machines = dconf.get("machines") or {}
        if instance_name in machines:
            gv = PROJECT_ROOT / "group_vars" / f"{dname}.yml"
            if gv.is_file():
                with open(gv) as f:
                    gvars = yaml.safe_load(f) or {}
                return gvars.get("incus_project", dname)
            return dname
    return None
