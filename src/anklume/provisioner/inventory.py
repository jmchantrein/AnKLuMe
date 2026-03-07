"""Génération de l'inventaire Ansible depuis l'infrastructure."""

from __future__ import annotations

from pathlib import Path

import yaml

from anklume.engine.models import Infrastructure

GENERATED_HEADER = "# Généré par anklume — sera écrasé au prochain apply\n"


def generate_inventories(infra: Infrastructure) -> dict[str, dict]:
    """Génère l'inventaire Ansible par domaine.

    Returns:
        {domain_name: inventory_dict} au format YAML inventory Ansible.
    """
    inventories: dict[str, dict] = {}

    for domain in infra.enabled_domains:
        hosts: dict[str, dict] = {}
        for machine in domain.sorted_machines:
            hosts[machine.full_name] = {
                "ansible_connection": "anklume_incus",
                "anklume_incus_project": domain.name,
            }

        inventories[domain.name] = {
            "all": {
                "children": {
                    domain.name: {
                        "hosts": hosts,
                    },
                },
            },
        }

    return inventories


def write_inventories(project_dir: Path, infra: Infrastructure) -> list[Path]:
    """Écrit les fichiers d'inventaire dans project_dir/ansible/inventory/."""
    inv_dir = project_dir / "ansible" / "inventory"
    inv_dir.mkdir(parents=True, exist_ok=True)

    inventories = generate_inventories(infra)
    paths: list[Path] = []

    for domain_name, inventory in inventories.items():
        path = inv_dir / f"{domain_name}.yml"
        content = GENERATED_HEADER + yaml.dump(inventory, default_flow_style=False)
        path.write_text(content)
        paths.append(path)

    return paths
