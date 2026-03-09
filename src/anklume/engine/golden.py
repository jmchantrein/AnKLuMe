"""Golden images — images réutilisables depuis des instances configurées.

Publie une instance provisionnée comme image Incus, pour réutilisation
comme base d'autres machines.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from anklume.engine.incus_driver import IncusDriver
from anklume.engine.models import Infrastructure
from anklume.engine.snapshot import resolve_instance_project

log = logging.getLogger(__name__)

GOLDEN_PREFIX = "golden/"


@dataclass
class GoldenImage:
    """Résultat de publication d'une golden image."""

    alias: str
    fingerprint: str
    size: int  # octets
    instance: str  # instance source


def create_golden(
    driver: IncusDriver,
    infra: Infrastructure,
    instance: str,
    *,
    alias: str | None = None,
) -> GoldenImage:
    """Publie une instance comme golden image.

    1. Résout instance → projet
    2. Arrête l'instance si running
    3. Publie via incus publish
    4. Redémarre l'instance si elle était running
    5. Retourne les métadonnées
    """
    project = resolve_instance_project(infra, instance)
    if project is None:
        msg = f"Instance inconnue : {instance}"
        raise ValueError(msg)

    final_alias = alias or f"{GOLDEN_PREFIX}{instance}"

    # Vérifier l'état de l'instance
    instances = driver.instance_list(project)
    real = next((i for i in instances if i.name == instance), None)
    was_running = real is not None and real.status == "Running"

    if was_running:
        driver.instance_stop(instance, project)

    meta = driver.image_publish(instance, project, alias=final_alias)

    if was_running:
        driver.instance_start(instance, project)

    return GoldenImage(
        alias=final_alias,
        fingerprint=meta.get("fingerprint", ""),
        size=meta.get("size", 0),
        instance=instance,
    )


def list_golden(
    driver: IncusDriver,
    *,
    project: str = "default",
) -> list[GoldenImage]:
    """Liste les golden images (alias golden/*)."""
    images = driver.image_list(project)
    results: list[GoldenImage] = []

    for img in images:
        for a in img.aliases:
            if a.startswith(GOLDEN_PREFIX):
                results.append(
                    GoldenImage(
                        alias=a,
                        fingerprint=img.fingerprint,
                        size=img.size,
                        instance="",
                    )
                )
                break  # un seul golden alias par image

    return results


def delete_golden(
    driver: IncusDriver,
    alias: str,
    *,
    project: str = "default",
) -> None:
    """Supprime une golden image par alias.

    Raises:
        ValueError: si l'alias est inconnu.
    """
    images = driver.image_list(project)

    for img in images:
        if alias in img.aliases:
            driver.image_delete(img.fingerprint, project)
            return

    msg = f"Image inconnue : {alias}"
    raise ValueError(msg)
