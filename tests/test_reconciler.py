"""Tests unitaires pour engine/reconciler.py.

Le réconciliateur est testé en mockant IncusDriver — pas besoin
d'Incus réel. On vérifie la logique de diff et la génération
du plan d'actions.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from anklume.engine.incus_driver import (
    IncusDriver,
    IncusInstance,
    IncusNetwork,
    IncusProject,
)
from anklume.engine.models import (
    AddressingConfig,
    Defaults,
    Domain,
    GlobalConfig,
    Infrastructure,
    Machine,
)
from anklume.engine.reconciler import Action, ReconcileResult, reconcile

# --- Helpers ---


def _make_infra(
    domains: dict[str, Domain] | None = None,
    os_image: str = "images:debian/13",
) -> Infrastructure:
    """Crée une Infrastructure minimale pour les tests."""
    return Infrastructure(
        config=GlobalConfig(
            defaults=Defaults(os_image=os_image),
            addressing=AddressingConfig(),
        ),
        domains=domains or {},
        policies=[],
    )


def _make_domain(
    name: str,
    machines: dict[str, Machine] | None = None,
    *,
    enabled: bool = True,
    ephemeral: bool = False,
    subnet: str = "10.120.0.0/24",
    gateway: str = "10.120.0.254",
) -> Domain:
    """Crée un Domain minimal."""
    return Domain(
        name=name,
        description=f"Domaine {name}",
        enabled=enabled,
        ephemeral=ephemeral,
        machines=machines or {},
        subnet=subnet,
        gateway=gateway,
    )


def _make_machine(
    name: str,
    domain: str,
    *,
    type: str = "lxc",
    ip: str = "10.120.0.1",
    ephemeral: bool = False,
    profiles: list[str] | None = None,
    config: dict | None = None,
) -> Machine:
    """Crée une Machine minimale."""
    return Machine(
        name=name,
        full_name=f"{domain}-{name}",
        description=f"Machine {name}",
        type=type,
        ip=ip,
        ephemeral=ephemeral,
        profiles=profiles or ["default"],
        config=config or {},
    )


def _mock_driver(
    projects: list[IncusProject] | None = None,
    networks: dict[str, list[IncusNetwork]] | None = None,
    instances: dict[str, list[IncusInstance]] | None = None,
) -> IncusDriver:
    """Crée un IncusDriver mocké."""
    driver = MagicMock(spec=IncusDriver)
    driver.project_list.return_value = projects or []
    driver.project_exists.side_effect = lambda n: any(p.name == n for p in (projects or []))

    _networks = networks or {}
    driver.network_list.side_effect = lambda p: _networks.get(p, [])
    driver.network_exists.side_effect = lambda n, p: any(
        net.name == n for net in _networks.get(p, [])
    )

    _instances = instances or {}
    driver.instance_list.side_effect = lambda p: _instances.get(p, [])

    return driver


# ============================================================
# Infrastructure vide
# ============================================================


class TestEmptyInfrastructure:
    def test_no_domains_no_actions(self) -> None:
        infra = _make_infra()
        driver = _mock_driver()
        result = reconcile(infra, driver)
        assert result.actions == []
        assert result.errors == []

    def test_disabled_domain_skipped(self) -> None:
        domain = _make_domain("pro", enabled=False)
        infra = _make_infra(domains={"pro": domain})
        driver = _mock_driver()
        result = reconcile(infra, driver)
        assert result.actions == []


# ============================================================
# Création complète (rien n'existe dans Incus)
# ============================================================


class TestFullCreation:
    def test_single_domain_single_machine(self) -> None:
        """Un domaine avec une machine → crée projet + réseau + instance + start."""
        machine = _make_machine("dev", "pro")
        domain = _make_domain("pro", machines={"dev": machine})
        infra = _make_infra(domains={"pro": domain})
        driver = _mock_driver()

        result = reconcile(infra, driver)

        verbs = [a.verb for a in result.actions]
        resources = [a.resource for a in result.actions]

        # Ordre : projet, réseau, instance, start
        assert verbs == ["create", "create", "create", "start"]
        assert resources == ["project", "network", "instance", "instance"]

        # Vérifie les cibles
        assert result.actions[0].target == "pro"
        assert result.actions[1].target == "net-pro"
        assert result.actions[2].target == "pro-dev"
        assert result.actions[3].target == "pro-dev"

    def test_multiple_machines(self) -> None:
        """Plusieurs machines → une action create + start par machine."""
        machines = {
            "dev": _make_machine("dev", "pro", ip="10.120.0.1"),
            "desktop": _make_machine("desktop", "pro", ip="10.120.0.2"),
        }
        domain = _make_domain("pro", machines=machines)
        infra = _make_infra(domains={"pro": domain})
        driver = _mock_driver()

        result = reconcile(infra, driver)

        instance_creates = [
            a for a in result.actions if a.resource == "instance" and a.verb == "create"
        ]
        instance_starts = [
            a for a in result.actions if a.resource == "instance" and a.verb == "start"
        ]
        assert len(instance_creates) == 2
        assert len(instance_starts) == 2

    def test_multiple_domains(self) -> None:
        """Plusieurs domaines → un projet + réseau par domaine."""
        d1 = _make_domain(
            "pro",
            machines={
                "dev": _make_machine("dev", "pro"),
            },
            subnet="10.120.0.0/24",
            gateway="10.120.0.254",
        )
        d2 = _make_domain(
            "perso",
            machines={
                "web": _make_machine("web", "perso", ip="10.120.1.1"),
            },
            subnet="10.120.1.0/24",
            gateway="10.120.1.254",
        )
        infra = _make_infra(domains={"pro": d1, "perso": d2})
        driver = _mock_driver()

        result = reconcile(infra, driver)

        project_creates = [
            a for a in result.actions if a.resource == "project" and a.verb == "create"
        ]
        network_creates = [
            a for a in result.actions if a.resource == "network" and a.verb == "create"
        ]
        assert len(project_creates) == 2
        assert len(network_creates) == 2

    def test_vm_type(self) -> None:
        """Une machine VM doit passer instance_type='virtual-machine'."""
        machine = _make_machine("desktop", "pro", type="vm")
        domain = _make_domain("pro", machines={"desktop": machine})
        infra = _make_infra(domains={"pro": domain})
        driver = _mock_driver()

        result = reconcile(infra, driver)

        create_action = next(
            a for a in result.actions if a.verb == "create" and a.resource == "instance"
        )
        assert "virtual-machine" in create_action.detail or "vm" in create_action.detail.lower()


# ============================================================
# Tout existe déjà (idempotence)
# ============================================================


class TestIdempotence:
    def test_everything_exists_running(self) -> None:
        """Si tout existe et tourne → aucune action."""
        machine = _make_machine("dev", "pro")
        domain = _make_domain("pro", machines={"dev": machine})
        infra = _make_infra(domains={"pro": domain})

        driver = _mock_driver(
            projects=[IncusProject(name="pro")],
            networks={"pro": [IncusNetwork(name="net-pro")]},
            instances={
                "pro": [
                    IncusInstance(
                        name="pro-dev",
                        status="Running",
                        type="container",
                        project="pro",
                    )
                ]
            },
        )

        result = reconcile(infra, driver)
        # Aucune action nécessaire
        assert len(result.actions) == 0

    def test_project_exists_network_missing(self) -> None:
        """Projet existe mais réseau manquant → crée réseau + instance."""
        machine = _make_machine("dev", "pro")
        domain = _make_domain("pro", machines={"dev": machine})
        infra = _make_infra(domains={"pro": domain})

        driver = _mock_driver(
            projects=[IncusProject(name="pro")],
        )

        result = reconcile(infra, driver)
        verbs_resources = [(a.verb, a.resource) for a in result.actions]
        assert ("create", "project") not in verbs_resources
        assert ("create", "network") in verbs_resources
        assert ("create", "instance") in verbs_resources

    def test_instance_stopped(self) -> None:
        """Instance existante mais Stopped → la démarrer."""
        machine = _make_machine("dev", "pro")
        domain = _make_domain("pro", machines={"dev": machine})
        infra = _make_infra(domains={"pro": domain})

        driver = _mock_driver(
            projects=[IncusProject(name="pro")],
            networks={"pro": [IncusNetwork(name="net-pro")]},
            instances={
                "pro": [
                    IncusInstance(
                        name="pro-dev",
                        status="Stopped",
                        type="container",
                        project="pro",
                    )
                ]
            },
        )

        result = reconcile(infra, driver)
        assert len(result.actions) == 1
        assert result.actions[0].verb == "start"
        assert result.actions[0].target == "pro-dev"


# ============================================================
# Protection delete (ephemeral)
# ============================================================


class TestEphemeralProtection:
    def test_non_ephemeral_sets_protection(self) -> None:
        """Machine non-éphémère → security.protection.delete=true dans le detail."""
        machine = _make_machine("dev", "pro", ephemeral=False)
        domain = _make_domain("pro", machines={"dev": machine})
        infra = _make_infra(domains={"pro": domain})
        driver = _mock_driver()

        result = reconcile(infra, driver)
        create = next(a for a in result.actions if a.verb == "create" and a.resource == "instance")
        assert "protection.delete" in create.detail

    def test_ephemeral_no_protection(self) -> None:
        """Machine éphémère → pas de protection delete."""
        machine = _make_machine("dev", "pro", ephemeral=True)
        domain = _make_domain("pro", machines={"dev": machine}, ephemeral=True)
        infra = _make_infra(domains={"pro": domain})
        driver = _mock_driver()

        result = reconcile(infra, driver)
        create = next(a for a in result.actions if a.verb == "create" and a.resource == "instance")
        assert "protection.delete" not in create.detail


# ============================================================
# Dry-run
# ============================================================


class TestDryRun:
    def test_dry_run_does_not_call_driver_mutators(self) -> None:
        """En dry-run, le driver ne doit jamais être appelé pour créer."""
        machine = _make_machine("dev", "pro")
        domain = _make_domain("pro", machines={"dev": machine})
        infra = _make_infra(domains={"pro": domain})
        driver = _mock_driver()

        result = reconcile(infra, driver, dry_run=True)

        # Des actions planifiées existent
        assert len(result.actions) > 0
        # Mais aucune création n'a été appelée sur le driver
        driver.project_create.assert_not_called()
        driver.network_create.assert_not_called()
        driver.instance_create.assert_not_called()
        driver.instance_start.assert_not_called()

    def test_dry_run_returns_same_plan_as_normal(self) -> None:
        """Le plan dry-run doit être identique au plan normal."""
        machine = _make_machine("dev", "pro")
        domain = _make_domain("pro", machines={"dev": machine})
        infra = _make_infra(domains={"pro": domain})

        driver1 = _mock_driver()
        result_dry = reconcile(infra, driver1, dry_run=True)

        driver2 = _mock_driver()
        result_normal = reconcile(infra, driver2, dry_run=False)

        # Mêmes actions planifiées
        assert len(result_dry.actions) == len(result_normal.actions)
        for a, b in zip(result_dry.actions, result_normal.actions, strict=True):
            assert a.verb == b.verb
            assert a.resource == b.resource
            assert a.target == b.target


# ============================================================
# Exécution du plan
# ============================================================


class TestExecution:
    def test_executes_all_actions(self) -> None:
        """Sans dry-run, toutes les actions du plan sont exécutées."""
        machine = _make_machine("dev", "pro")
        domain = _make_domain("pro", machines={"dev": machine})
        infra = _make_infra(domains={"pro": domain})
        driver = _mock_driver()

        result = reconcile(infra, driver)

        # Le driver a été appelé pour créer
        driver.project_create.assert_called_once()
        driver.network_create.assert_called_once()
        driver.instance_create.assert_called_once()
        driver.instance_start.assert_called_once()

        # Toutes les actions exécutées, pas d'erreurs
        assert len(result.executed) == len(result.actions)
        assert len(result.errors) == 0

    def test_error_on_instance_create_reported(self) -> None:
        """Si la création d'instance échoue → rapporté dans errors."""
        from anklume.engine.incus_driver import IncusError

        machine = _make_machine("dev", "pro")
        domain = _make_domain("pro", machines={"dev": machine})
        infra = _make_infra(domains={"pro": domain})
        driver = _mock_driver()
        driver.instance_create.side_effect = IncusError(
            command=["incus", "init"], returncode=1, stderr="image not found"
        )

        result = reconcile(infra, driver)

        # L'erreur est rapportée
        assert len(result.errors) > 0
        error_action, error_msg = result.errors[0]
        assert error_action.resource == "instance"
        assert "image not found" in error_msg

    def test_error_does_not_stop_other_domains(self) -> None:
        """Erreur sur un domaine → les autres domaines continuent."""
        from anklume.engine.incus_driver import IncusError

        d1 = _make_domain(
            "alpha",
            machines={
                "dev": _make_machine("dev", "alpha"),
            },
            subnet="10.120.0.0/24",
            gateway="10.120.0.254",
        )
        d2 = _make_domain(
            "beta",
            machines={
                "web": _make_machine("web", "beta", ip="10.120.1.1"),
            },
            subnet="10.120.1.0/24",
            gateway="10.120.1.254",
        )
        infra = _make_infra(domains={"alpha": d1, "beta": d2})

        driver = _mock_driver()

        call_count = 0

        def fail_first_project(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise IncusError(
                    command=["incus", "project", "create"],
                    returncode=1,
                    stderr="failed",
                )

        driver.project_create.side_effect = fail_first_project

        result = reconcile(infra, driver)

        # Il y a des erreurs pour le premier domaine
        assert len(result.errors) > 0
        # Mais le deuxième domaine a été traité (au moins un appel réussi)
        assert len(result.executed) > 0


# ============================================================
# Réseau — configuration
# ============================================================


class TestNetworkConfig:
    def test_network_name_convention(self) -> None:
        """Le réseau doit s'appeler net-{domain_name}."""
        machine = _make_machine("dev", "pro")
        domain = _make_domain("pro", machines={"dev": machine})
        infra = _make_infra(domains={"pro": domain})
        driver = _mock_driver()

        result = reconcile(infra, driver)
        net_action = next(a for a in result.actions if a.resource == "network")
        assert net_action.target == "net-pro"

    def test_network_includes_gateway(self) -> None:
        """La config réseau doit inclure le gateway du domaine."""
        machine = _make_machine("dev", "pro")
        domain = _make_domain(
            "pro",
            machines={"dev": machine},
            gateway="10.120.0.254",
        )
        infra = _make_infra(domains={"pro": domain})
        driver = _mock_driver()

        result = reconcile(infra, driver)
        net_action = next(a for a in result.actions if a.resource == "network")
        assert "10.120.0.254" in net_action.detail


# ============================================================
# Action dataclass
# ============================================================


class TestAction:
    def test_action_fields(self) -> None:
        action = Action(
            verb="create",
            resource="project",
            target="pro",
            project="pro",
            detail="Créer projet pro",
        )
        assert action.verb == "create"
        assert action.resource == "project"
        assert action.target == "pro"
        assert action.project == "pro"
        assert action.detail == "Créer projet pro"


# ============================================================
# ReconcileResult
# ============================================================


class TestReconcileResult:
    def test_empty_result(self) -> None:
        result = ReconcileResult()
        assert result.actions == []
        assert result.executed == []
        assert result.errors == []
        assert result.success is True

    def test_success_with_actions(self) -> None:
        action = Action("create", "project", "pro", "pro", "test")
        result = ReconcileResult(actions=[action], executed=[action])
        assert result.success is True

    def test_failure_with_errors(self) -> None:
        action = Action("create", "project", "pro", "pro", "test")
        result = ReconcileResult(
            actions=[action],
            errors=[(action, "failed")],
        )
        assert result.success is False
