"""Gestion des snapshots — création auto/manuelle, listing, restauration."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Literal

from anklume.engine.incus_driver import IncusDriver, IncusError, IncusSnapshot
from anklume.engine.models import Infrastructure

logger = logging.getLogger(__name__)

SnapshotPhase = Literal["pre", "post", "snap"]


def generate_name(phase: SnapshotPhase = "snap") -> str:
    """Génère un nom de snapshot : anklume-{phase}-{YYYYMMDD-HHMMSS}."""
    ts = datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S")
    return f"anklume-{phase}-{ts}"


def create_snapshot(
    driver: IncusDriver,
    instance: str,
    project: str,
    name: str | None = None,
) -> str:
    """Crée un snapshot sur une instance. Retourne le nom du snapshot."""
    snap_name = name or generate_name()
    driver.snapshot_create(instance, project, snap_name)
    return snap_name


def create_auto_snapshots(
    driver: IncusDriver,
    infra: Infrastructure,
    phase: SnapshotPhase,
    *,
    existing_projects: set[str] | None = None,
) -> list[tuple[str, str, str]]:
    """Crée des snapshots automatiques pour les instances existantes.

    Args:
        phase: "pre", "post" ou "snap"
        existing_projects: projets Incus existants (évite un appel subprocess).

    Returns:
        Liste de (instance, project, snapshot_name) créés avec succès.
    """
    if existing_projects is None:
        existing_projects = {p.name for p in driver.project_list()}
    snap_name = generate_name(phase)
    created: list[tuple[str, str, str]] = []

    for domain in infra.enabled_domains:
        if domain.name not in existing_projects:
            continue

        instances = {i.name for i in driver.instance_list(domain.name)}

        for machine in domain.sorted_machines:
            if machine.full_name not in instances:
                continue

            try:
                driver.snapshot_create(machine.full_name, domain.name, snap_name)
                created.append((machine.full_name, domain.name, snap_name))
            except IncusError as e:
                logger.warning("Snapshot %s/%s échoué : %s", domain.name, machine.full_name, e)

    return created


def list_all_snapshots(
    driver: IncusDriver,
    infra: Infrastructure,
    instance_name: str | None = None,
    *,
    existing_projects: set[str] | None = None,
) -> dict[str, list[IncusSnapshot]]:
    """Liste les snapshots, groupés par instance.

    Si instance_name est fourni, filtre sur cette instance uniquement.
    """
    if existing_projects is None:
        existing_projects = {p.name for p in driver.project_list()}
    result: dict[str, list[IncusSnapshot]] = {}

    for domain in infra.enabled_domains:
        if domain.name not in existing_projects:
            continue

        instances = driver.instance_list(domain.name)

        for inst in instances:
            if instance_name and inst.name != instance_name:
                continue
            snapshots = driver.snapshot_list(inst.name, domain.name)
            result[inst.name] = snapshots

    return result


def restore_snapshot(
    driver: IncusDriver,
    instance: str,
    project: str,
    snapshot_name: str,
) -> None:
    """Restaure un snapshot. Arrête l'instance si running, restaure, redémarre."""
    instances = driver.instance_list(project)
    inst = next((i for i in instances if i.name == instance), None)

    was_running = inst is not None and inst.status == "Running"

    if was_running:
        driver.instance_stop(instance, project)

    driver.snapshot_restore(instance, project, snapshot_name)

    if was_running:
        driver.instance_start(instance, project)


def resolve_instance_project(
    infra: Infrastructure,
    instance_name: str,
) -> str | None:
    """Trouve le projet Incus d'une instance à partir de son nom complet."""
    for domain in infra.domains.values():
        for machine in domain.machines.values():
            if machine.full_name == instance_name:
                return domain.name
    return None
