"""Tests for firewall-router Jinja2 template edge cases.

Covers boundary conditions and advanced rendering for the firewall
router template (firewall_router role).
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


# ── firewall-router template edge cases ─────────────────────


class TestFirewallRouterEdgeCases:
    def _render(self, **kwargs):
        tmpl_dir = ROLES_DIR / "firewall_router" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("firewall-router.nft.j2")
        return template.render(**kwargs)

    def test_single_interface_no_inter_domain_rules(self):
        """With one interface, no inter-domain drop rules are generated."""
        result = self._render(
            firewall_router_interfaces=[{"name": "eth0", "bridge": "net-anklume"}],
            firewall_router_logging=True,
            firewall_router_log_prefix="FW",
        )
        assert "chain forward" in result
        # Should not have inter-domain deny rules with only one interface
        assert "FW-DENY" not in result

    def test_many_interfaces(self):
        """Template handles 5+ interfaces correctly."""
        ifaces = [{"name": f"eth{i}", "bridge": f"net-domain{i}"} for i in range(5)]
        result = self._render(
            firewall_router_interfaces=ifaces,
            firewall_router_logging=True,
            firewall_router_log_prefix="FW",
        )
        for i in range(5):
            assert f'"eth{i}"' in result
        # Each interface should deny traffic to all others
        assert "FW-DENY-DOMAIN0" in result
        assert "FW-DENY-DOMAIN4" in result

    def test_custom_log_prefix(self):
        """Custom log prefix is used throughout."""
        result = self._render(
            firewall_router_interfaces=[
                {"name": "eth0", "bridge": "net-anklume"},
                {"name": "eth1", "bridge": "net-pro"},
            ],
            firewall_router_logging=True,
            firewall_router_log_prefix="MYFW",
        )
        assert 'MYFW-DENY-ANKLUME' in result
        assert 'MYFW-INVALID' in result
        assert 'MYFW-DROP' in result
        assert 'MYFW-INPUT-DROP' in result

    def test_icmp_always_allowed(self):
        """ICMP is allowed regardless of configuration."""
        result = self._render(
            firewall_router_interfaces=[
                {"name": "eth0", "bridge": "net-anklume"},
                {"name": "eth1", "bridge": "net-pro"},
            ],
            firewall_router_logging=False,
            firewall_router_log_prefix="FW",
        )
        assert "meta l4proto icmp accept" in result
        assert "meta l4proto icmpv6 accept" in result

    def test_input_chain_has_loopback(self):
        """Input chain allows loopback traffic."""
        result = self._render(
            firewall_router_interfaces=[{"name": "eth0", "bridge": "net-test"}],
            firewall_router_logging=False,
            firewall_router_log_prefix="FW",
        )
        assert 'iifname "lo" accept' in result

    def test_output_chain_policy_accept(self):
        """Output chain has policy accept."""
        result = self._render(
            firewall_router_interfaces=[{"name": "eth0", "bridge": "net-test"}],
            firewall_router_logging=False,
            firewall_router_log_prefix="FW",
        )
        assert "chain output" in result
        assert "policy accept" in result

    def test_bridge_name_in_deny_prefix(self):
        """Deny log prefix uses bridge name without 'net-' prefix, uppercased."""
        result = self._render(
            firewall_router_interfaces=[
                {"name": "eth0", "bridge": "net-anklume"},
                {"name": "eth1", "bridge": "net-pro"},
            ],
            firewall_router_logging=True,
            firewall_router_log_prefix="FW",
        )
        # Bridge "net-anklume" -> "ANKLUME", "net-pro" -> "PRO"
        assert "FW-DENY-ANKLUME" in result
        assert "FW-DENY-PRO" in result


# ── firewall-router many interfaces edge cases ──────────────


class TestFirewallRouterManyInterfaces:
    """Tests for firewall-router template with many interfaces."""

    def _render(self, **kwargs):
        tmpl_dir = ROLES_DIR / "firewall_router" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("firewall-router.nft.j2")
        return template.render(**kwargs)

    def test_five_interfaces_correct_routing_rules(self):
        """5 interfaces generate correct deny rules for each."""
        ifaces = [
            {"name": f"eth{i}", "bridge": f"net-domain{i}"} for i in range(5)
        ]
        result = self._render(
            firewall_router_interfaces=ifaces,
            firewall_router_logging=True,
            firewall_router_log_prefix="FW",
        )
        # Each interface should be present
        for i in range(5):
            assert f'"eth{i}"' in result
        # Each interface should deny traffic to all others
        for i in range(5):
            deny_line = [
                line for line in result.splitlines()
                if f'iifname "eth{i}"' in line and "drop" in line
            ]
            assert len(deny_line) == 1, f"Missing deny rule for eth{i}"
            # The deny line should reference the 4 other interfaces
            for j in range(5):
                if j != i:
                    assert f'"eth{j}"' in deny_line[0]

    def test_admin_on_eth0_admin_rules_applied(self):
        """Anklume interface on eth0 gets anklume-specific deny prefix."""
        ifaces = [
            {"name": "eth0", "bridge": "net-anklume"},
            {"name": "eth1", "bridge": "net-pro"},
            {"name": "eth2", "bridge": "net-perso"},
        ]
        result = self._render(
            firewall_router_interfaces=ifaces,
            firewall_router_logging=True,
            firewall_router_log_prefix="FW",
        )
        assert "FW-DENY-ANKLUME" in result
        assert "FW-DENY-PRO" in result
        assert "FW-DENY-PERSO" in result

    def test_no_non_admin_interfaces_minimal_ruleset(self):
        """With only one interface, no inter-domain deny rules are generated."""
        result = self._render(
            firewall_router_interfaces=[{"name": "eth0", "bridge": "net-anklume"}],
            firewall_router_logging=True,
            firewall_router_log_prefix="FW",
        )
        # Only one interface means no inter-domain deny
        assert "FW-DENY" not in result
        # But the chain structure should still be valid
        assert "chain forward" in result
        assert "chain input" in result
        assert "chain output" in result
        assert "ct state established,related accept" in result


# ── Firewall router: logging disabled ────────────────────────


class TestFirewallRouterLoggingDisabled:
    """Test firewall-router template with logging=False."""

    def _render(self, **kwargs):
        tmpl_dir = ROLES_DIR / "firewall_router" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("firewall-router.nft.j2")
        return template.render(**kwargs)

    def test_no_log_prefix_when_disabled(self):
        """No log prefix strings appear when logging is disabled."""
        result = self._render(
            firewall_router_interfaces=[
                {"name": "eth0", "bridge": "net-anklume"},
                {"name": "eth1", "bridge": "net-pro"},
            ],
            firewall_router_logging=False,
            firewall_router_log_prefix="FW",
        )
        assert "log prefix" not in result

    def test_drop_still_present_without_logging(self):
        """Drop rules still present when logging is disabled."""
        result = self._render(
            firewall_router_interfaces=[
                {"name": "eth0", "bridge": "net-anklume"},
                {"name": "eth1", "bridge": "net-pro"},
            ],
            firewall_router_logging=False,
            firewall_router_log_prefix="FW",
        )
        assert "drop" in result

    def test_chain_structure_intact_without_logging(self):
        """All three chains exist without logging."""
        result = self._render(
            firewall_router_interfaces=[
                {"name": "eth0", "bridge": "net-anklume"},
                {"name": "eth1", "bridge": "net-pro"},
            ],
            firewall_router_logging=False,
            firewall_router_log_prefix="FW",
        )
        assert "chain forward" in result
        assert "chain input" in result
        assert "chain output" in result


# ── Firewall router: bridge name extraction ──────────────────


class TestFirewallRouterBridgeNameExtraction:
    """Test that bridge name is correctly extracted for deny prefix."""

    def _render(self, **kwargs):
        tmpl_dir = ROLES_DIR / "firewall_router" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("firewall-router.nft.j2")
        return template.render(**kwargs)

    def test_net_prefix_removed(self):
        """The 'net-' prefix is removed from bridge name in log prefix."""
        result = self._render(
            firewall_router_interfaces=[
                {"name": "eth0", "bridge": "net-anklume"},
                {"name": "eth1", "bridge": "net-perso"},
            ],
            firewall_router_logging=True,
            firewall_router_log_prefix="FW",
        )
        assert "FW-DENY-ANKLUME" in result
        assert "FW-DENY-PERSO" in result
        # Should NOT contain "NET-" in the prefix
        assert "FW-DENY-NET-" not in result

    def test_bridge_with_multiple_hyphens(self):
        """Bridge with multiple hyphens extracts correctly."""
        result = self._render(
            firewall_router_interfaces=[
                {"name": "eth0", "bridge": "net-anklume"},
                {"name": "eth1", "bridge": "net-ai-tools"},
            ],
            firewall_router_logging=True,
            firewall_router_log_prefix="FW",
        )
        assert "FW-DENY-AI-TOOLS" in result

    def test_ten_interfaces_all_have_deny_rules(self):
        """10 interfaces each get their own deny rule."""
        ifaces = [
            {"name": f"eth{i}", "bridge": f"net-dom{i}"} for i in range(10)
        ]
        result = self._render(
            firewall_router_interfaces=ifaces,
            firewall_router_logging=True,
            firewall_router_log_prefix="FW",
        )
        for i in range(10):
            assert f"FW-DENY-DOM{i}" in result


# ── Firewall router: chain policies ─────────────────────────


class TestFirewallRouterChainPolicies:
    """Test firewall-router chain default policies."""

    def _render(self, **kwargs):
        tmpl_dir = ROLES_DIR / "firewall_router" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("firewall-router.nft.j2")
        return template.render(**kwargs)

    def test_forward_policy_drop(self):
        """Forward chain has default policy drop."""
        result = self._render(
            firewall_router_interfaces=[{"name": "eth0", "bridge": "net-anklume"}],
            firewall_router_logging=False,
            firewall_router_log_prefix="FW",
        )
        # Find the forward chain line
        forward_lines = [ln for ln in result.splitlines() if "chain forward" in ln]
        assert len(forward_lines) == 1
        # Policy should be on the next line
        idx = result.splitlines().index(forward_lines[0])
        next_line = result.splitlines()[idx + 1]
        assert "policy drop" in next_line

    def test_input_policy_drop(self):
        """Input chain has default policy drop."""
        result = self._render(
            firewall_router_interfaces=[{"name": "eth0", "bridge": "net-anklume"}],
            firewall_router_logging=False,
            firewall_router_log_prefix="FW",
        )
        lines = result.splitlines()
        input_idx = next(i for i, ln in enumerate(lines) if "chain input" in ln)
        assert "policy drop" in lines[input_idx + 1]

    def test_output_policy_accept(self):
        """Output chain has default policy accept."""
        result = self._render(
            firewall_router_interfaces=[{"name": "eth0", "bridge": "net-anklume"}],
            firewall_router_logging=False,
            firewall_router_log_prefix="FW",
        )
        lines = result.splitlines()
        output_idx = next(i for i, ln in enumerate(lines) if "chain output" in ln)
        assert "policy accept" in lines[output_idx + 1]

    def test_atomic_replacement_header(self):
        """Firewall router template uses atomic table replacement."""
        result = self._render(
            firewall_router_interfaces=[{"name": "eth0", "bridge": "net-anklume"}],
            firewall_router_logging=False,
            firewall_router_log_prefix="FW",
        )
        assert "table inet anklume" in result
        assert "delete table inet anklume" in result
