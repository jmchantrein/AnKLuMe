"""Tests unitaires pour engine/destroy.py.

Testé avec IncusDriver mocké — vérifie la logique de destruction
avec/sans --force et la protection ephemeral.
"""

from __future__ import annotations

from anklume.engine.destroy import destroy
from anklume.engine.incus_driver import (
    IncusError,
    IncusInstance,
    IncusNetwork,
    IncusProject,
)
from anklume.engine.nesting import NestingContext

from .conftest import make_domain, make_infra, make_machine, mock_driver

# ============================================================
# Infrastructure vide
# ============================================================


class TestEmptyInfra:
    def test_no_domains(self) -> None:
        infra = make_infra()
        driver = mock_driver()
        result = destroy(infra, driver)
        assert result.actions == []
        assert result.success is True

    def test_disabled_domain_skipped(self) -> None:
        domain = make_domain("pro", enabled=False)
        infra = make_infra(domains={"pro": domain})
        driver = mock_driver()
        result = destroy(infra, driver)
        assert result.actions == []


# ============================================================
# Destroy sans --force (respect ephemeral)
# ============================================================


class TestDestroyNoForce:
    def test_ephemeral_instance_deleted(self) -> None:
        """Instance éphémère → arrêtée et supprimée."""
        machine = make_machine("dev", "pro", ephemeral=True)
        domain = make_domain("pro", machines={"dev": machine}, ephemeral=True)
        infra = make_infra(domains={"pro": domain})

        driver = mock_driver(
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

        result = destroy(infra, driver)

        verbs = [a.verb for a in result.executed]
        assert "stop" in verbs
        assert "delete" in verbs
        # Projet et réseau supprimés aussi (toutes instances supprimées)
        resources = [a.resource for a in result.executed]
        assert "network" in resources
        assert "project" in resources
        assert result.success is True

    def test_non_ephemeral_instance_skipped(self) -> None:
        """Instance non-éphémère → ignorée sans --force."""
        machine = make_machine("dev", "pro", ephemeral=False)
        domain = make_domain("pro", machines={"dev": machine})
        infra = make_infra(domains={"pro": domain})

        driver = mock_driver(
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

        result = destroy(infra, driver)

        # Aucune action d'instance exécutée
        instance_deletes = [a for a in result.executed if a.resource == "instance"]
        assert len(instance_deletes) == 0
        # Instance dans skipped
        assert len(result.skipped) == 1
        assert result.skipped[0][0] == "pro-dev"
        # Projet et réseau conservés
        driver.network_delete.assert_not_called()
        driver.project_delete.assert_not_called()

    def test_mixed_ephemeral(self) -> None:
        """Un éphémère + un protégé → seul l'éphémère est supprimé."""
        m1 = make_machine("temp", "pro", ephemeral=True)
        m2 = make_machine("stable", "pro", ephemeral=False)
        domain = make_domain("pro", machines={"temp": m1, "stable": m2})
        infra = make_infra(domains={"pro": domain})

        driver = mock_driver(
            projects=[IncusProject(name="pro")],
            networks={"pro": [IncusNetwork(name="net-pro")]},
            instances={
                "pro": [
                    IncusInstance(
                        name="pro-temp",
                        status="Running",
                        type="container",
                        project="pro",
                    ),
                    IncusInstance(
                        name="pro-stable",
                        status="Running",
                        type="container",
                        project="pro",
                    ),
                ]
            },
        )

        result = destroy(infra, driver)

        # pro-temp supprimée, pro-stable ignorée
        deleted = [
            a.target for a in result.executed if a.verb == "delete" and a.resource == "instance"
        ]
        assert "pro-temp" in deleted
        assert "pro-stable" not in deleted
        assert len(result.skipped) == 1
        assert result.skipped[0][0] == "pro-stable"
        # Réseau et projet conservés (instance protégée reste)
        driver.network_delete.assert_not_called()
        driver.project_delete.assert_not_called()

    def test_stopped_instance_deleted_directly(self) -> None:
        """Instance éphémère déjà arrêtée → supprimée sans stop."""
        machine = make_machine("dev", "pro", ephemeral=True)
        domain = make_domain("pro", machines={"dev": machine}, ephemeral=True)
        infra = make_infra(domains={"pro": domain})

        driver = mock_driver(
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

        result = destroy(infra, driver)

        verbs = [a.verb for a in result.executed if a.resource == "instance"]
        assert "stop" not in verbs
        assert "delete" in verbs

    def test_absent_instance_no_action(self) -> None:
        """Instance absente dans Incus → rien à faire."""
        machine = make_machine("dev", "pro", ephemeral=True)
        domain = make_domain("pro", machines={"dev": machine}, ephemeral=True)
        infra = make_infra(domains={"pro": domain})

        driver = mock_driver(
            projects=[IncusProject(name="pro")],
            networks={"pro": [IncusNetwork(name="net-pro")]},
            instances={"pro": []},
        )

        result = destroy(infra, driver)

        instance_actions = [a for a in result.actions if a.resource == "instance"]
        assert len(instance_actions) == 0
        # Réseau et projet supprimés (aucune instance restante)
        resources = [a.resource for a in result.executed]
        assert "network" in resources
        assert "project" in resources


# ============================================================
# Destroy avec --force
# ============================================================


class TestDestroyForce:
    def test_force_deletes_protected_instance(self) -> None:
        """--force supprime même les instances non-éphémères."""
        machine = make_machine("dev", "pro", ephemeral=False)
        domain = make_domain("pro", machines={"dev": machine})
        infra = make_infra(domains={"pro": domain})

        driver = mock_driver(
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

        result = destroy(infra, driver, force=True)

        verbs = [a.verb for a in result.executed]
        assert "stop" in verbs
        assert "unprotect" in verbs
        assert "delete" in verbs
        assert len(result.skipped) == 0
        # Projet et réseau aussi supprimés
        resources = [a.resource for a in result.executed]
        assert "network" in resources
        assert "project" in resources

    def test_force_unprotect_before_delete(self) -> None:
        """--force retire la protection AVANT la suppression."""
        machine = make_machine("dev", "pro", ephemeral=False)
        domain = make_domain("pro", machines={"dev": machine})
        infra = make_infra(domains={"pro": domain})

        driver = mock_driver(
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

        result = destroy(infra, driver, force=True)

        instance_actions = [a for a in result.executed if a.resource == "instance"]
        verbs = [a.verb for a in instance_actions]
        # L'ordre doit être : stop → unprotect → delete
        assert verbs.index("stop") < verbs.index("unprotect")
        assert verbs.index("unprotect") < verbs.index("delete")

    def test_force_ephemeral_no_unprotect(self) -> None:
        """--force + éphémère → pas de unprotect (pas de protection)."""
        machine = make_machine("dev", "pro", ephemeral=True)
        domain = make_domain("pro", machines={"dev": machine}, ephemeral=True)
        infra = make_infra(domains={"pro": domain})

        driver = mock_driver(
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

        result = destroy(infra, driver, force=True)

        verbs = [a.verb for a in result.executed if a.resource == "instance"]
        assert "unprotect" not in verbs


# ============================================================
# Dry-run
# ============================================================


class TestDestroyDryRun:
    def test_dry_run_no_mutations(self) -> None:
        """En dry-run, le driver ne doit jamais être appelé."""
        machine = make_machine("dev", "pro", ephemeral=True)
        domain = make_domain("pro", machines={"dev": machine}, ephemeral=True)
        infra = make_infra(domains={"pro": domain})

        driver = mock_driver(
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

        result = destroy(infra, driver, dry_run=True)

        assert len(result.actions) > 0
        assert len(result.executed) == 0
        driver.instance_stop.assert_not_called()
        driver.instance_delete.assert_not_called()
        driver.network_delete.assert_not_called()
        driver.project_delete.assert_not_called()


# ============================================================
# Gestion d'erreurs
# ============================================================


class TestDestroyErrors:
    def test_error_on_stop_reported(self) -> None:
        """Si l'arrêt échoue → rapporté dans errors."""
        machine = make_machine("dev", "pro", ephemeral=True)
        domain = make_domain("pro", machines={"dev": machine}, ephemeral=True)
        infra = make_infra(domains={"pro": domain})

        driver = mock_driver(
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
        driver.instance_stop.side_effect = IncusError(
            command=["incus", "stop"], returncode=1, stderr="timeout"
        )

        result = destroy(infra, driver)

        assert not result.success
        assert len(result.errors) > 0

    def test_project_missing_no_error(self) -> None:
        """Si le projet n'existe pas dans Incus → rien à faire, pas d'erreur."""
        machine = make_machine("dev", "pro", ephemeral=True)
        domain = make_domain("pro", machines={"dev": machine}, ephemeral=True)
        infra = make_infra(domains={"pro": domain})

        driver = mock_driver()

        result = destroy(infra, driver)
        assert result.success is True
        assert result.actions == []

    def test_error_on_one_domain_others_continue(self) -> None:
        """Erreur sur un domaine → les autres continuent."""
        m1 = make_machine("dev", "alpha", ephemeral=True)
        m2 = make_machine("web", "beta", ephemeral=True)
        d1 = make_domain("alpha", machines={"dev": m1}, ephemeral=True)
        d2 = make_domain("beta", machines={"web": m2}, ephemeral=True)
        infra = make_infra(domains={"alpha": d1, "beta": d2})

        call_count = 0

        def fail_first_stop(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise IncusError(command=["incus", "stop"], returncode=1, stderr="failed")

        driver = mock_driver(
            projects=[IncusProject(name="alpha"), IncusProject(name="beta")],
            networks={
                "alpha": [IncusNetwork(name="net-alpha")],
                "beta": [IncusNetwork(name="net-beta")],
            },
            instances={
                "alpha": [
                    IncusInstance(
                        name="alpha-dev",
                        status="Running",
                        type="container",
                        project="alpha",
                    )
                ],
                "beta": [
                    IncusInstance(
                        name="beta-web",
                        status="Running",
                        type="container",
                        project="beta",
                    )
                ],
            },
        )
        driver.instance_stop.side_effect = fail_first_stop

        result = destroy(infra, driver)

        # Il y a des erreurs pour alpha
        assert len(result.errors) > 0
        # Mais beta a été traité (au moins des actions exécutées)
        assert len(result.executed) > 0


# ============================================================
# Nesting
# ============================================================


class TestDestroyNesting:
    def test_nesting_prefix_applied(self) -> None:
        """Avec nesting L1, les noms Incus sont préfixés."""
        machine = make_machine("dev", "pro", ephemeral=True)
        domain = make_domain("pro", machines={"dev": machine}, ephemeral=True)
        infra = make_infra(domains={"pro": domain})

        ctx = NestingContext(absolute_level=1)

        driver = mock_driver(
            projects=[IncusProject(name="001-pro")],
            networks={"001-pro": [IncusNetwork(name="001-net-pro")]},
            instances={
                "001-pro": [
                    IncusInstance(
                        name="001-pro-dev",
                        status="Running",
                        type="container",
                        project="001-pro",
                    )
                ]
            },
        )

        result = destroy(infra, driver, nesting_context=ctx)

        # Les actions ciblent les noms préfixés
        stop_action = next(a for a in result.executed if a.verb == "stop")
        assert stop_action.target == "001-pro-dev"
        assert stop_action.project == "001-pro"


# ============================================================
# Ordre de destruction
# ============================================================


class TestDestroyOrder:
    def test_reverse_order(self) -> None:
        """Destruction dans l'ordre inverse : instances → réseau → projet."""
        machine = make_machine("dev", "pro", ephemeral=True)
        domain = make_domain("pro", machines={"dev": machine}, ephemeral=True)
        infra = make_infra(domains={"pro": domain})

        driver = mock_driver(
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

        result = destroy(infra, driver)

        resources = [a.resource for a in result.executed]
        # instance(s) avant network avant project
        last_instance = max(i for i, r in enumerate(resources) if r == "instance")
        network_idx = resources.index("network")
        project_idx = resources.index("project")
        assert last_instance < network_idx < project_idx


# ============================================================
# DestroyResult
# ============================================================


class TestDestroyResult:
    def test_success_no_errors(self) -> None:
        from anklume.engine.destroy import DestroyResult

        result = DestroyResult()
        assert result.success is True

    def test_failure_with_errors(self) -> None:
        from anklume.engine.destroy import DestroyAction, DestroyResult

        action = DestroyAction("delete", "instance", "pro-dev", "pro", "test")
        result = DestroyResult(errors=[(action, "failed")])
        assert result.success is False
