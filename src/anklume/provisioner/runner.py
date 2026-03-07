"""Exécution d'ansible-playbook via subprocess."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ProvisionResult:
    """Résultat d'un provisioning Ansible."""

    success: bool
    skipped: bool = False
    skip_reason: str = ""
    output: str = ""
    error: str = ""


def ansible_available() -> bool:
    """Vérifie que ansible-playbook est dans le PATH."""
    return shutil.which("ansible-playbook") is not None


def run_playbook(
    *,
    project_dir: Path,
    builtin_roles_dir: Path,
    custom_roles_dir: Path | None,
    plugin_dir: Path,
) -> ProvisionResult:
    """Exécute ansible-playbook avec les bons chemins."""
    ansible_dir = project_dir / "ansible"
    site_yml = ansible_dir / "site.yml"
    inventory_dir = ansible_dir / "inventory"

    # Construire ANSIBLE_ROLES_PATH (custom prioritaire)
    roles_parts: list[str] = []
    if custom_roles_dir and custom_roles_dir.is_dir():
        roles_parts.append(str(custom_roles_dir))
    roles_parts.append(str(builtin_roles_dir))
    roles_path = ":".join(roles_parts)

    env = {
        **os.environ,
        "ANSIBLE_ROLES_PATH": roles_path,
        "ANSIBLE_CONNECTION_PLUGINS": str(plugin_dir),
        "ANSIBLE_HOST_KEY_CHECKING": "False",
    }

    cmd = [
        "ansible-playbook",
        "-i",
        str(inventory_dir),
        str(site_yml),
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
        timeout=600,
    )

    return ProvisionResult(
        success=result.returncode == 0,
        output=result.stdout,
        error=result.stderr,
    )
