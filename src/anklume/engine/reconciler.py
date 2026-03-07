"""Réconciliateur — diff désiré (YAML) vs réel (Incus) + exécution.

Compare l'Infrastructure (état désiré) avec l'état réel lu via
IncusDriver, produit un plan d'actions ordonnées, et l'exécute
(sauf en dry-run).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from anklume.engine.incus_driver import IncusDriver, IncusError
from anklume.engine.models import Domain, Infrastructure, Machine


@dataclass
class Action:
    """Une action de réconciliation à exécuter."""

    verb: str  # "create" | "start" | "stop" | "delete" | "skip"
    resource: str  # "project" | "network" | "instance"
    target: str  # nom de la ressource
    project: str  # projet Incus concerné
    detail: str  # description lisible


@dataclass
class ReconcileResult:
    """Résultat d'une réconciliation."""

    actions: list[Action] = field(default_factory=list)
    executed: list[Action] = field(default_factory=list)
    errors: list[tuple[Action, str]] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0


def reconcile(
    infra: Infrastructure,
    driver: IncusDriver,
    *,
    dry_run: bool = False,
) -> ReconcileResult:
    """Réconcilie l'infrastructure désirée avec l'état réel Incus.

    Produit un plan d'actions ordonnées. En dry-run, retourne le plan
    sans l'exécuter. Sinon, exécute action par action.
    Best-effort par domaine : si un domaine échoue, les autres continuent.
    """
    result = ReconcileResult()

    # Cache la liste des projets une seule fois (évite N appels subprocess)
    existing_projects = {p.name for p in driver.project_list()}

    for domain_name in sorted(infra.domains):
        domain = infra.domains[domain_name]
        if not domain.enabled:
            continue

        domain_actions = _plan_domain(domain, infra, driver, existing_projects)
        result.actions.extend(domain_actions)

        if not dry_run:
            _execute_domain_actions(domain_actions, domain, infra, driver, result)

    return result


def _plan_domain(
    domain: Domain,
    infra: Infrastructure,
    driver: IncusDriver,
    existing_projects: set[str],
) -> list[Action]:
    """Calcule les actions nécessaires pour un domaine."""
    actions: list[Action] = []
    project_name = domain.name
    project_is_new = project_name not in existing_projects

    # 1. Projet
    if project_is_new:
        actions.append(
            Action(
                verb="create",
                resource="project",
                target=project_name,
                project=project_name,
                detail=f"Créer projet {project_name}",
            )
        )

    # 2. Réseau — short-circuit si le projet n'existe pas encore
    if project_is_new:
        net_exists = False
    else:
        net_exists = driver.network_exists(domain.network_name, project_name)

    if not net_exists:
        gateway = domain.gateway or "auto"
        actions.append(
            Action(
                verb="create",
                resource="network",
                target=domain.network_name,
                project=project_name,
                detail=f"Créer réseau {domain.network_name} ({gateway}/24, nat=true)",
            )
        )

    # 3. Instances — short-circuit si le projet n'existe pas encore
    if project_is_new:
        existing_instances: dict[str, object] = {}
    else:
        existing_instances = {i.name: i for i in driver.instance_list(project_name)}

    for machine_name in sorted(domain.machines):
        machine = domain.machines[machine_name]
        full_name = machine.full_name

        if full_name in existing_instances:
            instance = existing_instances[full_name]
            if instance.status == "Stopped":
                actions.append(
                    Action(
                        verb="start",
                        resource="instance",
                        target=full_name,
                        project=project_name,
                        detail=f"Démarrer instance {full_name}",
                    )
                )
        else:
            detail = _instance_create_detail(machine, infra, domain)
            actions.append(
                Action(
                    verb="create",
                    resource="instance",
                    target=full_name,
                    project=project_name,
                    detail=detail,
                )
            )
            actions.append(
                Action(
                    verb="start",
                    resource="instance",
                    target=full_name,
                    project=project_name,
                    detail=f"Démarrer instance {full_name}",
                )
            )

    return actions


def _instance_create_detail(
    machine: Machine,
    infra: Infrastructure,
    domain: Domain,
) -> str:
    """Génère la description détaillée pour la création d'une instance."""
    image = infra.config.defaults.os_image
    parts = [
        f"Créer instance {machine.full_name}",
        f"({machine.incus_type}, {image})",
    ]

    if not machine.ephemeral:
        parts.append("security.protection.delete=true")

    if machine.profiles and machine.profiles != ["default"]:
        parts.append(f"profiles={machine.profiles}")

    return " ".join(parts)


def _execute_domain_actions(
    actions: list[Action],
    domain: Domain,
    infra: Infrastructure,
    driver: IncusDriver,
    result: ReconcileResult,
) -> None:
    """Exécute les actions d'un domaine. Best-effort."""
    domain_failed = False

    for action in actions:
        if domain_failed:
            result.errors.append((action, "Ignoré suite à une erreur précédente"))
            continue

        try:
            _execute_action(action, domain, infra, driver)
            result.executed.append(action)
        except (IncusError, ValueError) as e:
            result.errors.append((action, str(e)))
            domain_failed = True


def _execute_action(
    action: Action,
    domain: Domain,
    infra: Infrastructure,
    driver: IncusDriver,
) -> None:
    """Exécute une action unique."""
    if action.verb == "create" and action.resource == "project":
        driver.project_create(action.target, description=domain.description)

    elif action.verb == "create" and action.resource == "network":
        config = {}
        if domain.gateway:
            config["ipv4.address"] = f"{domain.gateway}/24"
            config["ipv4.nat"] = "true"
        driver.network_create(action.target, action.project, config=config)

    elif action.verb == "create" and action.resource == "instance":
        machine = domain.machines.get(action.target.removeprefix(f"{domain.name}-"))
        if not machine:
            msg = f"Machine introuvable : {action.target}"
            raise ValueError(msg)

        config = dict(machine.config)
        if not machine.ephemeral:
            config["security.protection.delete"] = "true"

        driver.instance_create(
            name=machine.full_name,
            project=action.project,
            image=infra.config.defaults.os_image,
            instance_type=machine.incus_type,
            profiles=machine.profiles,
            config=config,
            network=domain.network_name,
        )

    elif action.verb == "start" and action.resource == "instance":
        driver.instance_start(action.target, action.project)

    elif action.verb == "stop" and action.resource == "instance":
        driver.instance_stop(action.target, action.project)

    elif action.verb == "delete" and action.resource == "instance":
        driver.instance_delete(action.target, action.project)

    else:
        msg = f"Action inconnue : {action.verb}/{action.resource}"
        raise ValueError(msg)
