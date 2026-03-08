"""Tests unitaires pour engine/status.py.

Testé avec IncusDriver mocké — vérifie la comparaison
état déclaré vs état réel.
"""

from __future__ import annotations

from anklume.engine.incus_driver import (
    IncusInstance,
    IncusNetwork,
    IncusProject,
)
from anklume.engine.nesting import NestingContext
from anklume.engine.status import compute_status

from .conftest import make_domain, make_infra, make_machine, mock_driver

# ============================================================
# Infrastructure vide
# ============================================================


class TestEmptyInfra:
    def test_no_domains(self) -> None:
        infra = make_infra()
        driver = mock_driver()
        result = compute_status(infra, driver)
        assert result.domains == []
        assert result.projects_total == 0
        assert result.instances_total == 0

    def test_disabled_domain_skipped(self) -> None:
        domain = make_domain("pro", enabled=False)
        infra = make_infra(domains={"pro": domain})
        driver = mock_driver()
        result = compute_status(infra, driver)
        assert result.domains == []


# ============================================================
# Tout synchronisé
# ============================================================


class TestAllSynced:
    def test_single_domain_single_instance_running(self) -> None:
        machine = make_machine("dev", "pro")
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

        result = compute_status(infra, driver)
        assert len(result.domains) == 1
        ds = result.domains[0]
        assert ds.name == "pro"
        assert ds.project_exists is True
        assert ds.network_exists is True
        assert len(ds.instances) == 1
        assert ds.instances[0].name == "pro-dev"
        assert ds.instances[0].state == "Running"
        assert ds.instances[0].synced is True

    def test_summary_counts(self) -> None:
        m1 = make_machine("dev", "pro")
        m2 = make_machine("web", "perso")
        d1 = make_domain("pro", machines={"dev": m1})
        d2 = make_domain("perso", machines={"web": m2})
        infra = make_infra(domains={"pro": d1, "perso": d2})

        driver = mock_driver(
            projects=[IncusProject(name="pro"), IncusProject(name="perso")],
            networks={
                "pro": [IncusNetwork(name="net-pro")],
                "perso": [IncusNetwork(name="net-perso")],
            },
            instances={
                "pro": [
                    IncusInstance(name="pro-dev", status="Running", type="container", project="pro")
                ],
                "perso": [
                    IncusInstance(
                        name="perso-web", status="Running",
                        type="container", project="perso",
                    )
                ],
            },
        )

        result = compute_status(infra, driver)
        assert result.projects_total == 2
        assert result.projects_found == 2
        assert result.networks_total == 2
        assert result.networks_found == 2
        assert result.instances_total == 2
        assert result.instances_running == 2


# ============================================================
# Désynchronisé
# ============================================================


class TestDesync:
    def test_instance_stopped(self) -> None:
        machine = make_machine("dev", "pro")
        domain = make_domain("pro", machines={"dev": machine})
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

        result = compute_status(infra, driver)
        inst = result.domains[0].instances[0]
        assert inst.state == "Stopped"
        assert inst.synced is False

    def test_instance_absent(self) -> None:
        machine = make_machine("dev", "pro")
        domain = make_domain("pro", machines={"dev": machine})
        infra = make_infra(domains={"pro": domain})

        driver = mock_driver(
            projects=[IncusProject(name="pro")],
            networks={"pro": [IncusNetwork(name="net-pro")]},
            instances={"pro": []},
        )

        result = compute_status(infra, driver)
        inst = result.domains[0].instances[0]
        assert inst.state == "Absent"
        assert inst.synced is False

    def test_project_missing(self) -> None:
        machine = make_machine("dev", "pro")
        domain = make_domain("pro", machines={"dev": machine})
        infra = make_infra(domains={"pro": domain})

        driver = mock_driver()

        result = compute_status(infra, driver)
        ds = result.domains[0]
        assert ds.project_exists is False
        assert ds.network_exists is False
        # Toutes les instances sont Absent si le projet n'existe pas
        assert all(i.state == "Absent" for i in ds.instances)

    def test_network_missing(self) -> None:
        machine = make_machine("dev", "pro")
        domain = make_domain("pro", machines={"dev": machine})
        infra = make_infra(domains={"pro": domain})

        driver = mock_driver(
            projects=[IncusProject(name="pro")],
            networks={"pro": []},
            instances={"pro": []},
        )

        result = compute_status(infra, driver)
        ds = result.domains[0]
        assert ds.project_exists is True
        assert ds.network_exists is False

    def test_mixed_states(self) -> None:
        """Deux instances : une running, une absente."""
        machines = {
            "dev": make_machine("dev", "pro"),
            "desktop": make_machine("desktop", "pro"),
        }
        domain = make_domain("pro", machines=machines)
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

        result = compute_status(infra, driver)
        instances = {i.name: i for i in result.domains[0].instances}
        assert instances["pro-dev"].synced is True
        assert instances["pro-desktop"].synced is False
        assert instances["pro-desktop"].state == "Absent"
        assert result.instances_running == 1
        assert result.instances_total == 2


# ============================================================
# Plusieurs domaines
# ============================================================


class TestMultipleDomains:
    def test_two_domains_sorted(self) -> None:
        d1 = make_domain("pro", machines={"dev": make_machine("dev", "pro")})
        d2 = make_domain("perso", machines={"web": make_machine("web", "perso")})
        infra = make_infra(domains={"pro": d1, "perso": d2})
        driver = mock_driver()

        result = compute_status(infra, driver)
        # Domaines triés alphabétiquement
        assert [d.name for d in result.domains] == ["perso", "pro"]


# ============================================================
# Nesting
# ============================================================


class TestStatusNesting:
    def test_nesting_prefix_resolved(self) -> None:
        """Avec nesting L1, les noms Incus sont préfixés."""
        machine = make_machine("dev", "pro")
        domain = make_domain("pro", machines={"dev": machine})
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

        result = compute_status(infra, driver, nesting_context=ctx)
        ds = result.domains[0]
        assert ds.project_exists is True
        assert ds.network_exists is True
        # Le nom affiché est le nom logique (sans préfixe)
        assert ds.instances[0].name == "pro-dev"
        assert ds.instances[0].synced is True


# ============================================================
# Type de machine
# ============================================================


class TestMachineType:
    def test_vm_type_reported(self) -> None:
        machine = make_machine("desktop", "pro", type="vm")
        domain = make_domain("pro", machines={"desktop": machine})
        infra = make_infra(domains={"pro": domain})

        driver = mock_driver(
            projects=[IncusProject(name="pro")],
            networks={"pro": [IncusNetwork(name="net-pro")]},
            instances={
                "pro": [
                    IncusInstance(
                        name="pro-desktop",
                        status="Running",
                        type="virtual-machine",
                        project="pro",
                    )
                ]
            },
        )

        result = compute_status(infra, driver)
        assert result.domains[0].instances[0].machine_type == "vm"
