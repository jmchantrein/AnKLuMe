"""Fixtures et factories partagées pour les tests anklume."""

from __future__ import annotations

from unittest.mock import MagicMock

import yaml

from anklume.engine.incus_driver import (
    IncusDriver,
    IncusInstance,
    IncusNetwork,
    IncusProject,
    IncusSnapshot,
)
from anklume.engine.models import (
    AddressingConfig,
    Defaults,
    Domain,
    GlobalConfig,
    Infrastructure,
    Machine,
)
from anklume.provisioner import BUILTIN_ROLES_DIR


def make_infra(
    domains: dict[str, Domain] | None = None,
    os_image: str = "images:debian/13",
) -> Infrastructure:
    """Crée une Infrastructure minimale pour les tests."""
    return Infrastructure(
        config=GlobalConfig(
            defaults=Defaults(os_image=os_image),
            addressing=AddressingConfig(),
        ),
        domains=domains or {},
        policies=[],
    )


def make_domain(
    name: str,
    machines: dict[str, Machine] | None = None,
    *,
    enabled: bool = True,
    ephemeral: bool = False,
    subnet: str | None = None,
    gateway: str | None = None,
) -> Domain:
    """Crée un Domain minimal."""
    return Domain(
        name=name,
        description=f"Domaine {name}",
        enabled=enabled,
        ephemeral=ephemeral,
        machines=machines or {},
        subnet=subnet,
        gateway=gateway,
    )


def make_machine(
    name: str,
    domain: str,
    *,
    type: str = "lxc",
    ip: str | None = None,
    ephemeral: bool = False,
    profiles: list[str] | None = None,
    config: dict | None = None,
    roles: list[str] | None = None,
    vars: dict | None = None,
) -> Machine:
    """Crée une Machine minimale."""
    return Machine(
        name=name,
        full_name=f"{domain}-{name}",
        description=f"Machine {name}",
        type=type,
        ip=ip,
        ephemeral=ephemeral,
        profiles=profiles or ["default"],
        config=config or {},
        roles=roles or [],
        vars=vars or {},
    )


def mock_driver(
    projects: list[IncusProject] | None = None,
    networks: dict[str, list[IncusNetwork]] | None = None,
    instances: dict[str, list[IncusInstance]] | None = None,
    snapshots: dict[str, list[IncusSnapshot]] | None = None,
) -> IncusDriver:
    """Crée un IncusDriver mocké."""
    driver = MagicMock(spec=IncusDriver)
    driver.project_list.return_value = projects or []
    driver.project_exists.side_effect = lambda n: any(p.name == n for p in (projects or []))

    _networks = networks or {}
    driver.network_list.side_effect = lambda p: _networks.get(p, [])
    driver.network_exists.side_effect = lambda n, p: any(
        net.name == n for net in _networks.get(p, [])
    )

    _instances = instances or {}
    driver.instance_list.side_effect = lambda p: _instances.get(p, [])

    _snapshots = snapshots or {}
    driver.snapshot_list.side_effect = lambda inst, proj: _snapshots.get(inst, [])

    # Méthodes destroy — noop par défaut
    driver.instance_config_set.return_value = None
    driver.network_delete.return_value = None
    driver.project_delete.return_value = None

    return driver


def running_instance(name: str, project: str) -> IncusInstance:
    return IncusInstance(name=name, status="Running", type="container", project=project)


def stopped_instance(name: str, project: str) -> IncusInstance:
    return IncusInstance(name=name, status="Stopped", type="container", project=project)


# ---------------------------------------------------------------------------
# Helpers pour lire les fichiers YAML des rôles Ansible
# ---------------------------------------------------------------------------


def role_tasks(role_name: str) -> list[dict]:
    """Lit et parse tasks/main.yml d'un rôle."""
    return yaml.safe_load((BUILTIN_ROLES_DIR / role_name / "tasks" / "main.yml").read_text())


def role_defaults(role_name: str) -> dict:
    """Lit et parse defaults/main.yml d'un rôle."""
    return yaml.safe_load((BUILTIN_ROLES_DIR / role_name / "defaults" / "main.yml").read_text())


def role_task_names(role_name: str) -> list[str]:
    """Retourne les noms des tâches d'un rôle."""
    return [t.get("name", "") for t in role_tasks(role_name)]
