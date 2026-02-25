"""Resource allocation — CPU and memory distribution to machines."""

import contextlib
import sys

from psot.resources import (
    _apply_memory_enforce,
    _format_memory,
    _parse_memory_value,
    _resolve,
)


def _enrich_resources(infra):
    """Auto-allocate CPU and memory based on resource_policy."""
    g = infra.get("global", {})
    policy = g.get("resource_policy")
    if policy is None:
        return

    # resource_policy: true -> all defaults
    if policy is True:
        policy = {}
    if not isinstance(policy, dict):
        return

    host = _resolve("_detect_host_resources")()
    if host is None:
        print(
            "WARNING: Could not detect host resources, "
            "skipping resource allocation.",
            file=sys.stderr,
        )
        return

    host_reserve = policy.get("host_reserve", {})
    if not isinstance(host_reserve, dict):
        host_reserve = {}

    mode = policy.get("mode", "proportional")
    cpu_mode = policy.get("cpu_mode", "allowance")
    memory_enforce = policy.get("memory_enforce", "soft")
    overcommit = policy.get("overcommit", False)

    # Parse CPU reserve
    cpu_reserve_val = host_reserve.get("cpu", "20%")
    if isinstance(cpu_reserve_val, str) and cpu_reserve_val.endswith("%"):
        reserve_cpu = host["cpu"] * int(cpu_reserve_val.rstrip("%")) / 100
    else:
        reserve_cpu = float(cpu_reserve_val)

    # Parse memory reserve
    mem_reserve_val = host_reserve.get("memory", "20%")
    if isinstance(mem_reserve_val, str) and mem_reserve_val.endswith("%"):
        reserve_mem = int(
            host["memory_bytes"] * int(mem_reserve_val.rstrip("%")) / 100
        )
    elif isinstance(mem_reserve_val, str):
        reserve_mem = _parse_memory_value(mem_reserve_val)
    else:
        reserve_mem = int(mem_reserve_val)

    available_cpu = host["cpu"] - reserve_cpu
    available_mem = host["memory_bytes"] - reserve_mem

    if available_cpu <= 0 or available_mem <= 0:
        print(
            "WARNING: Host reserve exceeds available resources, "
            "skipping resource allocation.",
            file=sys.stderr,
        )
        return

    # Collect machines needing allocation
    domains = infra.get("domains") or {}
    entries = []  # (machine_dict, weight, needs_cpu, needs_mem)

    for domain in domains.values():
        for machine in (domain.get("machines") or {}).values():
            config = machine.get("config") or {}
            needs_cpu = (
                "limits.cpu" not in config
                and "limits.cpu.allowance" not in config
            )
            needs_mem = "limits.memory" not in config
            if needs_cpu or needs_mem:
                entries.append(
                    (machine, machine.get("weight", 1), needs_cpu, needs_mem)
                )

    if not entries:
        # Still apply memory_enforce to explicit machines
        if memory_enforce == "soft":
            _apply_memory_enforce(infra)
        return

    _distribute_cpu(entries, available_cpu, host, mode, cpu_mode)
    _distribute_memory(entries, available_mem, mode)

    if memory_enforce == "soft":
        _apply_memory_enforce(infra)

    _check_overcommit(
        domains, available_cpu, available_mem, host, overcommit,
    )


def _distribute_cpu(entries, available_cpu, host, mode, cpu_mode):
    """Distribute CPU resources to machines that need it."""
    cpu_entries = [(m, w) for m, w, nc, _ in entries if nc]
    if not cpu_entries:
        return
    w_total = (
        len(cpu_entries)
        if mode == "equal"
        else sum(w for _, w in cpu_entries)
    )
    for m, w in cpu_entries:
        share = (
            available_cpu * (1 if mode == "equal" else w) / w_total
        )
        config = m.setdefault("config", {})
        if cpu_mode == "count":
            config["limits.cpu"] = str(max(1, int(share)))
        else:
            pct = max(1, int(share / host["cpu"] * 100))
            config["limits.cpu.allowance"] = f"{pct}%"


def _distribute_memory(entries, available_mem, mode):
    """Distribute memory resources to machines that need it."""
    mem_entries = [(m, w) for m, w, _, nm in entries if nm]
    if not mem_entries:
        return
    w_total = (
        len(mem_entries)
        if mode == "equal"
        else sum(w for _, w in mem_entries)
    )
    for m, w in mem_entries:
        share = int(
            available_mem * (1 if mode == "equal" else w) / w_total
        )
        share = max(128 * 1024 * 1024, share)  # min 128 MiB
        config = m.setdefault("config", {})
        config["limits.memory"] = _format_memory(share)


def _check_overcommit(
    domains, available_cpu, available_mem, host, overcommit,
):
    """Check if total allocated resources exceed available pool."""
    total_cpu_count = 0.0
    total_cpu_allowance_pct = 0.0
    total_mem = 0
    for domain in domains.values():
        for machine in (domain.get("machines") or {}).values():
            config = machine.get("config") or {}
            if "limits.cpu" in config:
                with contextlib.suppress(ValueError, TypeError):
                    total_cpu_count += int(config["limits.cpu"])
            elif "limits.cpu.allowance" in config:
                val = str(config["limits.cpu.allowance"])
                if val.endswith("%"):
                    with contextlib.suppress(ValueError):
                        total_cpu_allowance_pct += int(val.rstrip("%"))
            if "limits.memory" in config:
                total_mem += _parse_memory_value(config["limits.memory"])

    max_allowance_pct = available_cpu / host["cpu"] * 100
    cpu_count_over = total_cpu_count > available_cpu * 1.001
    cpu_allowance_over = (
        total_cpu_allowance_pct > max_allowance_pct * 1.001
    )
    mem_over = total_mem > available_mem
    if cpu_count_over or cpu_allowance_over or mem_over:
        parts = []
        if cpu_count_over:
            parts.append(
                f"CPU: {total_cpu_count:.0f} cores > "
                f"{available_cpu:.0f} available"
            )
        if cpu_allowance_over:
            parts.append(
                f"CPU allowance: {total_cpu_allowance_pct:.0f}% > "
                f"{max_allowance_pct:.0f}% available"
            )
        if mem_over:
            parts.append(
                f"Memory: {_format_memory(total_mem)} > "
                f"{_format_memory(int(available_mem))}"
            )
        msg = "Resource overcommit: " + "; ".join(parts)
        if not overcommit:
            raise ValueError(
                f"{msg}. Set resource_policy.overcommit: true to allow."
            )
        else:
            print(f"WARNING: {msg}", file=sys.stderr)
