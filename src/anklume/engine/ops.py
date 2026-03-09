"""Opérations d'inspection — instance list, info, domain list, network status.

Fonctions pures (sauf lecture Incus via driver) pour les requêtes
d'inspection opérationnelle quotidienne.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field

from anklume.engine.incus_driver import IncusDriver
from anklume.engine.models import Infrastructure
from anklume.engine.nesting import NestingContext, prefix_name


@dataclass
class InstanceInfo:
    """Informations complètes d'une instance."""

    name: str
    domain: str
    machine_type: str
    state: str
    ip: str | None
    trust_level: str
    gpu: bool
    ephemeral: bool
    roles: list[str] = field(default_factory=list)
    profiles: list[str] = field(default_factory=list)
    snapshots: list[str] = field(default_factory=list)


@dataclass
class DomainInfo:
    """Informations récapitulatives d'un domaine."""

    name: str
    enabled: bool
    trust_level: str
    machine_count: int
    ephemeral: bool


@dataclass
class NetworkInfo:
    """État réseau d'un domaine."""

    domain: str
    bridge: str
    subnet: str | None
    gateway: str | None
    exists: bool


@dataclass
class NetworkStatus:
    """État réseau complet."""

    networks: list[NetworkInfo] = field(default_factory=list)
    nftables_present: bool = False
    nftables_rule_count: int = 0


def list_instances(
    infra: Infrastructure,
    driver: IncusDriver,
    nesting_context: NestingContext | None = None,
) -> list[InstanceInfo]:
    """Liste toutes les instances avec état réel combiné."""
    ctx = nesting_context or NestingContext()
    nesting_cfg = infra.config.nesting
    results: list[InstanceInfo] = []

    existing_projects = {p.name for p in driver.project_list()}

    for domain in infra.enabled_domains:
        project_name = prefix_name(domain.name, ctx, nesting_cfg)

        if project_name in existing_projects:
            real_instances = {i.name: i for i in driver.instance_list(project_name)}
        else:
            real_instances = {}

        for machine in domain.sorted_machines:
            incus_name = prefix_name(machine.full_name, ctx, nesting_cfg)
            real = real_instances.get(incus_name)
            state = real.status if real else "Absent"

            results.append(
                InstanceInfo(
                    name=machine.full_name,
                    domain=domain.name,
                    machine_type=machine.type,
                    state=state,
                    ip=machine.ip,
                    trust_level=domain.trust_level,
                    gpu=machine.gpu,
                    ephemeral=bool(machine.ephemeral),
                    roles=list(machine.roles),
                    profiles=list(machine.profiles),
                )
            )

    return results


def get_instance_info(
    infra: Infrastructure,
    driver: IncusDriver,
    instance_name: str,
    nesting_context: NestingContext | None = None,
) -> InstanceInfo | None:
    """Détails complets d'une instance (avec snapshots)."""
    ctx = nesting_context or NestingContext()
    nesting_cfg = infra.config.nesting

    existing_projects = {p.name for p in driver.project_list()}

    for domain in infra.enabled_domains:
        for machine in domain.machines.values():
            if machine.full_name != instance_name:
                continue

            project_name = prefix_name(domain.name, ctx, nesting_cfg)
            incus_name = prefix_name(machine.full_name, ctx, nesting_cfg)

            state = "Absent"
            snapshots: list[str] = []

            if project_name in existing_projects:
                real_instances = {
                    i.name: i for i in driver.instance_list(project_name)
                }
                real = real_instances.get(incus_name)
                if real:
                    state = real.status

                    snap_list = driver.snapshot_list(incus_name, project_name)
                    snapshots = [s.name for s in snap_list]

            return InstanceInfo(
                name=machine.full_name,
                domain=domain.name,
                machine_type=machine.type,
                state=state,
                ip=machine.ip,
                trust_level=domain.trust_level,
                gpu=machine.gpu,
                ephemeral=bool(machine.ephemeral),
                roles=list(machine.roles),
                profiles=list(machine.profiles),
                snapshots=snapshots,
            )

    return None


def list_domains(infra: Infrastructure) -> list[DomainInfo]:
    """Liste tous les domaines (actifs et inactifs), triés par nom."""
    return sorted(
        [
            DomainInfo(
                name=d.name,
                enabled=d.enabled,
                trust_level=d.trust_level,
                machine_count=len(d.machines),
                ephemeral=d.ephemeral,
            )
            for d in infra.domains.values()
        ],
        key=lambda d: d.name,
    )


def compute_network_status(
    infra: Infrastructure,
    driver: IncusDriver,
    nesting_context: NestingContext | None = None,
) -> NetworkStatus:
    """État réseau complet : bridges et nftables."""
    ctx = nesting_context or NestingContext()
    nesting_cfg = infra.config.nesting
    networks: list[NetworkInfo] = []

    existing_projects = {p.name for p in driver.project_list()}

    for domain in infra.enabled_domains:
        project_name = prefix_name(domain.name, ctx, nesting_cfg)
        bridge_name = prefix_name(domain.network_name, ctx, nesting_cfg)

        exists = False
        if project_name in existing_projects:
            exists = driver.network_exists(bridge_name, project_name)

        networks.append(
            NetworkInfo(
                domain=domain.name,
                bridge=domain.network_name,
                subnet=domain.subnet,
                gateway=domain.gateway,
                exists=exists,
            )
        )

    nftables_present, rule_count = _check_nftables()

    return NetworkStatus(
        networks=networks,
        nftables_present=nftables_present,
        nftables_rule_count=rule_count,
    )


def _check_nftables() -> tuple[bool, int]:
    """Vérifie si la table inet anklume existe et compte les règles."""
    try:
        result = subprocess.run(
            ["nft", "list", "table", "inet", "anklume"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return False, 0

        lines = result.stdout.strip().splitlines()
        keywords = ("iifname", "oifname", "ip ", "ct ", "accept", "drop")
        rule_count = sum(
            1 for line in lines if line.strip().startswith(keywords)
        )
        return True, rule_count
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False, 0
