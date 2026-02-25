"""Host resource detection and parsing utilities."""

import json
import subprocess
import sys


def _resolve(name):
    """Look up a patchable function on the ``generate`` module.

    See psot.validation._resolve for rationale.
    """
    gen = sys.modules.get("generate")
    if gen and hasattr(gen, name):
        return getattr(gen, name)
    import psot  # noqa: PLC0415

    return getattr(psot, name)


def _detect_host_resources():
    """Detect host CPU count and total memory.

    Tries 'incus info --resources --format json' first, then /proc fallback.
    Returns {"cpu": int, "memory_bytes": int} or None if detection fails.
    """
    try:
        result = subprocess.run(
            ["incus", "info", "--resources", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            cpu_total = data.get("cpu", {}).get("total", 0)
            mem_total = data.get("memory", {}).get("total", 0)
            if cpu_total > 0 and mem_total > 0:
                return {"cpu": cpu_total, "memory_bytes": mem_total}
    except (
        FileNotFoundError,
        subprocess.TimeoutExpired,
        json.JSONDecodeError,
    ):
        pass

    # Fallback: /proc
    try:
        cpu_count = 0
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("processor"):
                    cpu_count += 1
        mem_bytes = 0
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    mem_bytes = int(line.split()[1]) * 1024
                    break
        if cpu_count > 0 and mem_bytes > 0:
            return {"cpu": cpu_count, "memory_bytes": mem_bytes}
    except (FileNotFoundError, ValueError, IndexError):
        pass

    return None


def _parse_memory_value(value):
    """Parse Incus memory string (e.g., '2GiB', '512MiB') to bytes."""
    value = str(value).strip()
    suffixes = {
        "GiB": 1024**3,
        "MiB": 1024**2,
        "KiB": 1024,
        "GB": 10**9,
        "MB": 10**6,
    }
    for suffix, mult in suffixes.items():
        if value.endswith(suffix):
            try:
                return int(float(value[: -len(suffix)]) * mult)
            except ValueError:
                return 0
    try:
        return int(value)
    except ValueError:
        return 0


def _format_memory(bytes_val):
    """Format bytes as Incus memory string (e.g., '2GiB', '512MiB')."""
    gib = bytes_val / (1024**3)
    if gib >= 1 and int(gib) == gib:
        return f"{int(gib)}GiB"
    mib = bytes_val / (1024**2)
    if mib >= 1:
        return f"{int(mib)}MiB"
    return str(bytes_val)


def _apply_memory_enforce(infra):
    """Set limits.memory.enforce: soft on all machines with limits.memory."""
    for domain in (infra.get("domains") or {}).values():
        for machine in (domain.get("machines") or {}).values():
            config = machine.get("config") or {}
            if (
                "limits.memory" in config
                and "limits.memory.enforce" not in config
            ):
                config["limits.memory.enforce"] = "soft"
