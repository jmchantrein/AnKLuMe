"""Status — compare l'état déclaré (YAML) avec l'état réel (Incus)."""

from __future__ import annotations

from dataclasses import dataclass, field

from anklume.engine.incus_driver import IncusDriver
from anklume.engine.models import Infrastructure
from anklume.engine.nesting import NestingContext, prefix_name


@dataclass
class InstanceStatus:
    """État d'une instance : déclaré vs réel."""

    name: str
    machine_type: str
    state: str  # "Running", "Stopped", "Absent"

    @property
    def synced(self) -> bool:
        return self.state == "Running"


@dataclass
class DomainStatus:
    """État d'un domaine."""

    name: str
    project_exists: bool
    network_exists: bool
    instances: list[InstanceStatus] = field(default_factory=list)


@dataclass
class InfraStatus:
    """État complet de l'infrastructure."""

    domains: list[DomainStatus] = field(default_factory=list)

    @property
    def projects_total(self) -> int:
        return len(self.domains)

    @property
    def projects_found(self) -> int:
        return sum(1 for d in self.domains if d.project_exists)

    @property
    def networks_total(self) -> int:
        return len(self.domains)

    @property
    def networks_found(self) -> int:
        return sum(1 for d in self.domains if d.network_exists)

    @property
    def instances_total(self) -> int:
        return sum(len(d.instances) for d in self.domains)

    @property
    def instances_running(self) -> int:
        return sum(1 for d in self.domains for i in d.instances if i.synced)


def compute_status(
    infra: Infrastructure,
    driver: IncusDriver,
    nesting_context: NestingContext | None = None,
    domain_name: str | None = None,
) -> InfraStatus:
    """Compare l'état déclaré avec l'état réel Incus.

    Si domain_name est fourni, filtre sur ce seul domaine
    (évite les requêtes Incus pour les autres domaines).
    """
    ctx = nesting_context or NestingContext()
    nesting_cfg = infra.config.nesting
    result = InfraStatus()

    existing_projects = {p.name for p in driver.project_list()}

    for domain in infra.enabled_domains:
        if domain_name and domain.name != domain_name:
            continue
        project_name = prefix_name(domain.name, ctx, nesting_cfg)
        network_name = prefix_name(domain.network_name, ctx, nesting_cfg)

        project_exists = project_name in existing_projects

        if project_exists:
            network_exists = driver.network_exists(network_name, project_name)
            existing = {i.name: i for i in driver.instance_list(project_name)}
        else:
            network_exists = False
            existing = {}

        instances: list[InstanceStatus] = []
        for machine in domain.sorted_machines:
            incus_name = prefix_name(machine.full_name, ctx, nesting_cfg)
            incus_inst = existing.get(incus_name)

            if incus_inst is None:
                state = "Absent"
            else:
                state = incus_inst.status

            instances.append(
                InstanceStatus(
                    name=machine.full_name,
                    machine_type=machine.type,
                    state=state,
                )
            )

        result.domains.append(
            DomainStatus(
                name=domain.name,
                project_exists=project_exists,
                network_exists=network_exists,
                instances=instances,
            )
        )

    return result
