"""Import infrastructure existante — scan Incus → domains/*.yml.

Scanne un Incus déjà configuré et génère les fichiers
domaine correspondants pour adoption par anklume.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml

from anklume.engine.incus_driver import IncusDriver

log = logging.getLogger(__name__)

# Projets Incus à ignorer lors du scan
_SKIP_PROJECTS = {"default"}


@dataclass
class ScannedInstance:
    """Instance détectée dans Incus."""

    name: str
    status: str
    instance_type: Literal["container", "virtual-machine"]
    project: str


@dataclass
class ScannedDomain:
    """Domaine reconstitué depuis un projet Incus."""

    project: str
    network: str | None = None
    subnet: str | None = None
    instances: list[ScannedInstance] = field(default_factory=list)


@dataclass
class ImportResult:
    """Résultat d'un import."""

    domains: list[ScannedDomain] = field(default_factory=list)
    files_written: list[str] = field(default_factory=list)


def scan_incus(driver: IncusDriver) -> list[ScannedDomain]:
    """Scanne les projets Incus et reconstruit les domaines.

    Ignore le projet `default`. Pour chaque projet :
    - Détecte le réseau `net-*` et son subnet
    - Liste les instances avec leur type et état
    """
    projects = driver.project_list()
    domains: list[ScannedDomain] = []

    for proj in projects:
        if proj.name in _SKIP_PROJECTS:
            continue

        # Réseaux
        networks = driver.network_list(proj.name)
        network_name = None
        subnet = None
        for net in networks:
            if net.name.startswith("net-"):
                network_name = net.name
                subnet = net.config.get("ipv4.address")
                break

        # Instances
        instances = driver.instance_list(proj.name)
        scanned_instances = [
            ScannedInstance(
                name=inst.name,
                status=inst.status,
                instance_type=inst.type,
                project=proj.name,
            )
            for inst in instances
        ]

        domains.append(
            ScannedDomain(
                project=proj.name,
                network=network_name,
                subnet=subnet,
                instances=scanned_instances,
            )
        )

    return domains


def _instance_to_machine_name(instance_name: str, project: str) -> str:
    """Déduit le nom de machine depuis le nom d'instance.

    Si l'instance s'appelle 'pro-dev', et le projet est 'pro',
    le nom de machine est 'dev'.
    """
    prefix = f"{project}-"
    if instance_name.startswith(prefix):
        return instance_name[len(prefix) :]
    return instance_name


def _instance_type_to_anklume(instance_type: str) -> str:
    """Convertit le type Incus en type anklume."""
    if instance_type == "virtual-machine":
        return "vm"
    return "lxc"


def generate_domain_files(
    domains: list[ScannedDomain],
    output_dir: Path,
) -> list[str]:
    """Génère les fichiers domains/*.yml depuis le scan.

    Returns:
        Liste des chemins de fichiers écrits.
    """
    domains_dir = output_dir / "domains"
    domains_dir.mkdir(parents=True, exist_ok=True)

    files_written: list[str] = []

    for domain in domains:
        machines = {}
        for inst in domain.instances:
            machine_name = _instance_to_machine_name(inst.name, domain.project)
            machines[machine_name] = {
                "description": f"Importé depuis {inst.name}",
                "type": _instance_type_to_anklume(inst.instance_type),
            }

        domain_data = {
            "description": f"Domaine importé depuis le projet {domain.project}",
            "trust_level": "semi-trusted",
            "enabled": True,
            "machines": machines,
        }

        file_path = domains_dir / f"{domain.project}.yml"
        file_path.write_text(
            yaml.dump(domain_data, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )
        files_written.append(str(file_path))

    return files_written


def import_infrastructure(
    driver: IncusDriver,
    output_dir: Path,
) -> ImportResult:
    """Scan complet + génération de fichiers.

    Args:
        driver: driver Incus
        output_dir: répertoire de sortie (racine du projet)

    Returns:
        ImportResult avec domaines scannés et fichiers écrits.
    """
    domains = scan_incus(driver)
    files = generate_domain_files(domains, output_dir)

    return ImportResult(
        domains=domains,
        files_written=files,
    )
