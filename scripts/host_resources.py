"""Host resource collection: CPU, RAM, disk, GPU/VRAM, LLM models.

Rendering functions are in host_resources_render.py (re-exported here).
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def collect_cpu() -> float | None:
    """Collect CPU usage percentage via two /proc/stat samples."""
    try:
        def read_stat() -> tuple[int, int]:
            with open("/proc/stat") as f:
                line = f.readline()
            parts = line.split()
            values = [int(x) for x in parts[1:9]]
            return values[3] + values[4], sum(values)

        idle1, total1 = read_stat()
        time.sleep(0.1)
        idle2, total2 = read_stat()
        total_delta = total2 - total1
        if total_delta == 0:
            return 0.0
        return round((1.0 - (idle2 - idle1) / total_delta) * 100, 1)
    except (FileNotFoundError, ValueError, IndexError):
        return None


def collect_cpu_count() -> int:
    """Return CPU core count."""
    return os.cpu_count() or 0


def collect_memory() -> dict | None:
    """Collect RAM usage from /proc/meminfo."""
    try:
        info: dict[str, int] = {}
        with open("/proc/meminfo") as f:
            for line in f:
                parts = line.split()
                info[parts[0].rstrip(":")] = int(parts[1]) * 1024
        total, available = info.get("MemTotal", 0), info.get("MemAvailable", 0)
        used = total - available
        return {"total": total, "used": used,
                "percent": round(used / total * 100, 1) if total > 0 else 0}
    except (FileNotFoundError, ValueError, IndexError):
        return None


def collect_disk(path: str = "/") -> dict | None:
    """Collect disk usage via os.statvfs."""
    try:
        st = os.statvfs(path)
        total, free = st.f_blocks * st.f_frsize, st.f_bfree * st.f_frsize
        used = total - free
        return {"total": total, "used": used, "free": free,
                "percent": round(used / total * 100, 1) if total > 0 else 0}
    except OSError:
        return None


def collect_gpu(
    container: str = "gpu-server", project: str = "ai-tools",
) -> dict | None:
    """Collect GPU info via incus exec nvidia-smi."""
    try:
        result = subprocess.run(
            ["incus", "exec", container, "--project", project, "--",
             "nvidia-smi", "--query-gpu=name,memory.used,memory.total,"
             "memory.free,temperature.gpu,utilization.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return None
        fields = [x.strip() for x in result.stdout.strip().split(",")]
        if len(fields) < 6:
            return None
        vram_total = int(fields[2])
        return {
            "name": fields[0], "vram_used": int(fields[1]),
            "vram_total": vram_total, "vram_free": int(fields[3]),
            "vram_percent": round(int(fields[1]) / vram_total * 100, 1) if vram_total > 0 else 0,
            "temperature": int(fields[4]), "utilization": int(fields[5]),
        }
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, IndexError):
        return None


def collect_ollama_models(
    host: str = "10.100.3.1", port: int = 11434,
) -> list[dict]:
    """Query Ollama /api/ps for loaded models."""
    try:
        req = urllib.request.Request(f"http://{host}:{port}/api/ps", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        models = []
        for m in data.get("models", []):
            size, size_vram = m.get("size", 0), m.get("size_vram", 0)
            models.append({
                "name": m.get("name", "unknown"), "size": size,
                "size_vram": size_vram,
                "vram_percent": round(size_vram / size * 100, 1) if size > 0 else 0,
                "expires_at": m.get("expires_at", ""),
            })
        return models
    except (urllib.error.URLError, json.JSONDecodeError, ValueError, KeyError, OSError):
        return []


def collect_ollama_connections(
    container: str = "gpu-server", project: str = "ai-tools", port: int = 11434,
) -> dict[str, str]:
    """Map Ollama connections to calling instances via ss + incus list."""
    try:
        result = subprocess.run(
            ["incus", "exec", container, "--project", project, "--",
             "ss", "-tnp", f"sport = :{port}"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return {}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {}
    source_ips: set[str] = set()
    for line in result.stdout.strip().splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 5:
            source_ips.add(parts[4].rsplit(":", 1)[0])
    if not source_ips:
        return {}
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
    ip_map: dict[str, str] = {}
    for inst in instances:
        name = inst.get("name", "")
        for nic, net in inst.get("state", {}).get("network", {}).items():
            if nic != "lo":
                for addr in net.get("addresses", []):
                    if addr.get("family") == "inet":
                        ip_map[addr["address"]] = name
    return {ip: ip_map.get(ip, ip) for ip in source_ips}


def collect_all() -> dict:
    """Aggregate all resource data (I/O-bound collectors run in parallel)."""
    with ThreadPoolExecutor(max_workers=4) as pool:
        cpu_fut = pool.submit(collect_cpu)
        gpu_fut = pool.submit(collect_gpu)
        models_fut = pool.submit(collect_ollama_models)
        conns_fut = pool.submit(collect_ollama_connections)
    return {
        "cpu_percent": cpu_fut.result(),
        "cpu_count": collect_cpu_count(),
        "memory": collect_memory(),
        "disk": collect_disk(),
        "gpu": gpu_fut.result(),
        "ollama_models": models_fut.result(),
        "ollama_connections": conns_fut.result(),
    }


# Re-export render functions for backward compatibility
from host_resources_render import (  # noqa: E402, F401
    render_cli,
    render_dashboard_data,
    render_tmux,
)


def main() -> None:
    """CLI entrypoint."""
    import argparse
    parser = argparse.ArgumentParser(description="Host resource monitoring")
    parser.add_argument("--json", dest="json_output", action="store_true")
    parser.add_argument("--tmux", action="store_true")
    parser.add_argument("--html", action="store_true")
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
