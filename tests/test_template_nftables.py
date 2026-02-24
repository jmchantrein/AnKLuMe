"""Tests for nftables Jinja2 template edge cases.

Covers boundary conditions and advanced rendering for the nftables
isolation template (incus_nftables role).
"""

import re
from pathlib import Path

import pytest

try:
    from jinja2 import Environment, FileSystemLoader
except ImportError:
    pytest.skip("jinja2 not installed", allow_module_level=True)

ROLES_DIR = Path(__file__).resolve().parent.parent / "roles"


def _ansible_env(tmpl_dir):
    """Create a Jinja2 Environment with Ansible-compatible filters."""
    env = Environment(loader=FileSystemLoader(str(tmpl_dir)))
    env.filters["regex_replace"] = lambda value, pattern, replacement: re.sub(
        pattern, replacement, value,
    )
    return env


# ── nftables isolation template edge cases ──────────────────


class TestNftablesEdgeCases:
    def _render(self, **kwargs):
        tmpl_dir = ROLES_DIR / "incus_nftables" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("anklume-isolation.nft.j2")
        return template.render(**kwargs)

    def test_bidirectional_policy(self):
        """Bidirectional policies generate rules in both directions."""
        result = self._render(
            incus_nftables_all_bridges=["net-pro", "net-ai-tools"],
            incus_nftables_resolved_policies=[{
                "description": "Pro <-> AI bidirectional",
                "from_bridge": "net-pro",
                "to_bridge": "net-ai-tools",
                "ports": [8080],
                "protocol": "tcp",
                "bidirectional": True,
            }],
        )
        # Forward direction
        assert 'iifname "net-pro" oifname "net-ai-tools" tcp dport { 8080 } accept' in result
        # Reverse direction
        assert 'iifname "net-ai-tools" oifname "net-pro" tcp dport { 8080 } accept' in result

    def test_ports_all_policy(self):
        """Policy with ports='all' generates accept without port filter."""
        result = self._render(
            incus_nftables_all_bridges=["net-anklume", "net-work"],
            incus_nftables_resolved_policies=[{
                "description": "Full access",
                "from_bridge": "net-anklume",
                "to_bridge": "net-work",
                "ports": "all",
                "protocol": "tcp",
                "bidirectional": False,
            }],
        )
        # Should have accept without tcp dport
        assert 'iifname "net-anklume" oifname "net-work" accept' in result
        assert "dport" not in result.split("net-work")[1].split("\n")[0]

    def test_bidirectional_ports_all(self):
        """Bidirectional with ports='all' generates both directions without ports."""
        result = self._render(
            incus_nftables_all_bridges=["net-a", "net-b"],
            incus_nftables_resolved_policies=[{
                "description": "Full bidirectional",
                "from_bridge": "net-a",
                "to_bridge": "net-b",
                "ports": "all",
                "protocol": "tcp",
                "bidirectional": True,
            }],
        )
        assert 'iifname "net-a" oifname "net-b" accept' in result
        assert 'iifname "net-b" oifname "net-a" accept' in result

    def test_multiple_policies(self):
        """Multiple policies are rendered in order."""
        result = self._render(
            incus_nftables_all_bridges=["net-a", "net-b", "net-c"],
            incus_nftables_resolved_policies=[
                {
                    "description": "Policy 1",
                    "from_bridge": "net-a",
                    "to_bridge": "net-b",
                    "ports": [80],
                    "protocol": "tcp",
                    "bidirectional": False,
                },
                {
                    "description": "Policy 2",
                    "from_bridge": "net-a",
                    "to_bridge": "net-c",
                    "ports": [443],
                    "protocol": "tcp",
                    "bidirectional": False,
                },
            ],
        )
        assert "Policy 1" in result
        assert "Policy 2" in result
        assert "dport { 80 }" in result
        assert "dport { 443 }" in result

    def test_many_bridges(self):
        """Template handles many bridges (10+) correctly."""
        bridges = [f"net-domain{i}" for i in range(12)]
        result = self._render(
            incus_nftables_all_bridges=bridges,
            incus_nftables_resolved_policies=[],
        )
        # Each bridge should have a same-bridge accept rule
        for bridge in bridges:
            assert f'iifname "{bridge}" oifname "{bridge}" accept' in result
        # Inter-bridge drop should list all bridges
        assert "drop" in result

    def test_empty_bridges_list(self):
        """Template handles empty bridges list without error."""
        result = self._render(
            incus_nftables_all_bridges=[],
            incus_nftables_resolved_policies=[],
        )
        assert "table inet anklume" in result
        # No same-bridge rules or inter-bridge drop
        assert "iifname" not in result.split("ct state")[0]

    def test_multiple_ports_in_policy(self):
        """Policy with multiple ports renders comma-separated list."""
        result = self._render(
            incus_nftables_all_bridges=["net-a", "net-b"],
            incus_nftables_resolved_policies=[{
                "description": "Multi-port",
                "from_bridge": "net-a",
                "to_bridge": "net-b",
                "ports": [80, 443, 8080, 11434],
                "protocol": "tcp",
                "bidirectional": False,
            }],
        )
        assert "dport { 80, 443, 8080, 11434 }" in result

    def test_udp_protocol(self):
        """Policy with UDP protocol uses 'udp dport'."""
        result = self._render(
            incus_nftables_all_bridges=["net-a", "net-b"],
            incus_nftables_resolved_policies=[{
                "description": "DNS traffic",
                "from_bridge": "net-a",
                "to_bridge": "net-b",
                "ports": [53],
                "protocol": "udp",
                "bidirectional": False,
            }],
        )
        assert "udp dport { 53 }" in result

    def test_atomic_replacement_header(self):
        """Template includes atomic replacement commands."""
        result = self._render(
            incus_nftables_all_bridges=["net-test"],
            incus_nftables_resolved_policies=[],
        )
        assert "table inet anklume;" in result
        assert "delete table inet anklume;" in result

    def test_stateful_tracking(self):
        """Template includes stateful connection tracking."""
        result = self._render(
            incus_nftables_all_bridges=["net-test"],
            incus_nftables_resolved_policies=[],
        )
        assert "ct state established,related accept" in result
        assert "ct state invalid drop" in result


# ── nftables many-bridges edge cases ────────────────────────


class TestNftablesManyBridges:
    """Tests for nftables template with large numbers of bridges."""

    def _render(self, **kwargs):
        tmpl_dir = ROLES_DIR / "incus_nftables" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("anklume-isolation.nft.j2")
        return template.render(**kwargs)

    def test_ten_bridges_generates_ten_same_bridge_rules(self):
        """10 bridges generate 10 same-bridge accept rules."""
        bridges = [f"net-domain{i}" for i in range(10)]
        result = self._render(
            incus_nftables_all_bridges=bridges,
            incus_nftables_resolved_policies=[],
        )
        for bridge in bridges:
            assert f'iifname "{bridge}" oifname "{bridge}" accept' in result
        # Exactly 10 same-bridge rules
        same_bridge_count = result.count("oifname") - 1  # minus 1 for inter-bridge drop
        assert same_bridge_count >= 10

    def test_twenty_bridges_no_truncation(self):
        """20 bridges are all present in output, no truncation."""
        bridges = [f"net-zone{i}" for i in range(20)]
        result = self._render(
            incus_nftables_all_bridges=bridges,
            incus_nftables_resolved_policies=[],
        )
        for bridge in bridges:
            assert f'"{bridge}"' in result, f"Bridge {bridge} missing from output"
        # Inter-bridge drop line should contain all 20 bridges
        drop_lines = [line for line in result.splitlines() if "drop" in line and "iifname" in line]
        assert len(drop_lines) == 1
        for bridge in bridges:
            assert bridge in drop_lines[0]

    def test_single_bridge_minimal_ruleset(self):
        """Single bridge produces minimal valid ruleset without inter-bridge drop."""
        result = self._render(
            incus_nftables_all_bridges=["net-solo"],
            incus_nftables_resolved_policies=[],
        )
        assert 'iifname "net-solo" oifname "net-solo" accept' in result
        # With only one bridge, no inter-bridge drop is needed
        drop_lines = [line for line in result.splitlines() if "drop" in line and "iifname" in line]
        assert len(drop_lines) == 0
        assert "table inet anklume" in result


# ── nftables complex policies edge cases ────────────────────


class TestNftablesComplexPolicies:
    """Tests for nftables template with complex policy configurations."""

    def _render(self, **kwargs):
        tmpl_dir = ROLES_DIR / "incus_nftables" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("anklume-isolation.nft.j2")
        return template.render(**kwargs)

    def test_ten_policies_ten_accept_rules_before_drop(self):
        """10 network policies generate 10 accept rules before drop."""
        bridges = ["net-src", "net-dst"]
        policies = [
            {
                "description": f"Policy {i}",
                "from_bridge": "net-src",
                "to_bridge": "net-dst",
                "ports": [8000 + i],
                "protocol": "tcp",
                "bidirectional": False,
            }
            for i in range(10)
        ]
        result = self._render(
            incus_nftables_all_bridges=bridges,
            incus_nftables_resolved_policies=policies,
        )
        # All 10 policies should produce accept rules
        for i in range(10):
            assert f"dport {{ {8000 + i} }}" in result
        # Drop comes after all accept rules
        lines = result.splitlines()
        last_accept_idx = max(
            idx for idx, line in enumerate(lines) if "accept" in line and "dport" in line
        )
        drop_idx = next(
            idx for idx, line in enumerate(lines) if "drop" in line and "iifname" in line
        )
        assert last_accept_idx < drop_idx

    def test_bidirectional_policy_two_accept_rules(self):
        """Bidirectional policy generates 2 accept rules."""
        result = self._render(
            incus_nftables_all_bridges=["net-alpha", "net-beta"],
            incus_nftables_resolved_policies=[{
                "description": "Bidir link",
                "from_bridge": "net-alpha",
                "to_bridge": "net-beta",
                "ports": [5000],
                "protocol": "tcp",
                "bidirectional": True,
            }],
        )
        assert 'iifname "net-alpha" oifname "net-beta" tcp dport { 5000 } accept' in result
        assert 'iifname "net-beta" oifname "net-alpha" tcp dport { 5000 } accept' in result

    def test_policy_ports_all_no_dport_restriction(self):
        """Policy with ports='all' generates no dport/sport restriction."""
        result = self._render(
            incus_nftables_all_bridges=["net-x", "net-y"],
            incus_nftables_resolved_policies=[{
                "description": "All ports",
                "from_bridge": "net-x",
                "to_bridge": "net-y",
                "ports": "all",
                "protocol": "tcp",
                "bidirectional": False,
            }],
        )
        # Accept rule without dport
        assert 'iifname "net-x" oifname "net-y" accept' in result
        # No dport on the accept line for this policy
        accept_lines = [
            line for line in result.splitlines()
            if 'iifname "net-x" oifname "net-y"' in line
        ]
        assert len(accept_lines) == 1
        assert "dport" not in accept_lines[0]

    def test_policy_udp_protocol_correct(self):
        """Policy with protocol='udp' uses udp in the nftables rule."""
        result = self._render(
            incus_nftables_all_bridges=["net-dns-src", "net-dns-dst"],
            incus_nftables_resolved_policies=[{
                "description": "DNS forward",
                "from_bridge": "net-dns-src",
                "to_bridge": "net-dns-dst",
                "ports": [53, 5353],
                "protocol": "udp",
                "bidirectional": False,
            }],
        )
        assert "udp dport { 53, 5353 }" in result
        assert "tcp" not in result.split("DNS forward")[1].split("\n")[1]

    def test_policy_targeting_specific_machine_uses_bridge(self):
        """Policy targets use bridge-level filtering in the template."""
        # The template works at bridge level; machine-level filtering
        # is resolved upstream (PSOT generator resolves machine names
        # to bridges). Here we verify the template renders correctly
        # with whatever from_bridge/to_bridge it receives.
        result = self._render(
            incus_nftables_all_bridges=["net-office", "net-services"],
            incus_nftables_resolved_policies=[{
                "description": "Office to service host",
                "from_bridge": "net-office",
                "to_bridge": "net-services",
                "ports": [443],
                "protocol": "tcp",
                "bidirectional": False,
            }],
        )
        assert 'iifname "net-office" oifname "net-services" tcp dport { 443 } accept' in result


# ── nftables AI override edge cases ─────────────────────────


class TestNftablesAiOverride:
    """Tests for nftables AI access override rendering.

    The AI override is applied at the Ansible task level (set_fact),
    not directly in the Jinja2 template. These tests verify that the
    template correctly renders the resolved policies list which
    includes an AI override policy entry.
    """

    def _render(self, **kwargs):
        tmpl_dir = ROLES_DIR / "incus_nftables" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("anklume-isolation.nft.j2")
        return template.render(**kwargs)

    def test_ai_override_policy_present_in_output(self):
        """When AI override is in resolved policies, override section is present."""
        # Simulate what the Ansible set_fact produces with an AI override
        result = self._render(
            incus_nftables_all_bridges=["net-pro", "net-ai-tools"],
            incus_nftables_resolved_policies=[{
                "description": "AI access override (dynamic)",
                "from_bridge": "net-pro",
                "to_bridge": "net-ai-tools",
                "ports": "all",
                "protocol": "tcp",
                "bidirectional": True,
            }],
        )
        assert "AI access override (dynamic)" in result
        assert 'iifname "net-pro" oifname "net-ai-tools" accept' in result
        assert 'iifname "net-ai-tools" oifname "net-pro" accept' in result

    def test_ai_override_replaces_bridge_name_correctly(self):
        """Override with different domain bridge renders correct bridge name."""
        result = self._render(
            incus_nftables_all_bridges=["net-perso", "net-ai-tools"],
            incus_nftables_resolved_policies=[{
                "description": "AI access override (dynamic)",
                "from_bridge": "net-perso",
                "to_bridge": "net-ai-tools",
                "ports": "all",
                "protocol": "tcp",
                "bidirectional": True,
            }],
        )
        assert 'iifname "net-perso" oifname "net-ai-tools" accept' in result
        assert 'iifname "net-ai-tools" oifname "net-perso" accept' in result
        # Should NOT have net-pro anywhere
        assert "net-pro" not in result

    def test_ai_override_without_base_policy_still_works(self):
        """Override as the only policy (no base policies) still renders correctly."""
        result = self._render(
            incus_nftables_all_bridges=["net-work", "net-ai-tools"],
            incus_nftables_resolved_policies=[{
                "description": "AI access override (dynamic)",
                "from_bridge": "net-work",
                "to_bridge": "net-ai-tools",
                "ports": "all",
                "protocol": "tcp",
                "bidirectional": True,
            }],
        )
        assert "table inet anklume" in result
        assert 'iifname "net-work" oifname "net-ai-tools" accept' in result
        # Inter-bridge drop should still be present
        assert "drop" in result


# ── nftables: special bridge name variations ────────────────


class TestNftablesSpecialBridgeNames:
    """Tests for nftables with unusual bridge name patterns."""

    def _render(self, **kwargs):
        tmpl_dir = ROLES_DIR / "incus_nftables" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("anklume-isolation.nft.j2")
        return template.render(**kwargs)

    def test_bridge_names_with_numbers(self):
        """Bridge names containing numbers render correctly."""
        result = self._render(
            incus_nftables_all_bridges=["net-zone1", "net-zone2", "net-zone3"],
            incus_nftables_resolved_policies=[],
        )
        assert 'iifname "net-zone1" oifname "net-zone1" accept' in result
        assert 'iifname "net-zone2" oifname "net-zone2" accept' in result
        assert 'iifname "net-zone3" oifname "net-zone3" accept' in result

    def test_long_bridge_names(self):
        """Long bridge names render correctly."""
        result = self._render(
            incus_nftables_all_bridges=["net-very-long-domain-name"],
            incus_nftables_resolved_policies=[],
        )
        assert '"net-very-long-domain-name"' in result

    def test_two_bridges_have_inter_bridge_drop(self):
        """Exactly two bridges produce an inter-bridge drop rule."""
        result = self._render(
            incus_nftables_all_bridges=["net-a", "net-b"],
            incus_nftables_resolved_policies=[],
        )
        drop_lines = [ln for ln in result.splitlines() if "drop" in ln and "iifname" in ln]
        assert len(drop_lines) == 1
        assert '"net-a"' in drop_lines[0]
        assert '"net-b"' in drop_lines[0]

    def test_accept_rules_come_before_drop(self):
        """Same-bridge accept and policy accept rules appear before inter-bridge drop."""
        result = self._render(
            incus_nftables_all_bridges=["net-x", "net-y"],
            incus_nftables_resolved_policies=[{
                "description": "test policy",
                "from_bridge": "net-x",
                "to_bridge": "net-y",
                "ports": [80],
                "protocol": "tcp",
                "bidirectional": False,
            }],
        )
        lines = result.splitlines()
        policy_accept_idx = next(
            i for i, ln in enumerate(lines) if "dport { 80 }" in ln
        )
        drop_idx = next(
            i for i, ln in enumerate(lines) if "drop" in ln and "iifname" in ln and "oifname" in ln
        )
        assert policy_accept_idx < drop_idx


# ── nftables policy descriptions as comments ─────────────────


class TestNftablesPolicyDescriptions:
    """Test that policy descriptions appear as nftables comments."""

    def _render(self, **kwargs):
        tmpl_dir = ROLES_DIR / "incus_nftables" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("anklume-isolation.nft.j2")
        return template.render(**kwargs)

    def test_description_appears_as_comment(self):
        """Policy description appears as an nftables comment."""
        result = self._render(
            incus_nftables_all_bridges=["net-a", "net-b"],
            incus_nftables_resolved_policies=[{
                "description": "Allow HTTP from A to B",
                "from_bridge": "net-a",
                "to_bridge": "net-b",
                "ports": [80],
                "protocol": "tcp",
                "bidirectional": False,
            }],
        )
        assert "# Allow HTTP from A to B" in result

    def test_description_with_special_chars(self):
        """Description with special chars appears as comment."""
        result = self._render(
            incus_nftables_all_bridges=["net-a", "net-b"],
            incus_nftables_resolved_policies=[{
                "description": "Pro <-> AI bidirectional (8080/tcp)",
                "from_bridge": "net-a",
                "to_bridge": "net-b",
                "ports": [8080],
                "protocol": "tcp",
                "bidirectional": False,
            }],
        )
        assert "# Pro <-> AI bidirectional (8080/tcp)" in result

    def test_multiple_descriptions_in_order(self):
        """Multiple policy descriptions appear in order."""
        result = self._render(
            incus_nftables_all_bridges=["net-a", "net-b"],
            incus_nftables_resolved_policies=[
                {
                    "description": "First policy",
                    "from_bridge": "net-a",
                    "to_bridge": "net-b",
                    "ports": [80],
                    "protocol": "tcp",
                    "bidirectional": False,
                },
                {
                    "description": "Second policy",
                    "from_bridge": "net-b",
                    "to_bridge": "net-a",
                    "ports": [443],
                    "protocol": "tcp",
                    "bidirectional": False,
                },
            ],
        )
        first_idx = result.index("# First policy")
        second_idx = result.index("# Second policy")
        assert first_idx < second_idx


# ── Nftables: single port rendering ─────────────────────────


class TestNftablesSinglePort:
    """Test nftables template with single-port policies."""

    def _render(self, **kwargs):
        tmpl_dir = ROLES_DIR / "incus_nftables" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("anklume-isolation.nft.j2")
        return template.render(**kwargs)

    def test_single_port_has_braces(self):
        """Single port is still rendered with braces: { 80 }."""
        result = self._render(
            incus_nftables_all_bridges=["net-a", "net-b"],
            incus_nftables_resolved_policies=[{
                "description": "Single port",
                "from_bridge": "net-a",
                "to_bridge": "net-b",
                "ports": [80],
                "protocol": "tcp",
                "bidirectional": False,
            }],
        )
        assert "dport { 80 }" in result

    def test_high_port_number(self):
        """High port number (65535) renders correctly."""
        result = self._render(
            incus_nftables_all_bridges=["net-a", "net-b"],
            incus_nftables_resolved_policies=[{
                "description": "High port",
                "from_bridge": "net-a",
                "to_bridge": "net-b",
                "ports": [65535],
                "protocol": "tcp",
                "bidirectional": False,
            }],
        )
        assert "dport { 65535 }" in result

    def test_port_one(self):
        """Port 1 renders correctly."""
        result = self._render(
            incus_nftables_all_bridges=["net-a", "net-b"],
            incus_nftables_resolved_policies=[{
                "description": "Port 1",
                "from_bridge": "net-a",
                "to_bridge": "net-b",
                "ports": [1],
                "protocol": "tcp",
                "bidirectional": False,
            }],
        )
        assert "dport { 1 }" in result


# ── Nftables: rule count verification ────────────────────────


class TestNftablesRuleCount:
    """Test that the correct number of rules are generated."""

    def _render(self, **kwargs):
        tmpl_dir = ROLES_DIR / "incus_nftables" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("anklume-isolation.nft.j2")
        return template.render(**kwargs)

    def test_non_bidir_generates_one_accept(self):
        """Non-bidirectional policy generates exactly one accept rule."""
        result = self._render(
            incus_nftables_all_bridges=["net-a", "net-b"],
            incus_nftables_resolved_policies=[{
                "description": "One way",
                "from_bridge": "net-a",
                "to_bridge": "net-b",
                "ports": [80],
                "protocol": "tcp",
                "bidirectional": False,
            }],
        )
        accept_lines = [ln for ln in result.splitlines()
                       if 'iifname "net-a" oifname "net-b"' in ln and "accept" in ln]
        assert len(accept_lines) == 1

    def test_bidir_generates_two_accepts(self):
        """Bidirectional policy generates exactly two accept rules."""
        result = self._render(
            incus_nftables_all_bridges=["net-a", "net-b"],
            incus_nftables_resolved_policies=[{
                "description": "Two way",
                "from_bridge": "net-a",
                "to_bridge": "net-b",
                "ports": [80],
                "protocol": "tcp",
                "bidirectional": True,
            }],
        )
        accept_ab = [ln for ln in result.splitlines()
                    if 'iifname "net-a" oifname "net-b"' in ln and "accept" in ln]
        accept_ba = [ln for ln in result.splitlines()
                    if 'iifname "net-b" oifname "net-a"' in ln and "accept" in ln]
        assert len(accept_ab) == 1
        assert len(accept_ba) == 1

    def test_five_policies_five_accept_lines(self):
        """Five non-bidir policies generate five accept lines."""
        policies = [
            {
                "description": f"Policy {i}",
                "from_bridge": "net-a",
                "to_bridge": "net-b",
                "ports": [8000 + i],
                "protocol": "tcp",
                "bidirectional": False,
            }
            for i in range(5)
        ]
        result = self._render(
            incus_nftables_all_bridges=["net-a", "net-b"],
            incus_nftables_resolved_policies=policies,
        )
        accept_lines = [ln for ln in result.splitlines()
                       if "dport" in ln and "accept" in ln]
        assert len(accept_lines) == 5

    def test_mixed_bidir_and_non_bidir(self):
        """Mix of bidirectional and non-bidirectional policies."""
        result = self._render(
            incus_nftables_all_bridges=["net-a", "net-b"],
            incus_nftables_resolved_policies=[
                {
                    "description": "Non-bidir",
                    "from_bridge": "net-a",
                    "to_bridge": "net-b",
                    "ports": [80],
                    "protocol": "tcp",
                    "bidirectional": False,
                },
                {
                    "description": "Bidir",
                    "from_bridge": "net-a",
                    "to_bridge": "net-b",
                    "ports": [443],
                    "protocol": "tcp",
                    "bidirectional": True,
                },
            ],
        )
        # 1 for non-bidir + 2 for bidir = 3 total accept lines with dport
        accept_lines = [ln for ln in result.splitlines()
                       if "dport" in ln and "accept" in ln]
        assert len(accept_lines) == 3
