"""Disposable containers — conteneurs jetables.

Lancement rapide de conteneurs éphémères pour des tâches ponctuelles.
Destruction automatique après usage.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass

from anklume.engine.incus_driver import IncusDriver, IncusError

log = logging.getLogger(__name__)

DISP_PREFIX = "disp-"
DISP_PROJECT = "default"


@dataclass
class DispContainer:
    """Conteneur jetable."""

    name: str
    image: str
    project: str = DISP_PROJECT
    status: str = "Running"


def generate_disp_name() -> str:
    """Génère un nom unique disp-XXXXXXXX (8 hex)."""
    return f"{DISP_PREFIX}{secrets.token_hex(4)}"


def launch_disposable(
    driver: IncusDriver,
    image: str,
    *,
    project: str = DISP_PROJECT,
) -> DispContainer:
    """Crée et démarre un conteneur jetable.

    Args:
        image: image Incus (ex: images:debian/13)
        project: projet Incus (défaut: default)

    Returns:
        DispContainer avec le nom généré.
    """
    name = generate_disp_name()

    driver.instance_create(
        name=name,
        project=project,
        image=image,
    )
    try:
        driver.instance_start(name, project)
    except IncusError:
        driver.instance_delete(name, project)
        raise

    return DispContainer(
        name=name,
        image=image,
        project=project,
        status="Running",
    )


def list_disposables(
    driver: IncusDriver,
    *,
    project: str = DISP_PROJECT,
) -> list[DispContainer]:
    """Liste les conteneurs jetables (préfixe disp-)."""
    instances = driver.instance_list(project)
    return [
        DispContainer(
            name=i.name,
            image="",
            project=project,
            status=i.status,
        )
        for i in instances
        if i.name.startswith(DISP_PREFIX)
    ]


def destroy_disposable(
    driver: IncusDriver,
    name: str,
    *,
    project: str = DISP_PROJECT,
) -> None:
    """Arrête et détruit un conteneur jetable."""
    instances = driver.instance_list(project)
    inst = next((i for i in instances if i.name == name), None)

    if inst is None:
        return

    if inst.status == "Running":
        driver.instance_stop(name, project)

    driver.instance_delete(name, project)


def cleanup_disposables(
    driver: IncusDriver,
    *,
    project: str = DISP_PROJECT,
) -> int:
    """Détruit tous les conteneurs jetables.

    Returns:
        Nombre de conteneurs supprimés.
    """
    disposables = list_disposables(driver, project=project)
    count = 0

    for disp in disposables:
        try:
            if disp.status == "Running":
                driver.instance_stop(disp.name, project)
            driver.instance_delete(disp.name, project)
            count += 1
        except IncusError as e:
            log.warning("Suppression %s échouée : %s", disp.name, e)

    return count
