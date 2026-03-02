"""Host resource collection: CPU, RAM, disk, GPU/VRAM, LLM models.

Collects system resource usage without psutil dependency:
- CPU: /proc/stat (usage percentage via two samples)
- RAM: /proc/meminfo
- Disk: os.statvfs
- GPU: nvidia-smi via incus exec on gpu-server container
- LLM models: Ollama /api/ps
- Model→instance mapping: ss -tnp cross-referenced with incus list

Usage:
    python3 scripts/host_resources.py              # CLI table
    python3 scripts/host_resources.py --json       # JSON output
    python3 scripts/host_resources.py --tmux       # compact one-line for tmux
"""

import argparse
import json
import os
import subprocess
import time
import urllib.request


def collect_cpu():
    """Collect CPU usage percentage via two /proc/stat samples."""
    try:
        def read_stat():
            with open("/proc/stat") as f:
                line = f.readline()
            parts = line.split()
            # user, nice, system, idle, iowait, irq, softirq, steal
            values = [int(x) for x in parts[1:9]]
            idle = values[3] + values[4]
            total = sum(values)
            return idle, total

        idle1, total1 = read_stat()
        time.sleep(0.1)
        idle2, total2 = read_stat()

        idle_delta = idle2 - idle1
        total_delta = total2 - total1
        if total_delta == 0:
            return 0.0
        return round((1.0 - idle_delta / total_delta) * 100, 1)
    except (FileNotFoundError, ValueError, IndexError):
        return None


def collect_cpu_count():
    """Return CPU core count."""
    try:
        return os.cpu_count() or 0
    except Exception:
        return 0


def collect_memory():
    """Collect RAM usage from /proc/meminfo."""
    try:
        info = {}
        with open("/proc/meminfo") as f:
            for line in f:
                parts = line.split()
                key = parts[0].rstrip(":")
                info[key] = int(parts[1]) * 1024  # kB to bytes
        total = info.get("MemTotal", 0)
        available = info.get("MemAvailable", 0)
        used = total - available
        pct = round(used / total * 100, 1) if total > 0 else 0
        return {"total": total, "used": used, "percent": pct}
    except (FileNotFoundError, ValueError, IndexError):
        return None


def collect_disk(path="/"):
    """Collect disk usage via os.statvfs."""
    try:
        st = os.statvfs(path)
        total = st.f_blocks * st.f_frsize
        free = st.f_bfree * st.f_frsize
        used = total - free
        pct = round(used / total * 100, 1) if total > 0 else 0
        return {"total": total, "used": used, "free": free, "percent": pct}
    except OSError:
        return None


def collect_gpu(container="gpu-server", project="ai-tools"):
    """Collect GPU info via incus exec nvidia-smi."""
    try:
        result = subprocess.run(
            [
                "incus", "exec", container, "--project", project, "--",
                "nvidia-smi",
                "--query-gpu=name,memory.used,memory.total,memory.free,temperature.gpu,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return None
        parts = [x.strip() for x in result.stdout.strip().split(",")]
        if len(parts) < 6:
            return None
        return {
            "name": parts[0],
            "vram_used": int(parts[1]),
            "vram_total": int(parts[2]),
            "vram_free": int(parts[3]),
            "vram_percent": round(int(parts[1]) / int(parts[2]) * 100, 1) if int(parts[2]) > 0 else 0,
            "temperature": int(parts[4]),
            "utilization": int(parts[5]),
        }
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, IndexError):
        return None


def collect_ollama_models(host="10.100.3.1", port=11434):
    """Query Ollama /api/ps for loaded models."""
    try:
        url = f"http://{host}:{port}/api/ps"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        models = []
        for m in data.get("models", []):
            size = m.get("size", 0)
            size_vram = m.get("size_vram", 0)
            pct = round(size_vram / size * 100, 1) if size > 0 else 0
            models.append({
                "name": m.get("name", "unknown"),
                "size": size,
                "size_vram": size_vram,
                "vram_percent": pct,
                "expires_at": m.get("expires_at", ""),
            })
        return models
    except Exception:
        return []


def collect_ollama_connections(
    container="gpu-server", project="ai-tools", port=11434,
):
    """Map model connections to calling instances via ss + incus list.

    Cross-references source IPs of TCP connections to Ollama port with
    instance IPs from incus list.

    Returns: {source_ip: instance_name} mapping.
    """
    # Get active connections to Ollama port
    try:
        result = subprocess.run(
            [
                "incus", "exec", container, "--project", project, "--",
                "ss", "-tnp", f"sport = :{port}",
            ],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return {}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {}

    # Parse source IPs from ss output
    source_ips = set()
    for line in result.stdout.strip().splitlines()[1:]:  # skip header
        parts = line.split()
        if len(parts) >= 5:
            # peer address is column 5 (0-indexed: 4)
            peer = parts[4]
            ip = peer.rsplit(":", 1)[0]
            source_ips.add(ip)

    if not source_ips:
        return {}

    # Get instance→IP mapping
    try:
        result = subprocess.run(
            ["incus", "list", "--all-projects", "--format", "json"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return {}
        instances = json.loads(result.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return {}

    ip_to_instance = {}
    for inst in instances:
        name = inst.get("name", "")
        for net_name, net in inst.get("state", {}).get("network", {}).items():
            if net_name == "lo":
                continue
            for addr in net.get("addresses", []):
                if addr.get("family") == "inet":
                    ip_to_instance[addr["address"]] = name

    # Cross-reference
    result_map = {}
    for ip in source_ips:
        result_map[ip] = ip_to_instance.get(ip, ip)

    return result_map


def collect_all():
    """Aggregate all resource data."""
    return {
        "cpu_percent": collect_cpu(),
        "cpu_count": collect_cpu_count(),
        "memory": collect_memory(),
        "disk": collect_disk(),
        "gpu": collect_gpu(),
        "ollama_models": collect_ollama_models(),
        "ollama_connections": collect_ollama_connections(),
    }


def _fmt_bytes(n):
    """Format bytes as human-readable."""
    if n is None:
        return "N/A"
    gib = n / (1024 ** 3)
    if gib >= 1:
        return f"{gib:.1f} GiB"
    mib = n / (1024 ** 2)
    if mib >= 1:
        return f"{mib:.0f} MiB"
    return f"{n} B"


def _fmt_mib(mib):
    """Format MiB as human-readable GiB."""
    if mib >= 1024:
        return f"{mib / 1024:.1f} GiB"
    return f"{mib} MiB"


def _bar(pct, width=8):
    """Render a text progress bar."""
    if pct is None:
        return " " * width
    filled = int(pct / 100 * width)
    return "\u2588" * filled + "\u2591" * (width - filled)


def render_cli(data, json_output=False):
    """Render resource data as Rich CLI table."""
    if json_output:
        print(json.dumps(data, indent=2, default=str))
        return

    from rich.console import Console
    from rich.table import Table

    con = Console()

    # Section 1: Host resources
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
            _fmt_bytes(mem["used"]),
            _fmt_bytes(mem["total"]),
            _bar(mem["percent"]),
        )

    disk = data.get("disk")
    if disk:
        table.add_row(
            "Disk (/)",
            _fmt_bytes(disk["used"]),
            _fmt_bytes(disk["total"]),
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

    # Section 2: LLM models
    models = data.get("ollama_models", [])
    connections = data.get("ollama_connections", {})

    if models or gpu:
        con.print()
        mtable = Table(title="LLM Models (VRAM)")
        mtable.add_column("Model", style="bold")
        mtable.add_column("VRAM")
        mtable.add_column("% VRAM")
        mtable.add_column("Called by")

        for m in models:
            vram_gib = m["size_vram"] / (1024 ** 3)
            callers = [inst for inst in connections.values()]
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


def render_tmux(data):
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


def render_dashboard_data(data):
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

    # Models
    models = data.get("ollama_models", [])
    if models:
        parts.append('<div class="resource-models">')
        for m in models:
            vram_gib = m["size_vram"] / (1024 ** 3)
            parts.append(f'<span class="resource-model">{m["name"]}: {vram_gib:.1f}G</span>')
        parts.append('</div>')

    parts.append('</div>')
    return "\n".join(parts)


def main():
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Host resource monitoring")
    parser.add_argument("--json", dest="json_output", action="store_true",
                        help="JSON output")
    parser.add_argument("--tmux", action="store_true",
                        help="Compact one-line for tmux status")
    parser.add_argument("--html", action="store_true",
                        help="HTML fragment for dashboard")
    args = parser.parse_args()

    data = collect_all()

    if args.tmux:
        render_tmux(data)
    elif args.html:
        print(render_dashboard_data(data))
    else:
        render_cli(data, json_output=args.json_output)


if __name__ == "__main__":
    main()
