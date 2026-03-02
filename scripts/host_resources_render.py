"""Host resource rendering: CLI table, tmux one-liner, HTML dashboard.

Separated from host_resources.py (collectors) per 200-line limit.
"""

import html
import json

from scripts.cli._helpers import format_bytes


def _fmt_mib(mib: int) -> str:
    """Format MiB as human-readable GiB."""
    if mib >= 1024:
        return f"{mib / 1024:.1f} GiB"
    return f"{mib} MiB"


def _bar(pct: float | None, width: int = 8) -> str:
    """Render a text progress bar."""
    if pct is None:
        return " " * width
    filled = int(pct / 100 * width)
    return "\u2588" * filled + "\u2591" * (width - filled)


def render_cli(data: dict, json_output: bool = False) -> None:
    """Render resource data as Rich CLI table."""
    if json_output:
        print(json.dumps(data, indent=2, default=str))
        return

    from rich.console import Console
    from rich.table import Table

    con = Console()

    table = Table(title="Host Resources")
    table.add_column("Resource", style="bold")
    table.add_column("Used")
    table.add_column("Total")
    table.add_column("Usage")

    cpu = data.get("cpu_percent")
    table.add_row(
        "CPU",
        f"{cpu}%" if cpu is not None else "N/A",
        f"{data.get('cpu_count', '?')} cores",
        _bar(cpu),
    )

    mem = data.get("memory")
    if mem:
        table.add_row(
            "Memory",
            format_bytes(mem["used"]),
            format_bytes(mem["total"]),
            _bar(mem["percent"]),
        )

    disk = data.get("disk")
    if disk:
        table.add_row(
            "Disk (/)",
            format_bytes(disk["used"]),
            format_bytes(disk["total"]),
            _bar(disk["percent"]),
        )

    gpu = data.get("gpu")
    if gpu:
        table.add_row(
            "GPU VRAM",
            _fmt_mib(gpu["vram_used"]),
            _fmt_mib(gpu["vram_total"]),
            _bar(gpu["vram_percent"]),
        )
        table.add_row("GPU Temp", f"{gpu['temperature']}\u00b0C", "", "")
        table.add_row("GPU Util", f"{gpu['utilization']}%", "", _bar(gpu["utilization"]))

    con.print(table)

    models = data.get("ollama_models", [])
    connections = data.get("ollama_connections", {})
    callers = list(connections.values())

    if models or gpu:
        con.print()
        mtable = Table(title="LLM Models (VRAM)")
        mtable.add_column("Model", style="bold")
        mtable.add_column("VRAM")
        mtable.add_column("% VRAM")
        mtable.add_column("Called by")

        for m in models:
            vram_gib = m["size_vram"] / (1024 ** 3)
            caller_str = ", ".join(callers) if callers else ""
            mtable.add_row(
                m["name"],
                f"{vram_gib:.1f} GiB",
                f"{m['vram_percent']:.0f}%",
                caller_str,
            )

        if gpu:
            free_mib = gpu["vram_free"]
            mtable.add_row(
                "[dim][free][/dim]",
                f"[dim]{_fmt_mib(free_mib)}[/dim]",
                f"[dim]{round(free_mib / gpu['vram_total'] * 100)}%[/dim]",
                "",
            )

        con.print(mtable)


def render_tmux(data: dict) -> None:
    """Render compact one-line for tmux status-right."""
    parts = []
    cpu = data.get("cpu_percent")
    if cpu is not None:
        parts.append(f"CPU:{cpu:.0f}%")

    mem = data.get("memory")
    if mem:
        parts.append(f"RAM:{mem['percent']:.0f}%")

    gpu = data.get("gpu")
    if gpu:
        parts.append(f"VRAM:{gpu['vram_percent']:.0f}%")
        models = data.get("ollama_models", [])
        if models:
            names = [m["name"].split(":")[0] for m in models]
            vrams = [f"{m['size_vram'] // (1024**3)}G" for m in models]
            model_info = "+".join(f"{n}:{v}" for n, v in zip(names, vrams, strict=True))
            parts.append(f"[{model_info}]")
        parts.append(f"T:{gpu['temperature']}\u00b0")

    print(" ".join(parts))


def render_dashboard_data(data: dict) -> str:
    """Return HTML fragment for dashboard widget."""
    parts = ['<div class="resource-widget">']
    parts.append('<h2>Host Resources</h2>')

    for label, pct in [
        ("CPU", data.get("cpu_percent")),
        ("RAM", data["memory"]["percent"] if data.get("memory") else None),
        ("Disk", data["disk"]["percent"] if data.get("disk") else None),
        ("VRAM", data["gpu"]["vram_percent"] if data.get("gpu") else None),
    ]:
        if pct is None:
            continue
        color = "#3fb950" if pct < 70 else "#d29922" if pct < 90 else "#f85149"
        parts.append(
            f'<div class="resource-bar">'
            f'<span class="resource-label">{label}: {pct:.0f}%</span>'
            f'<div class="resource-track">'
            f'<div class="resource-fill" style="width:{pct}%;background:{color}"></div>'
            f'</div></div>'
        )

    models = data.get("ollama_models", [])
    if models:
        parts.append('<div class="resource-models">')
        for m in models:
            vram_gib = m["size_vram"] / (1024 ** 3)
            safe_name = html.escape(m["name"])
            parts.append(f'<span class="resource-model">{safe_name}: {vram_gib:.1f}G</span>')
        parts.append('</div>')

    parts.append('</div>')
    return "\n".join(parts)
