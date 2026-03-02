"""anklume instance — manage individual instances."""

import json
from typing import Annotated

import typer
from rich.table import Table

from scripts.cli._completions import complete_domain, complete_instance
from scripts.cli._helpers import PROJECT_ROOT, console, format_bytes, load_infra_safe, run_cmd, run_make, run_script

app = typer.Typer(name="instance", help="Manage instances (containers and VMs).")


def _build_domain_map(infra: dict) -> dict:
    """Build machine_name -> (domain_name, domain_config) mapping."""
    result = {}
    for dname, dconf in (infra.get("domains") or {}).items():
        for mname in (dconf.get("machines") or {}):
            result[mname] = (dname, dconf)
    return result


def _get_trust_style(trust: str) -> str:
    """Return Rich style string for a trust level."""
    styles = {
        "admin": "bold blue",
        "trusted": "bold green",
        "semi-trusted": "bold yellow",
        "untrusted": "bold red",
        "disposable": "bold magenta",
    }
    return styles.get(trust, "dim")


@app.command("list")
def list_(
    domain: Annotated[
        str | None,
        typer.Option("--domain", "-d", help="Filter by domain", autocompletion=complete_domain),
    ] = None,
    sort: Annotated[
        str,
        typer.Option("--sort", "-s", help="Sort by: domain, cpu, memory, disk"),
    ] = "domain",
) -> None:
    """List instances with resource usage (Rich table)."""
    # Fetch instance data from Incus
    result = run_cmd(
        ["incus", "list", "--all-projects", "--format", "json"],
        capture=True, check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        console.print("[yellow]No instances found or Incus not available.[/yellow]")
        return

    try:
        instances = json.loads(result.stdout)
    except json.JSONDecodeError:
        console.print("[red]Failed to parse Incus output.[/red]")
        return

    if not instances:
        console.print("[yellow]No instances found.[/yellow]")
        return

    # Load infra for domain/trust enrichment
    try:
        infra = load_infra_safe()
    except SystemExit:
        infra = {"domains": {}}
    domain_map = _build_domain_map(infra)

    # Build rows
    rows = []
    for inst in instances:
        name = inst.get("name", "?")
        itype = inst.get("type", "container")
        type_label = "vm" if itype == "virtual-machine" else "lxc"
        status = inst.get("status", "Unknown")
        project = inst.get("project", "default")

        # Domain and trust from infra.yml
        dname = "-"
        trust = "-"
        if name in domain_map:
            dname, dconf = domain_map[name]
            from scripts.colors import infer_trust_level
            trust = infer_trust_level(dname, dconf)
        elif project != "default":
            dname = project

        # Filter by domain
        if domain and dname != domain:
            continue

        # CPU usage
        state = inst.get("state") or {}
        cpu_ns = state.get("cpu", {}).get("usage", 0)
        cpu_str = f"{cpu_ns / 1e9:.0f}s" if cpu_ns else "-"

        # Memory
        mem = state.get("memory") or {}
        mem_usage = mem.get("usage", 0)
        mem_str = format_bytes(mem_usage) if mem_usage else "-"

        # Disk
        disk = state.get("disk") or {}
        root_disk = disk.get("root", {})
        disk_usage = root_disk.get("usage", 0)
        disk_str = format_bytes(disk_usage) if disk_usage else "-"

        # IP (first IPv4 from eth0)
        ip_str = "-"
        network = state.get("network") or {}
        for nic_name in ("eth0", "enp5s0", "enp6s0"):
            nic = network.get(nic_name, {})
            for addr in nic.get("addresses", []):
                if addr.get("family") == "inet" and addr.get("scope") == "global":
                    ip_str = addr["address"]
                    break
            if ip_str != "-":
                break

        # GPU detection
        devices = inst.get("expanded_devices") or {}
        has_gpu = any(d.get("type") == "gpu" for d in devices.values())
        gpu_str = "yes" if has_gpu else ""

        rows.append({
            "name": name, "domain": dname, "trust": trust,
            "type": type_label, "status": status,
            "cpu": cpu_str, "cpu_val": cpu_ns,
            "memory": mem_str, "memory_val": mem_usage,
            "disk": disk_str, "disk_val": disk_usage,
            "ip": ip_str, "gpu": gpu_str,
        })

    # Sort
    sort_keys = {
        "domain": lambda r: (r["domain"], r["name"]),
        "cpu": lambda r: -r["cpu_val"],
        "memory": lambda r: -r["memory_val"],
        "disk": lambda r: -r["disk_val"],
    }
    rows.sort(key=sort_keys.get(sort, sort_keys["domain"]))

    # Build Rich table
    table = Table(title="Instances")
    table.add_column("Name", style="cyan")
    table.add_column("Domain")
    table.add_column("Trust")
    table.add_column("Type")
    table.add_column("Status")
    table.add_column("CPU", justify="right")
    table.add_column("Memory", justify="right")
    table.add_column("Disk", justify="right")
    table.add_column("IP")
    table.add_column("GPU")

    for row in rows:
        status_style = "green" if row["status"] == "Running" else "red"
        trust_style = _get_trust_style(row["trust"])
        table.add_row(
            row["name"],
            row["domain"],
            f"[{trust_style}]{row['trust']}[/{trust_style}]",
            row["type"],
            f"[{status_style}]{row['status']}[/{status_style}]",
            row["cpu"],
            row["memory"],
            row["disk"],
            row["ip"],
            row["gpu"],
        )

    console.print(table)


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
