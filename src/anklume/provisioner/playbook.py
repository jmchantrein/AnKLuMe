"""Génération du playbook et des host_vars Ansible."""

from __future__ import annotations

from pathlib import Path

import yaml

from anklume.engine.models import Infrastructure

GENERATED_HEADER = "# Généré par anklume — sera écrasé au prochain apply\n"


def generate_playbook(infra: Infrastructure) -> list[dict]:
    """Génère la liste des plays Ansible.

    Un play par machine ayant des rôles, trié par domaine puis machine.
    """
    plays: list[dict] = []

    for domain in infra.enabled_domains:
        for machine in domain.sorted_machines:
            if not machine.roles:
                continue

            plays.append(
                {
                    "hosts": machine.full_name,
                    "become": True,
                    "gather_facts": False,
                    "pre_tasks": [
                        {
                            "name": "Installer Python3 (bootstrap)",
                            "raw": (
                                "test -x /usr/bin/python3"
                                " || (apt-get update -qq"
                                " && apt-get install -y -qq python3-minimal)"
                            ),
                            "changed_when": False,
                        },
                        {
                            "name": "Collecter les facts",
                            "setup": None,
                        },
                    ],
                    "roles": list(machine.roles),
                }
            )

    return plays


def generate_host_vars(infra: Infrastructure) -> dict[str, dict]:
    """Génère les variables par machine.

    Returns:
        {machine_full_name: vars_dict} — uniquement si vars non vide.
    """
    result: dict[str, dict] = {}

    for domain in infra.enabled_domains:
        for machine in domain.sorted_machines:
            if machine.vars:
                result[machine.full_name] = dict(machine.vars)

    return result


def write_playbook(project_dir: Path, infra: Infrastructure) -> Path | None:
    """Écrit site.yml dans project_dir/ansible/. None si aucun play."""
    plays = generate_playbook(infra)
    if not plays:
        return None

    ansible_dir = project_dir / "ansible"
    ansible_dir.mkdir(parents=True, exist_ok=True)

    path = ansible_dir / "site.yml"
    content = GENERATED_HEADER + "---\n" + yaml.dump(plays, default_flow_style=False)
    path.write_text(content)
    return path


def write_host_vars(project_dir: Path, infra: Infrastructure) -> list[Path]:
    """Écrit les fichiers host_vars dans project_dir/ansible/host_vars/."""
    host_vars = generate_host_vars(infra)
    if not host_vars:
        return []

    vars_dir = project_dir / "ansible" / "host_vars"
    vars_dir.mkdir(parents=True, exist_ok=True)

    paths: list[Path] = []
    for machine_name, vars_dict in sorted(host_vars.items()):
        path = vars_dir / f"{machine_name}.yml"
        content = GENERATED_HEADER + yaml.dump(vars_dict, default_flow_style=False)
        path.write_text(content)
        paths.append(path)

    return paths
