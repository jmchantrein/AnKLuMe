"""Resource policy — allocation CPU/mémoire aux instances par poids.

Détecte le hardware, calcule la répartition selon la politique
configurée dans anklume.yml, et enrichit le config des machines.
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass

from anklume.engine.incus_driver import IncusDriver, IncusError
from anklume.engine.models import Infrastructure, Machine, ResourcePolicyConfig

log = logging.getLogger(__name__)

# Suffixes mémoire (puissances de 1024)
_MEMORY_UNITS = {
    "KB": 1024,
    "MB": 1024**2,
    "GB": 1024**3,
    "TB": 1024**4,
}


class OvercommitError(Exception):
    """Levée quand les ressources dépassent le total et overcommit=false."""


@dataclass
class HardwareInfo:
    """Ressources hardware détectées."""

    cpu_threads: int
    memory_bytes: int


@dataclass
class ResourceAllocation:
    """Allocation calculée pour une instance."""

    instance_name: str
    cpu_value: str  # "25%" ou "4" selon cpu_mode
    cpu_key: str  # "limits.cpu.allowance" ou "limits.cpu"
    memory_value: str  # "512MB"
    memory_key: str  # "limits.memory.soft" ou "limits.memory"
    source: str  # "auto", "explicit" ou "mixed"


# ---------------------------------------------------------------------------
# Détection hardware
# ---------------------------------------------------------------------------


def detect_hardware(driver: IncusDriver | None = None) -> HardwareInfo:
    """Détecte le hardware via IncusDriver, fallback sur os/proc."""
    if driver is None:
        driver = IncusDriver()

    try:
        data = driver.host_resources()
        return HardwareInfo(
            cpu_threads=data["cpu"]["total"],
            memory_bytes=data["memory"]["total"],
        )
    except (IncusError, KeyError):
        log.warning("Détection hardware via Incus échouée, fallback sur os/proc")
        return detect_hardware_fallback()


def detect_hardware_fallback() -> HardwareInfo:
    """Détecte le hardware depuis os.cpu_count() et /proc/meminfo."""
    cpu_count = os.cpu_count() or 1

    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    memory_kb = int(line.split()[1])
                    return HardwareInfo(
                        cpu_threads=cpu_count,
                        memory_bytes=memory_kb * 1024,
                    )
    except OSError:
        pass

    return HardwareInfo(cpu_threads=cpu_count, memory_bytes=0)


# ---------------------------------------------------------------------------
# Parsing des valeurs
# ---------------------------------------------------------------------------


def parse_reserve(value: str, total: int) -> int:
    """Parse une réserve (pourcentage ou absolu) et retourne la valeur entière.

    Accepte : "20%", "4" (absolu), "8GB"/"512MB" (mémoire avec suffixe).
    """
    if value.endswith("%"):
        pct = int(value[:-1])
        return int(total * pct / 100)
    # Tenter le parsing mémoire si ce n'est pas un entier pur
    if not value.isdigit():
        return parse_memory_value(value)
    return int(value)


def parse_memory_value(value: str) -> int:
    """Parse une valeur mémoire avec suffixe (GB, MB, KB, TB) en octets."""
    upper = value.upper()
    for suffix, multiplier in _MEMORY_UNITS.items():
        if upper.endswith(suffix):
            num = upper[: -len(suffix)]
            return int(num) * multiplier

    # Nombre brut = octets
    if value.isdigit():
        return int(value)

    msg = f"unité mémoire inconnue : {value}"
    raise ValueError(msg)


# ---------------------------------------------------------------------------
# Allocation
# ---------------------------------------------------------------------------


def compute_resource_allocation(
    infra: Infrastructure,
    hardware: HardwareInfo,
) -> list[ResourceAllocation]:
    """Calcule l'allocation de ressources pour toutes les instances.

    Retourne une liste vide si resource_policy est None.
    """
    policy = infra.config.resource_policy
    if policy is None:
        return []

    # Collecter toutes les machines des domaines actifs
    all_machines: list[Machine] = []
    for domain in infra.enabled_domains:
        all_machines.extend(domain.sorted_machines)

    if not all_machines:
        return []

    # Réserve hôte
    reserve_cpu = parse_reserve(policy.host_reserve_cpu, hardware.cpu_threads)
    reserve_mem = parse_reserve(policy.host_reserve_memory, hardware.memory_bytes)

    available_cpu = hardware.cpu_threads - reserve_cpu
    available_mem = hardware.memory_bytes - reserve_mem

    # Séparer explicites et auto
    cpu_auto: list[Machine] = []
    mem_auto: list[Machine] = []
    explicit_cpu_total = 0
    explicit_mem_total = 0

    for m in all_machines:
        if "limits.cpu" in m.config:
            explicit_cpu_total += int(m.config["limits.cpu"])
        else:
            cpu_auto.append(m)

        if "limits.memory" in m.config:
            explicit_mem_total += parse_memory_value(m.config["limits.memory"])
        else:
            mem_auto.append(m)

    # Vérifier l'overcommit
    _check_overcommit(explicit_cpu_total, available_cpu, policy, "threads")
    _check_overcommit(explicit_mem_total, available_mem, policy, "octets")

    allocatable_cpu = max(0, available_cpu - explicit_cpu_total)
    allocatable_mem = max(0, available_mem - explicit_mem_total)

    # Calculer les parts
    cpu_parts = _distribute(cpu_auto, allocatable_cpu, policy.mode)
    mem_parts = _distribute(mem_auto, allocatable_mem, policy.mode)

    # Construire les allocations
    cpu_key = "limits.cpu.allowance" if policy.cpu_mode == "allowance" else "limits.cpu"
    mem_key = "limits.memory.soft" if policy.memory_enforce == "soft" else "limits.memory"

    allocations: list[ResourceAllocation] = []

    for m in all_machines:
        is_cpu_explicit = "limits.cpu" in m.config
        is_mem_explicit = "limits.memory" in m.config

        if is_cpu_explicit:
            cpu_val = m.config["limits.cpu"]
            alloc_cpu_key = "limits.cpu"
        else:
            raw_cpu = cpu_parts.get(m.full_name, 0)
            cpu_val = _format_cpu(raw_cpu, hardware.cpu_threads, policy.cpu_mode)
            alloc_cpu_key = cpu_key

        if is_mem_explicit:
            mem_val = m.config["limits.memory"]
            alloc_mem_key = "limits.memory"
        else:
            raw_mem = mem_parts.get(m.full_name, 0)
            mem_val = _format_memory(raw_mem)
            alloc_mem_key = mem_key

        source = "explicit" if is_cpu_explicit and is_mem_explicit else (
            "auto" if not is_cpu_explicit and not is_mem_explicit else "mixed"
        )

        allocations.append(
            ResourceAllocation(
                instance_name=m.full_name,
                cpu_value=cpu_val,
                cpu_key=alloc_cpu_key,
                memory_value=mem_val,
                memory_key=alloc_mem_key,
                source=source,
            )
        )

    return allocations


def _distribute(
    machines: list[Machine],
    total: int,
    mode: str,
) -> dict[str, float]:
    """Distribue une quantité totale entre les machines."""
    if not machines:
        return {}

    if mode == "equal":
        part = total / len(machines)
        return {m.full_name: part for m in machines}

    # proportional
    total_weight = sum(m.weight for m in machines)
    if total_weight == 0:
        return {m.full_name: 0.0 for m in machines}

    return {
        m.full_name: total * m.weight / total_weight
        for m in machines
    }


def _check_overcommit(
    explicit_total: int,
    available: int,
    policy: ResourcePolicyConfig,
    unit: str,
) -> None:
    """Vérifie le dépassement de ressources (CPU ou mémoire)."""
    if explicit_total > available:
        msg = (
            f"Overcommit : explicites ({explicit_total} {unit}) "
            f"> disponible ({available} {unit})"
        )
        if policy.overcommit:
            log.warning(msg)
        else:
            raise OvercommitError(msg)


def _format_cpu(raw: float, total_threads: int, mode: str) -> str:
    """Formate une allocation CPU brute selon le mode."""
    if mode == "allowance":
        pct = round(raw / total_threads * 100) if total_threads > 0 else 0
        pct = max(pct, 1) if raw > 0 else pct
        return f"{pct}%"

    # count
    count = math.ceil(raw) if raw > 0 else 0
    return str(count)


def _format_memory(raw: float) -> str:
    """Formate une allocation mémoire en MB (minimum 64MB)."""
    mb = max(math.ceil(raw / 1024**2), 64) if raw > 0 else 64
    return f"{mb}MB"


# ---------------------------------------------------------------------------
# Application au modèle
# ---------------------------------------------------------------------------


def apply_resource_config(
    infra: Infrastructure,
    allocations: list[ResourceAllocation],
) -> None:
    """Enrichit machine.config avec les allocations calculées.

    Les valeurs explicites existantes sont préservées.
    """
    alloc_map = {a.instance_name: a for a in allocations}

    for domain in infra.enabled_domains:
        for machine in domain.machines.values():
            alloc = alloc_map.get(machine.full_name)
            if alloc is None:
                continue

            if alloc.source == "explicit":
                continue

            # CPU : seulement si pas explicite
            if "limits.cpu" not in machine.config and "limits.cpu.allowance" not in machine.config:
                machine.config[alloc.cpu_key] = alloc.cpu_value

            # Mémoire : seulement si pas explicite
            if "limits.memory" not in machine.config and "limits.memory.soft" not in machine.config:
                machine.config[alloc.memory_key] = alloc.memory_value
