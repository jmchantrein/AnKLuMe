"""Tests unitaires pour engine/ops.py — opérations d'inspection.

Testé avec IncusDriver mocké — vérifie list_instances,
get_instance_info, list_domains, compute_network_status.
"""

from __future__ import annotations

from unittest.mock import patch

from anklume.engine.incus_driver import (
    IncusInstance,
    IncusNetwork,
    IncusProject,
    IncusSnapshot,
)
from anklume.engine.nesting import NestingContext
from anklume.engine.ops import (
    compute_network_status,
    get_instance_info,
    list_domains,
    list_instances,
)

from .conftest import make_domain, make_infra, make_machine, mock_driver

# ============================================================
# list_instances
# ============================================================


class TestListInstances:
    def test_empty_infra(self) -> None:
        infra = make_infra()
        driver = mock_driver()
        result = list_instances(infra, driver)
        assert result == []

    def test_disabled_domain_skipped(self) -> None:
        domain = make_domain("pro", enabled=False)
        infra = make_infra(domains={"pro": domain})
        driver = mock_driver()
        result = list_instances(infra, driver)
        assert result == []

    def test_single_running_instance(self) -> None:
        machine = make_machine("dev", "pro", ip="10.100.1.2")
        domain = make_domain("pro", machines={"dev": machine})
        infra = make_infra(domains={"pro": domain})

        driver = mock_driver(
            projects=[IncusProject(name="pro")],
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

        result = list_instances(infra, driver)
        assert len(result) == 1
        inst = result[0]
        assert inst.name == "pro-dev"
        assert inst.domain == "pro"
        assert inst.machine_type == "lxc"
        assert inst.state == "Running"
        assert inst.ip == "10.100.1.2"
        assert inst.trust_level == "semi-trusted"

    def test_absent_instance(self) -> None:
        machine = make_machine("dev", "pro")
        domain = make_domain("pro", machines={"dev": machine})
        infra = make_infra(domains={"pro": domain})

        driver = mock_driver(
            projects=[IncusProject(name="pro")],
            instances={"pro": []},
        )

        result = list_instances(infra, driver)
        assert result[0].state == "Absent"

    def test_project_missing_all_absent(self) -> None:
        machine = make_machine("dev", "pro")
        domain = make_domain("pro", machines={"dev": machine})
        infra = make_infra(domains={"pro": domain})

        driver = mock_driver()
        result = list_instances(infra, driver)
        assert result[0].state == "Absent"

    def test_multiple_domains(self) -> None:
        m1 = make_machine("dev", "pro", ip="10.100.1.2")
        m2 = make_machine("web", "perso", ip="10.100.2.2")
        d1 = make_domain("pro", machines={"dev": m1})
        d2 = make_domain("perso", machines={"web": m2})
        infra = make_infra(domains={"pro": d1, "perso": d2})

        driver = mock_driver(
            projects=[IncusProject(name="pro"), IncusProject(name="perso")],
            instances={
                "pro": [
                    IncusInstance(name="pro-dev", status="Running", type="container", project="pro")
                ],
                "perso": [
                    IncusInstance(
                        name="perso-web", status="Stopped", type="container", project="perso"
                    )
                ],
            },
        )

        result = list_instances(infra, driver)
        assert len(result) == 2
        names = {i.name for i in result}
        assert names == {"pro-dev", "perso-web"}

    def test_gpu_flag_propagated(self) -> None:
        machine = make_machine("gpu-server", "ai-tools", ip="10.100.3.1")
        machine.gpu = True
        domain = make_domain("ai-tools", machines={"gpu-server": machine})
        infra = make_infra(domains={"ai-tools": domain})

        driver = mock_driver(
            projects=[IncusProject(name="ai-tools")],
            instances={"ai-tools": []},
        )

        result = list_instances(infra, driver)
        assert result[0].gpu is True

    def test_vm_type(self) -> None:
        machine = make_machine("desktop", "pro", type="vm")
        domain = make_domain("pro", machines={"desktop": machine})
        infra = make_infra(domains={"pro": domain})

        driver = mock_driver(
            projects=[IncusProject(name="pro")],
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

        result = list_instances(infra, driver)
        assert result[0].machine_type == "vm"

    def test_roles_propagated(self) -> None:
        machine = make_machine("dev", "pro", roles=["base", "openssh_server"])
        domain = make_domain("pro", machines={"dev": machine})
        infra = make_infra(domains={"pro": domain})

        driver = mock_driver(
            projects=[IncusProject(name="pro")],
            instances={"pro": []},
        )

        result = list_instances(infra, driver)
        assert result[0].roles == ["base", "openssh_server"]

    def test_nesting_prefix(self) -> None:
        machine = make_machine("dev", "pro")
        domain = make_domain("pro", machines={"dev": machine})
        infra = make_infra(domains={"pro": domain})
        ctx = NestingContext(absolute_level=1)

        driver = mock_driver(
            projects=[IncusProject(name="001-pro")],
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

        result = list_instances(infra, driver, nesting_context=ctx)
        assert result[0].name == "pro-dev"
        assert result[0].state == "Running"


# ============================================================
# get_instance_info
# ============================================================


class TestGetInstanceInfo:
    def test_unknown_instance(self) -> None:
        infra = make_infra()
        driver = mock_driver()
        result = get_instance_info(infra, driver, "nonexistent")
        assert result is None

    def test_existing_instance_with_snapshots(self) -> None:
        machine = make_machine("dev", "pro", ip="10.100.1.2", roles=["base"])
        domain = make_domain("pro", machines={"dev": machine})
        infra = make_infra(domains={"pro": domain})

        driver = mock_driver(
            projects=[IncusProject(name="pro")],
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
            snapshots={
                "pro-dev": [
                    IncusSnapshot(name="snap-1", created_at="2025-01-01"),
                    IncusSnapshot(name="snap-2", created_at="2025-01-02"),
                ]
            },
        )

        result = get_instance_info(infra, driver, "pro-dev")
        assert result is not None
        assert result.name == "pro-dev"
        assert result.domain == "pro"
        assert result.state == "Running"
        assert result.ip == "10.100.1.2"
        assert result.snapshots == ["snap-1", "snap-2"]
        assert result.roles == ["base"]

    def test_absent_instance_no_snapshots(self) -> None:
        machine = make_machine("dev", "pro")
        domain = make_domain("pro", machines={"dev": machine})
        infra = make_infra(domains={"pro": domain})

        driver = mock_driver()
        result = get_instance_info(infra, driver, "pro-dev")
        assert result is not None
        assert result.state == "Absent"
        assert result.snapshots == []

    def test_disabled_domain_skipped(self) -> None:
        machine = make_machine("dev", "pro")
        domain = make_domain("pro", machines={"dev": machine}, enabled=False)
        infra = make_infra(domains={"pro": domain})

        driver = mock_driver()
        result = get_instance_info(infra, driver, "pro-dev")
        # Disabled domains are skipped (only enabled_domains are searched)
        assert result is None

    def test_trust_level_from_domain(self) -> None:
        machine = make_machine("dev", "pro")
        domain = make_domain("pro", machines={"dev": machine})
        domain.trust_level = "admin"
        infra = make_infra(domains={"pro": domain})

        driver = mock_driver(
            projects=[IncusProject(name="pro")],
            instances={"pro": []},
        )

        result = get_instance_info(infra, driver, "pro-dev")
        assert result is not None
        assert result.trust_level == "admin"


# ============================================================
# list_domains
# ============================================================


class TestListDomains:
    def test_empty(self) -> None:
        infra = make_infra()
        result = list_domains(infra)
        assert result == []

    def test_single_domain(self) -> None:
        machine = make_machine("dev", "pro")
        domain = make_domain("pro", machines={"dev": machine})
        infra = make_infra(domains={"pro": domain})

        result = list_domains(infra)
        assert len(result) == 1
        d = result[0]
        assert d.name == "pro"
        assert d.enabled is True
        assert d.trust_level == "semi-trusted"
        assert d.machine_count == 1
        assert d.ephemeral is False

    def test_multiple_domains_sorted(self) -> None:
        d1 = make_domain("pro")
        d2 = make_domain("perso")
        d3 = make_domain("ai-tools", enabled=False)
        infra = make_infra(domains={"pro": d1, "perso": d2, "ai-tools": d3})

        result = list_domains(infra)
        assert [d.name for d in result] == ["ai-tools", "perso", "pro"]

    def test_disabled_domain_included(self) -> None:
        domain = make_domain("pro", enabled=False)
        infra = make_infra(domains={"pro": domain})

        result = list_domains(infra)
        assert len(result) == 1
        assert result[0].enabled is False

    def test_ephemeral_flag(self) -> None:
        domain = make_domain("temp", ephemeral=True)
        infra = make_infra(domains={"temp": domain})

        result = list_domains(infra)
        assert result[0].ephemeral is True

    def test_trust_level_propagated(self) -> None:
        domain = make_domain("sec")
        domain.trust_level = "untrusted"
        infra = make_infra(domains={"sec": domain})

        result = list_domains(infra)
        assert result[0].trust_level == "untrusted"


# ============================================================
# compute_network_status
# ============================================================


class TestComputeNetworkStatus:
    def test_empty_infra(self) -> None:
        infra = make_infra()
        driver = mock_driver()

        with patch("anklume.engine.ops._check_nftables", return_value=(False, 0)):
            result = compute_network_status(infra, driver)

        assert result.networks == []
        assert result.nftables_present is False

    def test_network_exists(self) -> None:
        domain = make_domain("pro", subnet="10.100.1.0/24", gateway="10.100.1.1")
        infra = make_infra(domains={"pro": domain})

        driver = mock_driver(
            projects=[IncusProject(name="pro")],
            networks={"pro": [IncusNetwork(name="net-pro")]},
        )

        with patch("anklume.engine.ops._check_nftables", return_value=(True, 5)):
            result = compute_network_status(infra, driver)

        assert len(result.networks) == 1
        net = result.networks[0]
        assert net.domain == "pro"
        assert net.bridge == "net-pro"
        assert net.subnet == "10.100.1.0/24"
        assert net.gateway == "10.100.1.1"
        assert net.exists is True
        assert result.nftables_present is True
        assert result.nftables_rule_count == 5

    def test_network_absent(self) -> None:
        domain = make_domain("pro")
        infra = make_infra(domains={"pro": domain})

        driver = mock_driver()

        with patch("anklume.engine.ops._check_nftables", return_value=(False, 0)):
            result = compute_network_status(infra, driver)

        assert result.networks[0].exists is False

    def test_nesting_prefix(self) -> None:
        domain = make_domain("pro")
        infra = make_infra(domains={"pro": domain})
        ctx = NestingContext(absolute_level=1)

        driver = mock_driver(
            projects=[IncusProject(name="001-pro")],
            networks={"001-pro": [IncusNetwork(name="001-net-pro")]},
        )

        with patch("anklume.engine.ops._check_nftables", return_value=(False, 0)):
            result = compute_network_status(infra, driver, nesting_context=ctx)

        assert result.networks[0].exists is True

    def test_multiple_domains(self) -> None:
        d1 = make_domain("pro")
        d2 = make_domain("perso")
        infra = make_infra(domains={"pro": d1, "perso": d2})

        driver = mock_driver(
            projects=[IncusProject(name="pro")],
            networks={"pro": [IncusNetwork(name="net-pro")]},
        )

        with patch("anklume.engine.ops._check_nftables", return_value=(False, 0)):
            result = compute_network_status(infra, driver)

        assert len(result.networks) == 2
        states = {n.domain: n.exists for n in result.networks}
        assert states["pro"] is True
        assert states["perso"] is False
