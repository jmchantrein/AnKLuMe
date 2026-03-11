"""Exécution d'ansible-playbook via subprocess."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


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


def install_galaxy_requirements(
    project_dir: Path,
    galaxy_roles_dir: Path,
) -> bool:
    """Installe les rôles Galaxy depuis requirements.yml si présent.

    Returns:
        True si les rôles ont été installés (ou pas de requirements.yml).
        False en cas d'erreur.
    """
    requirements = project_dir / "requirements.yml"
    if not requirements.exists():
        return True

    if not shutil.which("ansible-galaxy"):
        log.warning("ansible-galaxy absent — rôles Galaxy ignorés")
        return True

    galaxy_roles_dir.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        [
            "ansible-galaxy",
            "install",
            "-r",
            str(requirements),
            "-p",
            str(galaxy_roles_dir),
            "--force",
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )

    if result.returncode != 0:
        log.error("ansible-galaxy install échoué : %s", result.stderr)
        return False

    log.info("Rôles Galaxy installés dans %s", galaxy_roles_dir)
    return True


def run_playbook(
    *,
    project_dir: Path,
    builtin_roles_dir: Path,
    custom_roles_dir: Path | None,
    galaxy_roles_dir: Path | None = None,
    plugin_dir: Path,
) -> ProvisionResult:
    """Exécute ansible-playbook avec les bons chemins."""
    ansible_dir = project_dir / "ansible"
    site_yml = ansible_dir / "site.yml"
    inventory_dir = ansible_dir / "inventory"

    # Construire ANSIBLE_ROLES_PATH (custom > galaxy > builtin)
    roles_parts: list[str] = []
    if custom_roles_dir and custom_roles_dir.is_dir():
        roles_parts.append(str(custom_roles_dir))
    if galaxy_roles_dir and galaxy_roles_dir.is_dir():
        roles_parts.append(str(galaxy_roles_dir))
    roles_parts.append(str(builtin_roles_dir))
    roles_path = ":".join(roles_parts)

    # Whitelist de variables d'environnement — évite de transmettre
    # des secrets accidentels au subprocess Ansible.
    _ENV_WHITELIST = (
        "PATH",
        "HOME",
        "USER",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TERM",
        "SSH_AUTH_SOCK",
        "TMPDIR",
    )
    env = {k: v for k, v in os.environ.items() if k in _ENV_WHITELIST}
    env.update(
        {
            "ANSIBLE_ROLES_PATH": roles_path,
            "ANSIBLE_CONNECTION_PLUGINS": str(plugin_dir),
            "ANSIBLE_HOST_KEY_CHECKING": "False",
        }
    )

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
