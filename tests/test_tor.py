"""Tests pour engine/tor.py — passerelle Tor transparente."""

from __future__ import annotations

import yaml

from anklume.engine.tor import (
    TOR_ROLE,
    TorGateway,
    find_tor_gateways,
    validate_tor_config,
)
from anklume.provisioner import BUILTIN_ROLES_DIR
from tests.conftest import make_domain, make_infra, make_machine


class TestFindTorGateways:
    """Tests pour find_tor_gateways."""

    def test_find_single_gateway(self):
        """Détecte une passerelle Tor."""
        domain = make_domain(
            "anon",
            machines={
                "browser": make_machine("browser", "anon"),
                "tor-gw": make_machine("tor-gw", "anon", type="vm", roles=["base", "tor_gateway"]),
            },
        )
        infra = make_infra(domains={"anon": domain})

        result = find_tor_gateways(infra)

        assert len(result) == 1
        assert isinstance(result[0], TorGateway)
        assert result[0].instance == "anon-tor-gw"
        assert result[0].domain == "anon"

    def test_find_no_gateway(self):
        """Aucune passerelle si pas de rôle tor_gateway."""
        domain = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro", roles=["base"])},
        )
        infra = make_infra(domains={"pro": domain})

        result = find_tor_gateways(infra)

        assert result == []

    def test_find_multiple_domains(self):
        """Détecte les passerelles dans plusieurs domaines."""
        d1 = make_domain(
            "anon",
            machines={
                "tor-gw": make_machine("tor-gw", "anon", roles=["tor_gateway"]),
            },
        )
        d2 = make_domain(
            "vpn",
            machines={
                "vpn-gw": make_machine("vpn-gw", "vpn", roles=["tor_gateway"]),
            },
        )
        infra = make_infra(domains={"anon": d1, "vpn": d2})

        result = find_tor_gateways(infra)

        assert len(result) == 2

    def test_find_disabled_domain_ignored(self):
        """Les domaines désactivés sont ignorés."""
        domain = make_domain(
            "anon",
            enabled=False,
            machines={
                "tor-gw": make_machine("tor-gw", "anon", roles=["tor_gateway"]),
            },
        )
        infra = make_infra(domains={"anon": domain})

        result = find_tor_gateways(infra)

        assert result == []

    def test_gateway_default_ports(self):
        """Ports par défaut."""
        domain = make_domain(
            "anon",
            machines={
                "tor-gw": make_machine("tor-gw", "anon", roles=["tor_gateway"]),
            },
        )
        infra = make_infra(domains={"anon": domain})

        result = find_tor_gateways(infra)

        assert result[0].trans_port == 9040
        assert result[0].dns_port == 5353
        assert result[0].socks_port == 9050

    def test_gateway_custom_ports(self):
        """Ports personnalisés via vars."""
        domain = make_domain(
            "anon",
            machines={
                "tor-gw": make_machine(
                    "tor-gw",
                    "anon",
                    roles=["tor_gateway"],
                    vars={
                        "tor_trans_port": 9041,
                        "tor_dns_port": 5354,
                        "tor_socks_port": 9051,
                    },
                ),
            },
        )
        infra = make_infra(domains={"anon": domain})

        result = find_tor_gateways(infra)

        assert result[0].trans_port == 9041
        assert result[0].dns_port == 5354
        assert result[0].socks_port == 9051


class TestValidateTorConfig:
    """Tests pour validate_tor_config."""

    def test_valid_config(self):
        """Config valide : aucune erreur."""
        domain = make_domain(
            "anon",
            machines={
                "tor-gw": make_machine("tor-gw", "anon", type="vm", roles=["tor_gateway"]),
            },
        )
        infra = make_infra(domains={"anon": domain})

        errors = validate_tor_config(infra)

        assert errors == []

    def test_multiple_gateways_same_domain(self):
        """Erreur si plusieurs passerelles dans un domaine."""
        domain = make_domain(
            "anon",
            machines={
                "tor-gw1": make_machine("tor-gw1", "anon", roles=["tor_gateway"]),
                "tor-gw2": make_machine("tor-gw2", "anon", roles=["tor_gateway"]),
            },
        )
        infra = make_infra(domains={"anon": domain})

        errors = validate_tor_config(infra)

        assert len(errors) >= 1
        assert "anon" in errors[0]

    def test_lxc_gateway_warning(self):
        """Warning si la passerelle est LXC au lieu de VM."""
        domain = make_domain(
            "anon",
            machines={
                "tor-gw": make_machine("tor-gw", "anon", type="lxc", roles=["tor_gateway"]),
            },
        )
        infra = make_infra(domains={"anon": domain})

        errors = validate_tor_config(infra)

        assert len(errors) == 1
        assert "vm" in errors[0].lower() or "VM" in errors[0]

    def test_no_gateways_valid(self):
        """Pas de passerelle : valide."""
        domain = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro")},
        )
        infra = make_infra(domains={"pro": domain})

        errors = validate_tor_config(infra)

        assert errors == []


class TestTorRole:
    """Tests pour le rôle Ansible tor_gateway."""

    def test_role_directory_exists(self):
        """Le répertoire du rôle existe."""
        assert (BUILTIN_ROLES_DIR / "tor_gateway").is_dir()

    def test_tasks_file_exists(self):
        """Le fichier tasks/main.yml existe."""
        assert (BUILTIN_ROLES_DIR / "tor_gateway" / "tasks" / "main.yml").is_file()

    def test_defaults_file_exists(self):
        """Le fichier defaults/main.yml existe."""
        assert (BUILTIN_ROLES_DIR / "tor_gateway" / "defaults" / "main.yml").is_file()

    def test_defaults_ports(self):
        """Les ports par défaut sont corrects."""
        defaults = yaml.safe_load(
            (BUILTIN_ROLES_DIR / "tor_gateway" / "defaults" / "main.yml").read_text()
        )
        assert defaults["tor_trans_port"] == 9040
        assert defaults["tor_dns_port"] == 5353
        assert defaults["tor_socks_port"] == 9050

    def test_torrc_template_exists(self):
        """Le template torrc.j2 existe."""
        assert (BUILTIN_ROLES_DIR / "tor_gateway" / "templates" / "torrc.j2").is_file()

    def test_nftables_template_exists(self):
        """Le template nftables-tor.conf.j2 existe."""
        assert (BUILTIN_ROLES_DIR / "tor_gateway" / "templates" / "nftables-tor.conf.j2").is_file()

    def test_tasks_content(self):
        """Les tâches principales sont présentes."""
        tasks = yaml.safe_load(
            (BUILTIN_ROLES_DIR / "tor_gateway" / "tasks" / "main.yml").read_text()
        )
        names = [t.get("name", "") for t in tasks]
        assert any("tor" in n.lower() for n in names), f"Tâche tor manquante dans {names}"

    def test_tor_role_constant(self):
        """La constante TOR_ROLE vaut 'tor_gateway'."""
        assert TOR_ROLE == "tor_gateway"
