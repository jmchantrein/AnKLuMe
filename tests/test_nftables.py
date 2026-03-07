"""Tests du générateur de règles nftables."""

from anklume.engine.addressing import assign_addresses
from anklume.engine.models import Policy
from anklume.engine.nftables import generate_ruleset

from .conftest import make_domain, make_infra, make_machine


def _effective_lines(ruleset: str, *must_contain: str) -> list[str]:
    """Extrait les lignes de règle effectives (pas commentaires) contenant les termes."""
    return [
        line for line in ruleset.splitlines()
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
        infra = make_infra(domains={
            "pro": make_domain("pro"),
            "perso": make_domain("perso"),
        })
        assign_addresses(infra)
        ruleset = generate_ruleset(infra)
        assert 'iifname "net-pro" oifname "net-pro" accept' in ruleset
        assert 'iifname "net-perso" oifname "net-perso" accept' in ruleset

    def test_no_inter_domain_without_policy(self):
        infra = make_infra(domains={
            "pro": make_domain("pro"),
            "perso": make_domain("perso"),
        })
        assign_addresses(infra)
        ruleset = generate_ruleset(infra)
        # Pas de règle cross-bridge
        assert 'net-pro" oifname "net-perso"' not in ruleset
        assert 'net-perso" oifname "net-pro"' not in ruleset

    def test_disabled_domain_excluded(self):
        infra = make_infra(domains={
            "pro": make_domain("pro"),
            "test": make_domain("test", enabled=False),
        })
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
        infra = make_infra(domains={
            "pro": make_domain("pro"),
            "ai-tools": make_domain("ai-tools"),
        })
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
            'iifname "net-pro" oifname "net-ai-tools" '
            "tcp dport { 3000, 11434 } accept"
        ) in ruleset

    def test_udp_protocol(self):
        infra = make_infra(domains={
            "pro": make_domain("pro"),
            "dns": make_domain("dns"),
        })
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
        infra = make_infra(domains={
            "pro": make_domain("pro"),
            "perso": make_domain("perso"),
        })
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
        # Règle sans restriction de port
        rule_lines = _effective_lines(ruleset, "net-pro", "net-perso")
        assert len(rule_lines) == 1
        assert "dport" not in rule_lines[0]

    def test_ports_empty_list(self):
        """Liste de ports vide = pas de restriction de port."""
        infra = make_infra(domains={
            "pro": make_domain("pro"),
            "perso": make_domain("perso"),
        })
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
        infra = make_infra(domains={
            "pro": make_domain("pro"),
            "perso": make_domain("perso"),
        })
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
        infra = make_infra(domains={
            "pro": make_domain("pro"),
            "perso": make_domain("perso"),
            "ai-tools": make_domain("ai-tools"),
        })
        infra.policies = [
            Policy(description="P1", from_target="pro", to_target="ai-tools", ports=[11434]),
            Policy(description="P2", from_target="perso", to_target="ai-tools", ports=[3000]),
        ]
        assign_addresses(infra)
        ruleset = generate_ruleset(infra)
        assert 'iifname "net-pro" oifname "net-ai-tools"' in ruleset
        assert 'iifname "net-perso" oifname "net-ai-tools"' in ruleset

    def test_description_as_comment(self):
        infra = make_infra(domains={
            "pro": make_domain("pro"),
            "perso": make_domain("perso"),
        })
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
                from_target="host", to_target="pro", ports=[22],
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
                from_target="pro", to_target="host", ports=[53],
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
                from_target="host", to_target="pro", ports=[22],
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
        infra = make_infra(domains={
            "pro": make_domain("pro"),
            "test": make_domain("test", enabled=False),
        })
        infra.policies = [
            Policy(description="Test → Pro", from_target="test", to_target="pro", ports=[80]),
        ]
        assign_addresses(infra)
        ruleset = generate_ruleset(infra)
        assert "ignoré" in ruleset
        assert "désactivé" in ruleset

    def test_to_disabled_domain(self):
        infra = make_infra(domains={
            "pro": make_domain("pro"),
            "test": make_domain("test", enabled=False),
        })
        infra.policies = [
            Policy(description="Pro → Test", from_target="pro", to_target="test", ports=[80]),
        ]
        assign_addresses(infra)
        ruleset = generate_ruleset(infra)
        assert "ignoré" in ruleset

    def test_no_forward_rule_for_disabled(self):
        infra = make_infra(domains={
            "pro": make_domain("pro"),
            "test": make_domain("test", enabled=False),
        })
        infra.policies = [
            Policy(
                description="Pro → Test",
                from_target="pro", to_target="test", ports=[80],
            ),
        ]
        assign_addresses(infra)
        ruleset = generate_ruleset(infra)
        assert _effective_lines(ruleset, "net-test") == []


class TestSortedPorts:
    """Les ports sont triés dans les règles."""

    def test_ports_sorted(self):
        infra = make_infra(domains={
            "pro": make_domain("pro"),
            "perso": make_domain("perso"),
        })
        infra.policies = [
            Policy(
                description="Multi",
                from_target="pro", to_target="perso",
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
                from_target="inexistant", to_target="pro", ports=[80],
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
                from_target="pro", to_target="inexistant", ports=[80],
            ),
        ]
        assign_addresses(infra)
        ruleset = generate_ruleset(infra)
        assert "non résolue" in ruleset
        assert _effective_lines(ruleset, "inexistant") == []
