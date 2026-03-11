"""Réconciliateur — diff désiré (YAML) vs réel (Incus) + exécution.

Compare l'Infrastructure (état désiré) avec l'état réel lu via
IncusDriver, produit un plan d'actions ordonnées, et l'exécute
(sauf en dry-run).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from anklume.engine.gpu import GPU_PROFILE_NAME
from anklume.engine.gui import (
    GUI_PROFILE_NAME,
    GuiInfo,
    create_gui_profile,
)
from anklume.engine.incus_driver import IncusDriver, IncusError
from anklume.engine.models import Domain, Infrastructure, Machine, NestingConfig
from anklume.engine.nesting import (
    NestingContext,
    context_files_for_instance,
    nesting_security_config,
    prefix_name,
    unprefix_name,
)

log = logging.getLogger(__name__)


@dataclass
class Action:
    """Une action de réconciliation à exécuter."""

    verb: str  # "create" | "start" | "stop" | "delete" | "skip"
    resource: str  # "project" | "network" | "instance" | "profile"
    target: str  # nom de la ressource (préfixé si nesting)
    project: str  # projet Incus concerné (préfixé si nesting)
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
    nesting_context: NestingContext | None = None,
    gui_info: GuiInfo | None = None,
) -> ReconcileResult:
    """Réconcilie l'infrastructure désirée avec l'état réel Incus.

    Produit un plan d'actions ordonnées. En dry-run, retourne le plan
    sans l'exécuter. Sinon, exécute action par action.
    Best-effort par domaine : si un domaine échoue, les autres continuent.
    """
    ctx = nesting_context or NestingContext()
    result = ReconcileResult()

    existing_projects = {p.name for p in driver.project_list()}

    for domain_name in sorted(infra.domains):
        domain = infra.domains[domain_name]
        if not domain.enabled:
            continue

        domain_actions = _plan_domain(domain, infra, driver, existing_projects, ctx)
        result.actions.extend(domain_actions)

        if not dry_run:
            _execute_domain_actions(
                domain_actions,
                domain,
                infra,
                driver,
                result,
                ctx,
                gui_info,
            )

    return result


def _plan_domain(
    domain: Domain,
    infra: Infrastructure,
    driver: IncusDriver,
    existing_projects: set[str],
    ctx: NestingContext,
) -> list[Action]:
    """Calcule les actions nécessaires pour un domaine."""
    actions: list[Action] = []
    nesting_cfg = infra.config.nesting

    project_name = prefix_name(domain.name, ctx, nesting_cfg)
    network_name = prefix_name(domain.network_name, ctx, nesting_cfg)
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

    # 1b. Profil GPU (si des machines GPU dans ce domaine)
    has_gpu_machines = any(GPU_PROFILE_NAME in m.profiles for m in domain.machines.values())
    if has_gpu_machines:
        if project_is_new:
            gpu_profile_exists = False
        else:
            gpu_profile_exists = driver.profile_exists(GPU_PROFILE_NAME, project_name)

        if not gpu_profile_exists:
            actions.append(
                Action(
                    verb="create",
                    resource="profile",
                    target=GPU_PROFILE_NAME,
                    project=project_name,
                    detail=f"Créer profil {GPU_PROFILE_NAME} (GPU passthrough)",
                )
            )

    # 1c. Profil GUI (si des machines GUI dans ce domaine)
    has_gui_machines = any(GUI_PROFILE_NAME in m.profiles for m in domain.machines.values())
    if has_gui_machines:
        if project_is_new:
            gui_profile_exists = False
        else:
            gui_profile_exists = driver.profile_exists(
                GUI_PROFILE_NAME,
                project_name,
            )

        if not gui_profile_exists:
            actions.append(
                Action(
                    verb="create",
                    resource="profile",
                    target=GUI_PROFILE_NAME,
                    project=project_name,
                    detail=f"Créer profil {GUI_PROFILE_NAME} (Wayland + PipeWire + iGPU)",
                )
            )

    # 1d. Profils custom du domaine
    for profile_name, _profile in domain.profiles.items():
        if profile_name in (GPU_PROFILE_NAME, GUI_PROFILE_NAME):
            continue  # déjà gérés ci-dessus
        if project_is_new:
            custom_exists = False
        else:
            custom_exists = driver.profile_exists(profile_name, project_name)

        if not custom_exists:
            actions.append(
                Action(
                    verb="create",
                    resource="profile",
                    target=profile_name,
                    project=project_name,
                    detail=f"Créer profil custom {profile_name}",
                )
            )

    # 2. Réseau
    if project_is_new:
        net_exists = False
    else:
        net_exists = driver.network_exists(network_name, project_name)

    if not net_exists:
        gateway = domain.gateway or "auto"
        actions.append(
            Action(
                verb="create",
                resource="network",
                target=network_name,
                project=project_name,
                detail=f"Créer réseau {network_name} ({gateway}/24, nat=true)",
            )
        )

    # 3. Instances
    if project_is_new:
        existing_instances: dict[str, object] = {}
    else:
        existing_instances = {i.name: i for i in driver.instance_list(project_name)}

    for machine_name in sorted(domain.machines):
        machine = domain.machines[machine_name]
        incus_name = prefix_name(machine.full_name, ctx, nesting_cfg)

        if incus_name in existing_instances:
            instance = existing_instances[incus_name]
            if instance.status == "Stopped":
                actions.append(
                    Action(
                        verb="start",
                        resource="instance",
                        target=incus_name,
                        project=project_name,
                        detail=f"Démarrer instance {incus_name}",
                    )
                )
            # Profil GUI manquant sur instance existante
            if GUI_PROFILE_NAME in machine.profiles:
                real_profiles = getattr(instance, "profiles", [])
                if GUI_PROFILE_NAME not in real_profiles:
                    actions.append(
                        Action(
                            verb="update",
                            resource="profile",
                            target=incus_name,
                            project=project_name,
                            detail=f"Appliquer profil {GUI_PROFILE_NAME} à {incus_name}",
                        )
                    )
        else:
            detail = _instance_create_detail(machine, infra, incus_name)
            actions.append(
                Action(
                    verb="create",
                    resource="instance",
                    target=incus_name,
                    project=project_name,
                    detail=detail,
                )
            )
            actions.append(
                Action(
                    verb="start",
                    resource="instance",
                    target=incus_name,
                    project=project_name,
                    detail=f"Démarrer instance {incus_name}",
                )
            )

    return actions


def _instance_create_detail(
    machine: Machine,
    infra: Infrastructure,
    incus_name: str,
) -> str:
    """Génère la description détaillée pour la création d'une instance."""
    image = infra.config.defaults.os_image
    parts = [
        f"Créer instance {incus_name}",
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
    ctx: NestingContext,
    gui_info: GuiInfo | None = None,
) -> None:
    """Exécute les actions d'un domaine. Best-effort."""
    domain_failed = False
    created_machines: dict[str, Machine] = {}

    for action in actions:
        if domain_failed:
            result.errors.append((action, "Ignoré suite à une erreur précédente"))
            continue

        try:
            _execute_action(action, domain, infra, driver, ctx, gui_info)
            result.executed.append(action)

            if action.verb == "create" and action.resource == "instance":
                machine = _find_machine(action.target, domain, infra.config.nesting, ctx)
                created_machines[action.target] = machine

            if action.verb == "start" and action.resource == "instance":
                machine = created_machines.get(action.target)
                if machine is not None:
                    _inject_context_files(action.target, action.project, machine, driver, ctx)

        except (IncusError, ValueError) as e:
            result.errors.append((action, str(e)))
            domain_failed = True


def _execute_action(
    action: Action,
    domain: Domain,
    infra: Infrastructure,
    driver: IncusDriver,
    ctx: NestingContext,
    gui_info: GuiInfo | None = None,
) -> None:
    """Exécute une action unique."""
    if action.verb == "create" and action.resource == "project":
        driver.project_create(action.target, description=domain.description)

    elif action.verb == "create" and action.resource == "profile":
        # Idempotent : Incus copie les profils de default dans les nouveaux projets
        if driver.profile_exists(action.target, action.project):
            log.info("Profil %s déjà présent dans %s — skip", action.target, action.project)
        elif action.target == GUI_PROFILE_NAME and gui_info and gui_info.detected:
            create_gui_profile(driver, action.project, gui_info)
        elif action.target == GPU_PROFILE_NAME:
            driver.profile_create(action.target, action.project)
            driver.profile_device_add(
                action.target,
                "gpu",
                "gpu",
                {"gid": "44", "uid": "0"},
                project=action.project,
            )
        elif action.target in domain.profiles:
            # Profil custom défini dans le domaine
            profile = domain.profiles[action.target]
            driver.profile_create(action.target, action.project)
            for dev_name, dev_cfg in profile.devices.items():
                cfg = dict(dev_cfg)  # copie pour ne pas modifier l'original
                dtype = cfg.pop("type", "none")
                driver.profile_device_add(
                    action.target,
                    dev_name,
                    dtype,
                    cfg,
                    project=action.project,
                )
            if profile.config:
                driver.profile_config_set(action.target, action.project, profile.config)
        else:
            driver.profile_create(action.target, action.project)

    elif action.verb == "create" and action.resource == "network":
        config = {}
        if domain.gateway:
            config["ipv4.address"] = f"{domain.gateway}/24"
            config["ipv4.nat"] = "true"
        driver.network_create(action.target, action.project, config=config)

    elif action.verb == "create" and action.resource == "instance":
        machine = _find_machine(action.target, domain, infra.config.nesting, ctx)

        # Config de sécurité nesting (base), puis config explicite (override)
        config = dict(nesting_security_config(ctx.absolute_level))
        if not machine.ephemeral:
            config["security.protection.delete"] = "true"
        for k, v in machine.config.items():
            if k.startswith("security.") and k in config and v != config[k]:
                log.warning(
                    "machine.config override nesting : %s=%s (nesting: %s)",
                    k,
                    v,
                    config[k],
                )
            config[k] = v

        network_name = prefix_name(domain.network_name, ctx, infra.config.nesting)

        driver.instance_create(
            name=action.target,
            project=action.project,
            image=infra.config.defaults.os_image,
            instance_type=machine.incus_type,
            profiles=machine.profiles,
            config=config,
            network=network_name,
        )

    elif action.verb == "start" and action.resource == "instance":
        driver.instance_start(action.target, action.project)

    elif action.verb == "stop" and action.resource == "instance":
        driver.instance_stop(action.target, action.project)

    elif action.verb == "delete" and action.resource == "instance":
        driver.instance_delete(action.target, action.project)

    elif action.verb == "update" and action.resource == "profile":
        # Appliquer un profil GUI à une instance existante
        from anklume.engine.gui import prepare_gui_dirs

        if gui_info and gui_info.detected:
            prepare_gui_dirs(driver, action.target, action.project, gui_info)
        driver.instance_profile_add(action.target, GUI_PROFILE_NAME, action.project)

    else:
        msg = f"Action inconnue : {action.verb}/{action.resource}"
        raise ValueError(msg)


def _find_machine(
    incus_name: str,
    domain: Domain,
    nesting_cfg: NestingConfig,
    ctx: NestingContext,
) -> Machine:
    """Retrouve la Machine depuis le nom Incus (potentiellement préfixé)."""
    logical_name = unprefix_name(incus_name, ctx, nesting_cfg)
    short_name = logical_name.removeprefix(f"{domain.name}-")
    machine = domain.machines.get(short_name)
    if not machine:
        msg = f"Machine introuvable : {incus_name}"
        raise ValueError(msg)
    return machine


def _inject_context_files(
    incus_name: str,
    project: str,
    machine: Machine,
    driver: IncusDriver,
    ctx: NestingContext,
) -> None:
    """Injecte les fichiers de contexte /etc/anklume/ dans une instance.

    Best-effort : si l'injection échoue, un warning est loggé.
    Batch en une seule commande shell pour minimiser les appels subprocess.
    """
    files = context_files_for_instance(ctx, machine.type)

    # Batch : mkdir + écriture des 4 fichiers en une seule commande
    # shlex.quote() empêche l'injection shell via les valeurs
    import shlex

    parts = ["mkdir -p /etc/anklume"]
    for filename, value in files.items():
        safe_value = shlex.quote(value)
        safe_name = shlex.quote(filename)
        parts.append(f"printf '%s' {safe_value} > /etc/anklume/{safe_name}")
    script = " && ".join(parts)

    try:
        driver.instance_exec(incus_name, project, ["sh", "-c", script])
    except IncusError:
        log.warning("Injection des fichiers de contexte échouée pour %s", incus_name)
