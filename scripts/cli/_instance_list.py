"""Instance list table builder — extracted from instance.py."""

import json

from rich.table import Table

from scripts.cli._helpers import console, format_bytes, load_infra_safe, run_cmd
from scripts.colors import (
    TRUST_RICH_STYLES,
    build_domain_map,
    extract_ipv4,
    infer_trust_level,
)


def render_instance_table(domain: str | None, sort: str) -> None:
    """Fetch instances from Incus and render a Rich table."""

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

    try:
        infra = load_infra_safe()
    except SystemExit:
        infra = {"domains": {}}
    domain_map = build_domain_map(infra)

    rows = []
    for inst in instances:
        name = inst.get("name", "?")
        itype = "vm" if inst.get("type") == "virtual-machine" else "lxc"
        status = inst.get("status", "Unknown")
        project = inst.get("project", "default")
        dname, trust = "-", "-"
        if name in domain_map:
            dname, dconf = domain_map[name]
            trust = infer_trust_level(dname, dconf)
        elif project != "default":
            dname = project
        if domain and dname != domain:
            continue
        state = inst.get("state") or {}
        cpu_ns = state.get("cpu", {}).get("usage", 0)
        mem_usage = (state.get("memory") or {}).get("usage", 0)
        disk_usage = (state.get("disk") or {}).get("root", {}).get("usage", 0)
        devices = inst.get("expanded_devices") or {}
        has_gpu = any(d.get("type") == "gpu" for d in devices.values())
        rows.append({
            "name": name, "domain": dname, "trust": trust,
            "type": itype, "status": status,
            "cpu": f"{cpu_ns / 1e9:.0f}s" if cpu_ns else "-", "cpu_val": cpu_ns,
            "memory": format_bytes(mem_usage) if mem_usage else "-",
            "memory_val": mem_usage,
            "disk": format_bytes(disk_usage) if disk_usage else "-",
            "disk_val": disk_usage,
            "ip": extract_ipv4(state, default="-"), "gpu": "yes" if has_gpu else "",
        })

    sort_keys = {
        "domain": lambda r: (r["domain"], r["name"]),
        "cpu": lambda r: -r["cpu_val"],
        "memory": lambda r: -r["memory_val"],
        "disk": lambda r: -r["disk_val"],
    }
    rows.sort(key=sort_keys.get(sort, sort_keys["domain"]))

    table = Table(title="Instances")
    for col, kw in [
        ("Name", {"style": "cyan"}), ("Domain", {}), ("Trust", {}),
        ("Type", {}), ("Status", {}),
        ("CPU", {"justify": "right"}), ("Memory", {"justify": "right"}),
        ("Disk", {"justify": "right"}), ("IP", {}), ("GPU", {}),
    ]:
        table.add_column(col, **kw)

    for row in rows:
        ss = "green" if row["status"] == "Running" else "red"
        ts = TRUST_RICH_STYLES.get(row["trust"], "dim")
        table.add_row(
            row["name"], row["domain"],
            f"[{ts}]{row['trust']}[/{ts}]",
            row["type"], f"[{ss}]{row['status']}[/{ss}]",
            row["cpu"], row["memory"], row["disk"],
            row["ip"], row["gpu"],
        )
    console.print(table)
