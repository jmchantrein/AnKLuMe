"""Tests pour engine/import_infra.py — import d'infrastructure existante."""

from __future__ import annotations

from pathlib import Path

import yaml

from anklume.engine.import_infra import (
    IMPORT_LIMITATIONS,
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


def _inst(
    name: str,
    project: str,
    *,
    net: str = "net-pro",
    status: str = "Running",
    type: str = "container",
    profiles: list[str] | None = None,
) -> IncusInstance:
    """Helper pour créer une IncusInstance avec devices.eth0.network."""
    return IncusInstance(
        name=name,
        status=status,
        type=type,
        project=project,
        profiles=profiles or ["default"],
        devices={"eth0": {"network": net, "type": "nic"}} if net else {},
    )


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
                    _inst("pro-dev", "pro"),
                    _inst("pro-mail", "pro", status="Stopped"),
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
                "pro": [_inst("pro-dev", "pro")],
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
            instances={"pro": [_inst("pro-dev", "pro", net="lxdbr0")]},
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
                    _inst("pro-router", "pro", type="virtual-machine"),
                ]
            },
        )

        domains = scan_incus(driver)

        assert domains[0].instances[0].instance_type == "virtual-machine"

    def test_scan_detects_gpu(self):
        """Détection GPU depuis le profile gpu-passthrough."""
        driver = mock_driver(
            projects=[IncusProject(name="ai")],
            instances={
                "ai": [
                    _inst("ai-gpu", "ai", net="net-ai", profiles=["default", "gpu-passthrough"]),
                    _inst("ai-web", "ai", net="net-ai"),
                ]
            },
        )

        domains = scan_incus(driver)

        gpu_inst = next(i for i in domains[0].instances if i.name == "ai-gpu")
        web_inst = next(i for i in domains[0].instances if i.name == "ai-web")
        assert gpu_inst.gpu is True
        assert web_inst.gpu is False

    def test_scan_detects_gui(self):
        """Détection GUI depuis le profile gui."""
        driver = mock_driver(
            projects=[IncusProject(name="perso")],
            instances={
                "perso": [
                    _inst("perso-desktop", "perso", net="net-perso", profiles=["default", "gui"]),
                    _inst("perso-server", "perso", net="net-perso"),
                ]
            },
        )

        domains = scan_incus(driver)

        desktop = next(i for i in domains[0].instances if i.name == "perso-desktop")
        server = next(i for i in domains[0].instances if i.name == "perso-server")
        assert desktop.gui is True
        assert server.gui is False

    def test_scan_network_from_instance_devices(self):
        """Le réseau est lu depuis devices.eth0.network, pas le project-level scan."""
        driver = mock_driver(
            projects=[IncusProject(name="pro"), IncusProject(name="perso")],
            networks={
                "pro": [
                    IncusNetwork(name="net-ai", config={"ipv4.address": "10.110.0.254/24"}),
                    IncusNetwork(name="net-pro", config={"ipv4.address": "10.120.1.254/24"}),
                ],
                "perso": [
                    IncusNetwork(name="net-ai", config={"ipv4.address": "10.110.0.254/24"}),
                    IncusNetwork(name="net-perso", config={"ipv4.address": "10.120.0.254/24"}),
                ],
            },
            instances={
                "pro": [_inst("pro-dev", "pro", net="net-pro")],
                "perso": [_inst("perso-desktop", "perso", net="net-perso")],
            },
        )

        domains = scan_incus(driver)

        pro = next(d for d in domains if d.project == "pro")
        perso = next(d for d in domains if d.project == "perso")
        assert pro.network == "net-pro"
        assert pro.subnet == "10.120.1.254/24"
        assert perso.network == "net-perso"
        assert perso.subnet == "10.120.0.254/24"


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

    def test_generate_gpu_gui(self, tmp_path):
        """GPU et GUI sont inclus dans le YAML quand détectés."""
        domains = [
            ScannedDomain(
                project="ai",
                instances=[
                    ScannedInstance(
                        name="ai-gpu",
                        status="Running",
                        instance_type="container",
                        project="ai",
                        gpu=True,
                    ),
                    ScannedInstance(
                        name="ai-desktop",
                        status="Running",
                        instance_type="container",
                        project="ai",
                        gui=True,
                    ),
                    ScannedInstance(
                        name="ai-plain",
                        status="Running",
                        instance_type="container",
                        project="ai",
                    ),
                ],
            )
        ]

        files = generate_domain_files(domains, tmp_path)

        content = yaml.safe_load(Path(files[0]).read_text())
        assert content["machines"]["gpu"]["gpu"] is True
        assert "gui" not in content["machines"]["gpu"]
        assert content["machines"]["desktop"]["gui"] is True
        assert "gpu" not in content["machines"]["desktop"]
        assert "gpu" not in content["machines"]["plain"]
        assert "gui" not in content["machines"]["plain"]

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
                "pro": [_inst("pro-dev", "pro")]
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


class TestImportLimitations:
    """Les limitations sont documentées et exportées."""

    def test_limitations_list_exists(self):
        assert isinstance(IMPORT_LIMITATIONS, list)
        assert len(IMPORT_LIMITATIONS) >= 4

    def test_limitations_mention_roles(self):
        text = " ".join(IMPORT_LIMITATIONS)
        assert "Ansible" in text

    def test_limitations_mention_trust(self):
        text = " ".join(IMPORT_LIMITATIONS)
        assert "trust" in text.lower()
