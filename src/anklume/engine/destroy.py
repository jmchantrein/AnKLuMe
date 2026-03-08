"""Destroy — suppression de l'infrastructure avec protection ephemeral."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from anklume.engine.incus_driver import IncusDriver, IncusError
from anklume.engine.models import Infrastructure
from anklume.engine.nesting import NestingContext, prefix_name

log = logging.getLogger(__name__)


@dataclass
class DestroyAction:
    """Une action de destruction à exécuter."""

    verb: str  # "stop", "unprotect", "delete"
    resource: str  # "instance", "network", "project"
    target: str
    project: str
    detail: str


@dataclass
class DestroyResult:
    """Résultat d'une destruction."""

    actions: list[DestroyAction] = field(default_factory=list)
    executed: list[DestroyAction] = field(default_factory=list)
    errors: list[tuple[DestroyAction, str]] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0

    @property
    def instances_deleted(self) -> int:
        return sum(1 for a in self.executed if a.verb == "delete" and a.resource == "instance")


def destroy(
    infra: Infrastructure,
    driver: IncusDriver,
    *,
    force: bool = False,
    dry_run: bool = False,
    nesting_context: NestingContext | None = None,
) -> DestroyResult:
    """Détruit l'infrastructure. Respecte la protection ephemeral sauf avec --force."""
    ctx = nesting_context or NestingContext()
    nesting_cfg = infra.config.nesting
    result = DestroyResult()

    existing_projects = {p.name for p in driver.project_list()}

    for domain in infra.enabled_domains:
        project_name = prefix_name(domain.name, ctx, nesting_cfg)

        if project_name not in existing_projects:
            continue

        existing = {i.name: i for i in driver.instance_list(project_name)}
        network_name = prefix_name(domain.network_name, ctx, nesting_cfg)

        domain_actions: list[DestroyAction] = []
        domain_skipped: list[tuple[str, str]] = []
        all_deleted = True

        for machine in domain.sorted_machines:
            incus_name = prefix_name(machine.full_name, ctx, nesting_cfg)
            incus_inst = existing.get(incus_name)

            if incus_inst is None:
                continue

            is_ephemeral = machine.ephemeral if machine.ephemeral is not None else domain.ephemeral

            if not is_ephemeral and not force:
                domain_skipped.append((incus_name, "protégée (utiliser --force)"))
                all_deleted = False
                continue

            # Arrêter si running
            if incus_inst.status == "Running":
                domain_actions.append(
                    DestroyAction(
                        verb="stop",
                        resource="instance",
                        target=incus_name,
                        project=project_name,
                        detail=f"Arrêter {incus_name}",
                    )
                )

            # Retirer la protection si non-éphémère et --force
            if not is_ephemeral and force:
                domain_actions.append(
                    DestroyAction(
                        verb="unprotect",
                        resource="instance",
                        target=incus_name,
                        project=project_name,
                        detail=f"Déprotéger {incus_name}",
                    )
                )

            # Supprimer
            domain_actions.append(
                DestroyAction(
                    verb="delete",
                    resource="instance",
                    target=incus_name,
                    project=project_name,
                    detail=f"Supprimer {incus_name}",
                )
            )

        # Réseau et projet si toutes les instances sont supprimées
        if all_deleted:
            if driver.network_exists(network_name, project_name):
                domain_actions.append(
                    DestroyAction(
                        verb="delete",
                        resource="network",
                        target=network_name,
                        project=project_name,
                        detail=f"Supprimer réseau {network_name}",
                    )
                )
            domain_actions.append(
                DestroyAction(
                    verb="delete",
                    resource="project",
                    target=project_name,
                    project=project_name,
                    detail=f"Supprimer projet {project_name}",
                )
            )

        result.actions.extend(domain_actions)
        result.skipped.extend(domain_skipped)

        if not dry_run:
            _execute_domain_actions(domain_actions, driver, result)

    return result


def _execute_domain_actions(
    actions: list[DestroyAction],
    driver: IncusDriver,
    result: DestroyResult,
) -> None:
    """Exécute les actions de destruction d'un domaine. Best-effort."""
    domain_failed = False

    for action in actions:
        if domain_failed:
            result.errors.append((action, "Ignoré suite à une erreur précédente"))
            continue

        try:
            _execute_action(action, driver)
            result.executed.append(action)
        except (IncusError, ValueError) as e:
            result.errors.append((action, str(e)))
            domain_failed = True


def _execute_action(action: DestroyAction, driver: IncusDriver) -> None:
    """Exécute une action de destruction unique."""
    if action.verb == "stop" and action.resource == "instance":
        driver.instance_stop(action.target, action.project)

    elif action.verb == "unprotect" and action.resource == "instance":
        driver.instance_config_set(
            action.target,
            action.project,
            "security.protection.delete",
            "false",
        )

    elif action.verb == "delete" and action.resource == "instance":
        driver.instance_delete(action.target, action.project)

    elif action.verb == "delete" and action.resource == "network":
        driver.network_delete(action.target, action.project)

    elif action.verb == "delete" and action.resource == "project":
        driver.project_delete(action.target)

    else:
        msg = f"Action inconnue : {action.verb}/{action.resource}"
        raise ValueError(msg)
