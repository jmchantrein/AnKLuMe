"""Tests pour engine/import_infra.py — import d'infrastructure existante."""

from __future__ import annotations

from pathlib import Path

import yaml

from anklume.engine.import_infra import (
    ImportResult,
    ScannedDomain,
    ScannedInstance,
    _instance_to_machine_name,
    _instance_type_to_anklume,
    generate_domain_files,
    import_infrastructure,
    scan_incus,
)
from anklume.engine.incus_driver import (
    IncusInstance,
    IncusNetwork,
    IncusProject,
)
from tests.conftest import mock_driver


class TestScanIncus:
    """Tests pour scan_incus."""

    def test_scan_basic(self):
        """Scan d'un projet avec instances et réseau."""
        net_cfg = {"ipv4.address": "10.100.0.1/24"}
        driver = mock_driver(
            projects=[IncusProject(name="pro"), IncusProject(name="default")],
            networks={"pro": [IncusNetwork(name="net-pro", config=net_cfg)]},
            instances={
                "pro": [
                    IncusInstance(
                        name="pro-dev",
                        status="Running",
                        type="container",
                        project="pro",
                    ),
                    IncusInstance(
                        name="pro-mail",
                        status="Stopped",
                        type="container",
                        project="pro",
                    ),
                ]
            },
        )

        domains = scan_incus(driver)

        assert len(domains) == 1
        assert domains[0].project == "pro"
        assert domains[0].network == "net-pro"
        assert domains[0].subnet == "10.100.0.1/24"
        assert len(domains[0].instances) == 2

    def test_scan_skips_default(self):
        """Le projet default est ignoré."""
        driver = mock_driver(
            projects=[IncusProject(name="default")],
        )

        domains = scan_incus(driver)

        assert domains == []

    def test_scan_multiple_projects(self):
        """Scan de plusieurs projets."""
        driver = mock_driver(
            projects=[
                IncusProject(name="pro"),
                IncusProject(name="perso"),
                IncusProject(name="default"),
            ],
            networks={
                "pro": [IncusNetwork(name="net-pro")],
                "perso": [IncusNetwork(name="net-perso")],
            },
            instances={
                "pro": [
                    IncusInstance(
                        name="pro-dev",
                        status="Running",
                        type="container",
                        project="pro",
                    )
                ],
                "perso": [],
            },
        )

        domains = scan_incus(driver)

        assert len(domains) == 2
        project_names = [d.project for d in domains]
        assert "pro" in project_names
        assert "perso" in project_names

    def test_scan_no_network(self):
        """Projet sans réseau net-*."""
        driver = mock_driver(
            projects=[IncusProject(name="pro")],
            networks={"pro": [IncusNetwork(name="lxdbr0")]},
            instances={"pro": []},
        )

        domains = scan_incus(driver)

        assert domains[0].network is None
        assert domains[0].subnet is None

    def test_scan_vm_instance(self):
        """Détection correcte du type VM."""
        driver = mock_driver(
            projects=[IncusProject(name="pro")],
            instances={
                "pro": [
                    IncusInstance(
                        name="pro-router",
                        status="Running",
                        type="virtual-machine",
                        project="pro",
                    ),
                ]
            },
        )

        domains = scan_incus(driver)

        assert domains[0].instances[0].instance_type == "virtual-machine"


class TestInstanceToMachineName:
    """Tests pour _instance_to_machine_name."""

    def test_strip_prefix(self):
        """Retire le préfixe projet."""
        assert _instance_to_machine_name("pro-dev", "pro") == "dev"

    def test_no_prefix(self):
        """Nom sans préfixe retourné tel quel."""
        assert _instance_to_machine_name("standalone", "pro") == "standalone"

    def test_multiple_dashes(self):
        """Préfixe retiré, reste conservé."""
        assert _instance_to_machine_name("pro-web-server", "pro") == "web-server"


class TestInstanceTypeToAnklume:
    """Tests pour _instance_type_to_anklume."""

    def test_container(self):
        assert _instance_type_to_anklume("container") == "lxc"

    def test_vm(self):
        assert _instance_type_to_anklume("virtual-machine") == "vm"

    def test_unknown(self):
        assert _instance_type_to_anklume("other") == "lxc"


class TestGenerateDomainFiles:
    """Tests pour generate_domain_files."""

    def test_generate_basic(self, tmp_path):
        """Génération d'un fichier domaine."""
        domains = [
            ScannedDomain(
                project="pro",
                network="net-pro",
                subnet="10.100.0.1/24",
                instances=[
                    ScannedInstance(
                        name="pro-dev",
                        status="Running",
                        instance_type="container",
                        project="pro",
                    ),
                ],
            )
        ]

        files = generate_domain_files(domains, tmp_path)

        assert len(files) == 1
        assert "pro.yml" in files[0]

        content = yaml.safe_load(Path(files[0]).read_text())
        assert content["description"] == "Domaine importé depuis le projet pro"
        assert content["trust_level"] == "semi-trusted"
        assert content["enabled"] is True
        assert "dev" in content["machines"]
        assert content["machines"]["dev"]["type"] == "lxc"

    def test_generate_vm(self, tmp_path):
        """Les VMs sont correctement typées."""
        domains = [
            ScannedDomain(
                project="pro",
                instances=[
                    ScannedInstance(
                        name="pro-router",
                        status="Running",
                        instance_type="virtual-machine",
                        project="pro",
                    ),
                ],
            )
        ]

        files = generate_domain_files(domains, tmp_path)

        content = yaml.safe_load(Path(files[0]).read_text())
        assert content["machines"]["router"]["type"] == "vm"

    def test_generate_creates_domains_dir(self, tmp_path):
        """Le répertoire domains/ est créé si absent."""
        output = tmp_path / "new-project"

        generate_domain_files(
            [ScannedDomain(project="pro", instances=[])],
            output,
        )

        assert (output / "domains").is_dir()

    def test_generate_empty(self, tmp_path):
        """Aucun fichier si aucun domaine."""
        files = generate_domain_files([], tmp_path)
        assert files == []

    def test_generate_multiple_domains(self, tmp_path):
        """Plusieurs domaines génèrent plusieurs fichiers."""
        domains = [
            ScannedDomain(project="pro", instances=[]),
            ScannedDomain(project="perso", instances=[]),
        ]

        files = generate_domain_files(domains, tmp_path)

        assert len(files) == 2
        names = [Path(f).name for f in files]
        assert "pro.yml" in names
        assert "perso.yml" in names


class TestImportInfrastructure:
    """Tests pour import_infrastructure."""

    def test_import_full(self, tmp_path):
        """Import complet : scan + génération."""
        net_cfg = {"ipv4.address": "10.100.0.1/24"}
        driver = mock_driver(
            projects=[IncusProject(name="pro"), IncusProject(name="default")],
            networks={"pro": [IncusNetwork(name="net-pro", config=net_cfg)]},
            instances={
                "pro": [
                    IncusInstance(
                        name="pro-dev",
                        status="Running",
                        type="container",
                        project="pro",
                    ),
                ]
            },
        )

        result = import_infrastructure(driver, tmp_path)

        assert isinstance(result, ImportResult)
        assert len(result.domains) == 1
        assert len(result.files_written) == 1
        assert result.domains[0].project == "pro"

    def test_import_empty(self, tmp_path):
        """Import d'un Incus vide (seulement default)."""
        driver = mock_driver(
            projects=[IncusProject(name="default")],
        )

        result = import_infrastructure(driver, tmp_path)

        assert result.domains == []
        assert result.files_written == []
