"""Tests du générateur de règles nftables."""

import pytest

from anklume.engine.addressing import assign_addresses
from anklume.engine.models import Policy
from anklume.engine.nftables import generate_ruleset

from .conftest import make_domain, make_infra, make_machine


def _effective_lines(ruleset: str, *must_contain: str) -> list[str]:
    """Extrait les lignes de règle effectives (pas commentaires) contenant les termes."""
    return [
        line
        for line in ruleset.splitlines()
        if all(term in line for term in must_contain)
        and "accept" in line
        and not line.strip().startswith("#")
    ]


class TestRulesetStructure:
    """Structure de base du ruleset."""

    def test_table_inet_anklume(self):
        infra = make_infra()
        ruleset = generate_ruleset(infra)
        assert "table inet anklume" in ruleset

    def test_chain_forward_drop(self):
        infra = make_infra()
        ruleset = generate_ruleset(infra)
        assert "chain forward" in ruleset
        assert "policy drop" in ruleset

    def test_established_related(self):
        infra = make_infra()
        ruleset = generate_ruleset(infra)
        assert "ct state established,related accept" in ruleset

    def test_flush_table_idempotent(self):
        infra = make_infra()
        ruleset = generate_ruleset(infra)
        assert "flush table inet anklume" in ruleset

    def test_shebang(self):
        infra = make_infra()
        ruleset = generate_ruleset(infra)
        assert ruleset.startswith("#!/usr/sbin/nft -f")

    def test_header_comment(self):
        infra = make_infra()
        ruleset = generate_ruleset(infra)
        assert "Généré par anklume" in ruleset


class TestIntraDomain:
    """Règles de trafic intra-domaine."""

    def test_single_domain(self):
        infra = make_infra(domains={"pro": make_domain("pro")})
        assign_addresses(infra)
        ruleset = generate_ruleset(infra)
        assert 'iifname "net-pro" oifname "net-pro" accept' in ruleset

    def test_two_domains(self):
        infra = make_infra(
            domains={
                "pro": make_domain("pro"),
                "perso": make_domain("perso"),
            }
        )
        assign_addresses(infra)
        ruleset = generate_ruleset(infra)
        assert 'iifname "net-pro" oifname "net-pro" accept' in ruleset
        assert 'iifname "net-perso" oifname "net-perso" accept' in ruleset

    def test_no_inter_domain_without_policy(self):
        infra = make_infra(
            domains={
                "pro": make_domain("pro"),
                "perso": make_domain("perso"),
            }
        )
        assign_addresses(infra)
        ruleset = generate_ruleset(infra)
        # Pas de règle cross-bridge
        assert 'net-pro" oifname "net-perso"' not in ruleset
        assert 'net-perso" oifname "net-pro"' not in ruleset

    def test_disabled_domain_excluded(self):
        infra = make_infra(
            domains={
                "pro": make_domain("pro"),
                "test": make_domain("test", enabled=False),
            }
        )
        assign_addresses(infra)
        ruleset = generate_ruleset(infra)
        assert "net-pro" in ruleset
        assert "net-test" not in ruleset

    def test_empty_infra(self):
        infra = make_infra()
        ruleset = generate_ruleset(infra)
        assert "intra-domaine" not in ruleset


class TestDomainToDomainPolicy:
    """Politiques entre domaines."""

    def test_basic(self):
        infra = make_infra(
            domains={
                "pro": make_domain("pro"),
                "ai-tools": make_domain("ai-tools"),
            }
        )
        infra.policies = [
            Policy(
                description="Pro accède à Ollama",
                from_target="pro",
                to_target="ai-tools",
                ports=[11434, 3000],
            )
        ]
        assign_addresses(infra)
        ruleset = generate_ruleset(infra)
        assert (
            'iifname "net-pro" oifname "net-ai-tools" tcp dport { 3000, 11434 } accept'
        ) in ruleset

    def test_udp_protocol(self):
        infra = make_infra(
            domains={
                "pro": make_domain("pro"),
                "dns": make_domain("dns"),
            }
        )
        infra.policies = [
            Policy(
                description="DNS",
                from_target="pro",
                to_target="dns",
                ports=[53],
                protocol="udp",
            )
        ]
        assign_addresses(infra)
        ruleset = generate_ruleset(infra)
        assert "udp dport { 53 }" in ruleset

    def test_ports_all(self):
        infra = make_infra(
            domains={
                "pro": make_domain("pro"),
                "perso": make_domain("perso"),
            }
        )
        infra.policies = [
            Policy(
                description="Tout",
                from_target="pro",
                to_target="perso",
                ports="all",
            )
        ]
        assign_addresses(infra)
        ruleset = generate_ruleset(infra)
        rule_lines = _effective_lines(ruleset, "net-pro", "net-perso")
        assert len(rule_lines) == 1
        assert "dport" not in rule_lines[0]
        # ports="all" avec protocole par défaut → filtre protocole
        assert "meta l4proto tcp" in rule_lines[0]

    def test_ports_all_with_udp(self):
        """ports='all' avec protocol='udp' → meta l4proto udp."""
        infra = make_infra(
            domains={
                "pro": make_domain("pro"),
                "perso": make_domain("perso"),
            }
        )
        infra.policies = [
            Policy(
                description="Tout UDP",
                from_target="pro",
                to_target="perso",
                ports="all",
                protocol="udp",
            )
        ]
        assign_addresses(infra)
        ruleset = generate_ruleset(infra)
        rule_lines = _effective_lines(ruleset, "net-pro", "net-perso")
        assert len(rule_lines) == 1
        assert "meta l4proto udp" in rule_lines[0]
        assert "dport" not in rule_lines[0]

    def test_ports_empty_list(self):
        """Liste de ports vide = pas de restriction de port."""
        infra = make_infra(
            domains={
                "pro": make_domain("pro"),
                "perso": make_domain("perso"),
            }
        )
        infra.policies = [
            Policy(
                description="Tout",
                from_target="pro",
                to_target="perso",
                ports=[],
            )
        ]
        assign_addresses(infra)
        ruleset = generate_ruleset(infra)
        rule_lines = _effective_lines(ruleset, "net-pro", "net-perso")
        assert len(rule_lines) == 1
        assert "dport" not in rule_lines[0]

    def test_bidirectional(self):
        infra = make_infra(
            domains={
                "pro": make_domain("pro"),
                "perso": make_domain("perso"),
            }
        )
        infra.policies = [
            Policy(
                description="Bidirectionnel",
                from_target="pro",
                to_target="perso",
                ports=[8080],
                bidirectional=True,
            )
        ]
        assign_addresses(infra)
        ruleset = generate_ruleset(infra)
        assert 'iifname "net-pro" oifname "net-perso" tcp dport { 8080 } accept' in ruleset
        assert 'iifname "net-perso" oifname "net-pro" tcp dport { 8080 } accept' in ruleset

    def test_multiple_policies(self):
        infra = make_infra(
            domains={
                "pro": make_domain("pro"),
                "perso": make_domain("perso"),
                "ai-tools": make_domain("ai-tools"),
            }
        )
        infra.policies = [
            Policy(description="P1", from_target="pro", to_target="ai-tools", ports=[11434]),
            Policy(description="P2", from_target="perso", to_target="ai-tools", ports=[3000]),
        ]
        assign_addresses(infra)
        ruleset = generate_ruleset(infra)
        assert 'iifname "net-pro" oifname "net-ai-tools"' in ruleset
        assert 'iifname "net-perso" oifname "net-ai-tools"' in ruleset

    def test_description_as_comment(self):
        infra = make_infra(
            domains={
                "pro": make_domain("pro"),
                "perso": make_domain("perso"),
            }
        )
        infra.policies = [
            Policy(description="Accès VPN", from_target="pro", to_target="perso", ports=[1194]),
        ]
        assign_addresses(infra)
        ruleset = generate_ruleset(infra)
        assert "# Accès VPN" in ruleset


class TestMachineTargetPolicy:
    """Politiques ciblant des machines spécifiques."""

    def _infra_with_machines(self):
        dev = make_machine("dev", "pro", ip="10.120.0.1")
        gpu = make_machine("gpu", "ai-tools", ip="10.100.0.1")
        pro = make_domain("pro", machines={"dev": dev})
        ai = make_domain("ai-tools", machines={"gpu": gpu})
        return make_infra(domains={"pro": pro, "ai-tools": ai})

    def test_machine_to_machine(self):
        infra = self._infra_with_machines()
        infra.policies = [
            Policy(
                description="Dev → GPU",
                from_target="pro-dev",
                to_target="ai-tools-gpu",
                ports=[11434],
            )
        ]
        assign_addresses(infra)
        ruleset = generate_ruleset(infra)
        assert "ip saddr 10.120.0.1" in ruleset
        assert "ip daddr 10.100.0.1" in ruleset
        assert "tcp dport { 11434 }" in ruleset

    def test_domain_to_machine(self):
        infra = self._infra_with_machines()
        infra.policies = [
            Policy(
                description="Pro → GPU",
                from_target="pro",
                to_target="ai-tools-gpu",
                ports=[11434],
            )
        ]
        assign_addresses(infra)
        ruleset = generate_ruleset(infra)
        rule_lines = _effective_lines(ruleset, "net-pro", "net-ai-tools")
        assert len(rule_lines) == 1
        assert "ip daddr 10.100.0.1" in rule_lines[0]
        assert "ip saddr" not in rule_lines[0]

    def test_machine_to_domain(self):
        infra = self._infra_with_machines()
        infra.policies = [
            Policy(
                description="Dev → AI",
                from_target="pro-dev",
                to_target="ai-tools",
                ports=[11434],
            )
        ]
        assign_addresses(infra)
        ruleset = generate_ruleset(infra)
        rule_lines = _effective_lines(ruleset, "net-pro", "net-ai-tools")
        assert len(rule_lines) == 1
        assert "ip saddr 10.120.0.1" in rule_lines[0]
        assert "ip daddr" not in rule_lines[0]


class TestHostPolicy:
    """Politiques impliquant l'hôte."""

    def test_from_host_is_comment(self):
        infra = make_infra(domains={"pro": make_domain("pro")})
        infra.policies = [
            Policy(
                description="Host accède à Pro",
                from_target="host",
                to_target="pro",
                ports=[22],
            ),
        ]
        assign_addresses(infra)
        ruleset = generate_ruleset(infra)
        assert "Host accède à Pro" in ruleset
        assert "hôte" in ruleset

    def test_to_host_is_comment(self):
        infra = make_infra(domains={"pro": make_domain("pro")})
        infra.policies = [
            Policy(
                description="Pro accède à Host",
                from_target="pro",
                to_target="host",
                ports=[53],
            ),
        ]
        assign_addresses(infra)
        ruleset = generate_ruleset(infra)
        assert "Pro accède à Host" in ruleset
        assert "non appliquée" in ruleset

    def test_host_policy_no_forward_rule(self):
        """Les politiques hôte ne génèrent pas de règle forward effective."""
        infra = make_infra(domains={"pro": make_domain("pro")})
        infra.policies = [
            Policy(
                description="Host → Pro",
                from_target="host",
                to_target="pro",
                ports=[22],
            ),
        ]
        assign_addresses(infra)
        ruleset = generate_ruleset(infra)
        # Seule la règle intra-domaine contient net-pro + accept
        effective = _effective_lines(ruleset, "net-pro")
        for line in effective:
            assert 'iifname "net-pro" oifname "net-pro"' in line


class TestDisabledDomainPolicy:
    """Politiques référençant des domaines désactivés."""

    def test_from_disabled_domain(self):
        infra = make_infra(
            domains={
                "pro": make_domain("pro"),
                "test": make_domain("test", enabled=False),
            }
        )
        infra.policies = [
            Policy(description="Test → Pro", from_target="test", to_target="pro", ports=[80]),
        ]
        assign_addresses(infra)
        ruleset = generate_ruleset(infra)
        assert "ignoré" in ruleset
        assert "désactivé" in ruleset

    def test_to_disabled_domain(self):
        infra = make_infra(
            domains={
                "pro": make_domain("pro"),
                "test": make_domain("test", enabled=False),
            }
        )
        infra.policies = [
            Policy(description="Pro → Test", from_target="pro", to_target="test", ports=[80]),
        ]
        assign_addresses(infra)
        ruleset = generate_ruleset(infra)
        assert "ignoré" in ruleset

    def test_no_forward_rule_for_disabled(self):
        infra = make_infra(
            domains={
                "pro": make_domain("pro"),
                "test": make_domain("test", enabled=False),
            }
        )
        infra.policies = [
            Policy(
                description="Pro → Test",
                from_target="pro",
                to_target="test",
                ports=[80],
            ),
        ]
        assign_addresses(infra)
        ruleset = generate_ruleset(infra)
        assert _effective_lines(ruleset, "net-test") == []


class TestSortedPorts:
    """Les ports sont triés dans les règles."""

    def test_ports_sorted(self):
        infra = make_infra(
            domains={
                "pro": make_domain("pro"),
                "perso": make_domain("perso"),
            }
        )
        infra.policies = [
            Policy(
                description="Multi",
                from_target="pro",
                to_target="perso",
                ports=[8080, 443, 80],
            ),
        ]
        assign_addresses(infra)
        ruleset = generate_ruleset(infra)
        assert "tcp dport { 80, 443, 8080 }" in ruleset


class TestUnresolvedTarget:
    """Cible non résolue dans une politique."""

    def test_unknown_from_target(self):
        """Cible source inconnue → commentaire d'erreur, pas de règle accept."""
        infra = make_infra(domains={"pro": make_domain("pro")})
        infra.policies = [
            Policy(
                description="Typo",
                from_target="inexistant",
                to_target="pro",
                ports=[80],
            ),
        ]
        assign_addresses(infra)
        ruleset = generate_ruleset(infra)
        assert "non résolue" in ruleset
        assert _effective_lines(ruleset, "inexistant") == []

    def test_unknown_to_target(self):
        """Cible destination inconnue → commentaire d'erreur, pas de règle accept."""
        infra = make_infra(domains={"pro": make_domain("pro")})
        infra.policies = [
            Policy(
                description="Typo",
                from_target="pro",
                to_target="inexistant",
                ports=[80],
            ),
        ]
        assign_addresses(infra)
        ruleset = generate_ruleset(infra)
        assert "non résolue" in ruleset
        assert _effective_lines(ruleset, "inexistant") == []


class TestNetworkPassthrough:
    """Passthrough pour les bridges non-anklume (ADR-027)."""

    def test_passthrough_disabled_by_default(self):
        infra = make_infra(domains={"pro": make_domain("pro")})
        assign_addresses(infra)
        ruleset = generate_ruleset(infra)
        assert 'iifname != "net-*"' not in ruleset

    def test_passthrough_enabled(self):
        infra = make_infra(domains={"pro": make_domain("pro")})
        infra.config.network_passthrough = True
        assign_addresses(infra)
        ruleset = generate_ruleset(infra)
        assert 'iifname != "net-*" oifname != "net-*" accept' in ruleset

    def test_passthrough_before_intra_domain(self):
        """Le passthrough est avant les règles intra-domaine."""
        infra = make_infra(domains={"pro": make_domain("pro")})
        infra.config.network_passthrough = True
        assign_addresses(infra)
        ruleset = generate_ruleset(infra)
        lines = ruleset.splitlines()
        passthrough_idx = next(i for i, line in enumerate(lines) if 'iifname != "net-*"' in line)
        intra_idx = next(i for i, line in enumerate(lines) if "intra-domaine" in line)
        assert passthrough_idx < intra_idx

    def test_passthrough_does_not_affect_anklume_rules(self):
        """Les règles anklume (intra + policies) sont toujours présentes."""
        infra = make_infra(
            domains={
                "pro": make_domain("pro"),
                "perso": make_domain("perso"),
            }
        )
        infra.config.network_passthrough = True
        infra.policies = [
            Policy(
                description="Pro → Perso SSH",
                from_target="pro",
                to_target="perso",
                ports=[22],
            ),
        ]
        assign_addresses(infra)
        ruleset = generate_ruleset(infra)
        assert 'iifname != "net-*"' in ruleset
        assert 'iifname "net-pro" oifname "net-pro" accept' in ruleset
        assert "tcp dport { 22 }" in ruleset
        assert "policy drop" in ruleset


class TestTorTransparentRouting:
    """Règles DNAT prerouting pour le routage transparent Tor."""

    def _make_tor_infra(self):
        """Infra avec un domaine sandbox contenant un tor_gateway."""
        gw = make_machine("tor-gw", "sandbox", roles=["tor_gateway"])
        gw.vars = {"tor_trans_port": 9040, "tor_dns_port": 5353}
        gw.type = "vm"
        browser = make_machine("browse", "sandbox")
        infra = make_infra(
            domains={
                "sandbox": make_domain(
                    "sandbox",
                    machines={"tor-gw": gw, "browse": browser},
                )
            }
        )
        assign_addresses(infra)
        return infra

    def test_tor_generates_prerouting_chain(self):
        infra = self._make_tor_infra()
        ruleset = generate_ruleset(infra)
        assert "chain prerouting" in ruleset
        assert "priority dstnat" in ruleset

    def test_tor_dnat_tcp_rule(self):
        infra = self._make_tor_infra()
        ruleset = generate_ruleset(infra)
        assert "tcp dport 1-65535 dnat to" in ruleset

    def test_tor_dnat_dns_rule(self):
        infra = self._make_tor_infra()
        ruleset = generate_ruleset(infra)
        assert "udp dport 53 dnat to" in ruleset

    def test_tor_excludes_gateway_ip(self):
        """La gateway elle-même est exclue des règles DNAT."""
        infra = self._make_tor_infra()
        ruleset = generate_ruleset(infra)
        # Trouver l'IP du gateway
        gw = infra.domains["sandbox"].machines["tor-gw"]
        assert f"ip saddr != {gw.ip}" in ruleset

    def test_no_tor_no_prerouting(self):
        """Sans tor_gateway, pas de chain prerouting."""
        infra = make_infra(domains={"pro": make_domain("pro")})
        assign_addresses(infra)
        ruleset = generate_ruleset(infra)
        assert "chain prerouting" not in ruleset

    def test_tor_custom_ports(self):
        """Les ports custom sont utilisés dans les règles DNAT."""
        gw = make_machine("tor-gw", "sandbox", roles=["tor_gateway"])
        gw.vars = {"tor_trans_port": 9999, "tor_dns_port": 5454}
        gw.type = "vm"
        infra = make_infra(
            domains={
                "sandbox": make_domain("sandbox", machines={"tor-gw": gw})
            }
        )
        assign_addresses(infra)
        ruleset = generate_ruleset(infra)
        assert "dnat to" in ruleset
        assert ":9999" in ruleset
        assert ":5454" in ruleset

    def test_tor_disabled_domain_ignored(self):
        """Domaine désactivé avec tor_gateway → pas de règles."""
        gw = make_machine("tor-gw", "sandbox", roles=["tor_gateway"])
        gw.vars = {"tor_trans_port": 9040, "tor_dns_port": 5353}
        infra = make_infra(
            domains={
                "sandbox": make_domain("sandbox", machines={"tor-gw": gw}, enabled=False)
            }
        )
        assign_addresses(infra)
        ruleset = generate_ruleset(infra)
        assert "chain prerouting" not in ruleset


class TestEdgeCharacterNames:
    """Noms de domaine/machine avec tirets et chiffres dans les règles nftables."""

    @pytest.mark.parametrize(
        "domain_name",
        ["ai-tools", "lab-42", "a", "x1", "my-long-name"],
        ids=["hyphenated", "hyphen-number", "single-char", "letter-number", "multi-hyphen"],
    )
    def test_domain_name_in_intra_rule(self, domain_name):
        """Les noms de domaine avec tirets/chiffres produisent des règles intra-domaine."""
        infra = make_infra(domains={domain_name: make_domain(domain_name)})
        assign_addresses(infra)
        ruleset = generate_ruleset(infra)
        expected = f'iifname "net-{domain_name}" oifname "net-{domain_name}" accept'
        assert expected in ruleset

    def test_policy_with_hyphenated_names(self):
        """Politique entre domaines aux noms avec tirets et chiffres."""
        infra = make_infra(
            domains={
                "ai-tools": make_domain("ai-tools"),
                "lab-42": make_domain("lab-42"),
            }
        )
        infra.policies = [
            Policy(
                description="AI vers Lab",
                from_target="ai-tools",
                to_target="lab-42",
                ports=[8080],
            )
        ]
        assign_addresses(infra)
        ruleset = generate_ruleset(infra)
        assert 'iifname "net-ai-tools" oifname "net-lab-42" tcp dport { 8080 } accept' in ruleset

    def test_machine_target_with_hyphens(self):
        """Machine cible avec tirets dans le nom génère la bonne règle IP."""
        dev = make_machine("gpu-node", "ai-tools", ip="10.120.0.5")
        web = make_machine("front-end", "lab-42", ip="10.100.0.3")
        infra = make_infra(
            domains={
                "ai-tools": make_domain("ai-tools", machines={"gpu-node": dev}),
                "lab-42": make_domain("lab-42", machines={"front-end": web}),
            }
        )
        infra.policies = [
            Policy(
                description="GPU vers Frontend",
                from_target="ai-tools-gpu-node",
                to_target="lab-42-front-end",
                ports=[443],
            )
        ]
        assign_addresses(infra)
        ruleset = generate_ruleset(infra)
        assert "ip saddr 10.120.0.5" in ruleset
        assert "ip daddr 10.100.0.3" in ruleset
        assert "tcp dport { 443 }" in ruleset
