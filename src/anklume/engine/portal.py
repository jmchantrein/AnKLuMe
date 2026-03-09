"""Portails fichiers — transfert hôte ↔ conteneur.

Push, pull et listing de fichiers via incus file push/pull.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Literal

from anklume.engine.incus_driver import IncusDriver
from anklume.engine.models import Infrastructure
from anklume.engine.snapshot import resolve_instance_project

_PATH_TRAVERSAL_MSG = "Chemin invalide : séquence '..' interdite"

log = logging.getLogger(__name__)


@dataclass
class PortalEntry:
    """Entrée dans un répertoire distant."""

    name: str
    entry_type: Literal["file", "directory", "link"]
    size: int  # octets (-1 si inconnu)
    permissions: str  # ex: "-rw-r--r--"


@dataclass
class TransferResult:
    """Résultat d'un transfert fichier."""

    instance: str
    local_path: str
    remote_path: str
    size: int  # octets transférés


def push_file(
    driver: IncusDriver,
    infra: Infrastructure,
    instance: str,
    local_path: str,
    remote_path: str = "/tmp/",  # noqa: S108
) -> TransferResult:
    """Envoie un fichier vers une instance.

    Args:
        instance: nom complet de l'instance (ex: pro-dev)
        local_path: chemin du fichier local
        remote_path: chemin distant (défaut /tmp/)

    Raises:
        FileNotFoundError: fichier local introuvable.
        ValueError: instance inconnue.
    """
    project = resolve_instance_project(infra, instance)
    if project is None:
        msg = f"Instance inconnue : {instance}"
        raise ValueError(msg)

    if ".." in local_path.split(os.sep):
        raise ValueError(_PATH_TRAVERSAL_MSG)
    if ".." in remote_path.split("/"):
        raise ValueError(_PATH_TRAVERSAL_MSG)

    if not os.path.exists(local_path):
        msg = f"Fichier introuvable : {local_path}"
        raise FileNotFoundError(msg)

    file_size = os.path.getsize(local_path)

    # Si remote_path finit par /, ajouter le nom du fichier
    if remote_path.endswith("/"):
        remote_path = remote_path + os.path.basename(local_path)

    driver.file_push(instance, project, local_path, remote_path)

    return TransferResult(
        instance=instance,
        local_path=local_path,
        remote_path=remote_path,
        size=file_size,
    )


def pull_file(
    driver: IncusDriver,
    infra: Infrastructure,
    instance: str,
    remote_path: str,
    local_path: str = ".",
) -> TransferResult:
    """Récupère un fichier depuis une instance.

    Args:
        instance: nom complet de l'instance
        remote_path: chemin du fichier distant
        local_path: chemin local de destination (défaut: répertoire courant)

    Raises:
        ValueError: instance inconnue.
    """
    project = resolve_instance_project(infra, instance)
    if project is None:
        msg = f"Instance inconnue : {instance}"
        raise ValueError(msg)

    if ".." in remote_path.split("/"):
        raise ValueError(_PATH_TRAVERSAL_MSG)
    if ".." in local_path.split(os.sep):
        raise ValueError(_PATH_TRAVERSAL_MSG)

    # Si local_path est un répertoire, ajouter le nom du fichier distant
    if os.path.isdir(local_path):
        local_path = os.path.join(local_path, os.path.basename(remote_path))

    driver.file_pull(instance, project, remote_path, local_path)

    size = os.path.getsize(local_path) if os.path.exists(local_path) else 0

    return TransferResult(
        instance=instance,
        local_path=local_path,
        remote_path=remote_path,
        size=size,
    )


def list_remote(
    driver: IncusDriver,
    infra: Infrastructure,
    instance: str,
    remote_path: str = "/root/",
) -> list[PortalEntry]:
    """Liste les entrées d'un répertoire distant via ls -la.

    Raises:
        ValueError: instance inconnue.
    """
    project = resolve_instance_project(infra, instance)
    if project is None:
        msg = f"Instance inconnue : {instance}"
        raise ValueError(msg)

    result = driver.instance_exec(instance, project, ["ls", "-la", remote_path])

    return _parse_ls_output(result.stdout)


def _parse_ls_output(output: str) -> list[PortalEntry]:
    """Parse la sortie de ls -la en PortalEntry."""
    entries: list[PortalEntry] = []
    for line in output.strip().splitlines():
        # Ignorer la ligne "total X"
        if line.startswith("total "):
            continue
        parts = line.split(None, 8)
        if len(parts) < 9:
            continue

        permissions = parts[0]
        size_str = parts[4]
        name = parts[8]

        # Ignorer . et ..
        if name in (".", ".."):
            continue

        try:
            size = int(size_str)
        except ValueError:
            size = -1

        if permissions.startswith("d"):
            entry_type = "directory"
        elif permissions.startswith("l"):
            entry_type = "link"
        else:
            entry_type = "file"

        entries.append(
            PortalEntry(
                name=name,
                entry_type=entry_type,
                size=size,
                permissions=permissions,
            )
        )

    return entries
