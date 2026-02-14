"""Tests for Jinja2 template edge cases — boundary conditions and advanced rendering.

Complements test_roles.py with edge cases not covered by basic rendering tests:
- nftables with AI override
- nftables with bidirectional policies
- nftables with 'all' ports
- Firewall router with single interface
- Speaches with language set
- Claude settings with various permission modes
"""

import json
import re
import sys
import tempfile
from pathlib import Path

import pytest
import yaml

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
            incus_nftables_all_bridges=["net-admin", "net-work"],
            incus_nftables_resolved_policies=[{
                "description": "Full access",
                "from_bridge": "net-admin",
                "to_bridge": "net-work",
                "ports": "all",
                "protocol": "tcp",
                "bidirectional": False,
            }],
        )
        # Should have accept without tcp dport
        assert 'iifname "net-admin" oifname "net-work" accept' in result
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
            firewall_router_interfaces=[{"name": "eth0", "bridge": "net-admin"}],
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
                {"name": "eth0", "bridge": "net-admin"},
                {"name": "eth1", "bridge": "net-pro"},
            ],
            firewall_router_logging=True,
            firewall_router_log_prefix="MYFW",
        )
        assert 'MYFW-DENY-ADMIN' in result
        assert 'MYFW-INVALID' in result
        assert 'MYFW-DROP' in result
        assert 'MYFW-INPUT-DROP' in result

    def test_icmp_always_allowed(self):
        """ICMP is allowed regardless of configuration."""
        result = self._render(
            firewall_router_interfaces=[
                {"name": "eth0", "bridge": "net-admin"},
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
                {"name": "eth0", "bridge": "net-admin"},
                {"name": "eth1", "bridge": "net-pro"},
            ],
            firewall_router_logging=True,
            firewall_router_log_prefix="FW",
        )
        # Bridge "net-admin" → "ADMIN", "net-pro" → "PRO"
        assert "FW-DENY-ADMIN" in result
        assert "FW-DENY-PRO" in result


# ── speaches service template edge cases ────────────────────


class TestSpeachesEdgeCases:
    def _render(self, **kwargs):
        tmpl_dir = ROLES_DIR / "stt_server" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("speaches.service.j2")
        return template.render(ansible_managed="Ansible managed", **kwargs)

    def test_with_language_set(self):
        """Speaches template includes language when set."""
        result = self._render(
            stt_server_host="0.0.0.0",
            stt_server_port=8000,
            stt_server_model="large-v3-turbo",
            stt_server_quantization="float16",
            stt_server_language="fr",
        )
        assert "WHISPER__LANGUAGE=fr" in result

    def test_without_language(self):
        """Speaches template omits language when empty."""
        result = self._render(
            stt_server_host="0.0.0.0",
            stt_server_port=8000,
            stt_server_model="large-v3-turbo",
            stt_server_quantization="float16",
            stt_server_language="",
        )
        assert "WHISPER__LANGUAGE" not in result
        assert "WHISPER__MODEL=large-v3-turbo" in result

    def test_int8_quantization(self):
        """Speaches template renders int8 quantization."""
        result = self._render(
            stt_server_host="0.0.0.0",
            stt_server_port=9000,
            stt_server_model="medium",
            stt_server_quantization="int8",
            stt_server_language="",
        )
        assert "WHISPER__COMPUTE_TYPE=int8" in result
        assert "WHISPER__MODEL=medium" in result

    def test_custom_host_and_port(self):
        """Speaches template uses custom host and port."""
        result = self._render(
            stt_server_host="127.0.0.1",
            stt_server_port=9999,
            stt_server_model="small",
            stt_server_quantization="float16",
            stt_server_language="",
        )
        assert "--host 127.0.0.1" in result
        assert "--port 9999" in result

    def test_systemd_restart_policy(self):
        """Speaches service has restart always policy."""
        result = self._render(
            stt_server_host="0.0.0.0",
            stt_server_port=8000,
            stt_server_model="large-v3-turbo",
            stt_server_quantization="float16",
            stt_server_language="",
        )
        assert "Restart=always" in result
        assert "RestartSec=5" in result


# ── lobechat service template edge cases ────────────────────


class TestLobechatEdgeCases:
    def _render(self, **kwargs):
        tmpl_dir = ROLES_DIR / "lobechat" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("lobechat.service.j2")
        return template.render(**kwargs)

    def test_custom_port(self):
        """LobeChat template uses custom port."""
        result = self._render(
            lobechat_port=4000,
            lobechat_ollama_url="http://localhost:11434",
        )
        assert '"PORT=4000"' in result or "PORT=4000" in result

    def test_remote_ollama_url(self):
        """LobeChat template connects to remote Ollama."""
        result = self._render(
            lobechat_port=3210,
            lobechat_ollama_url="http://10.100.3.10:11434",
        )
        assert "10.100.3.10:11434" in result

    def test_has_enabled_ollama(self):
        """LobeChat template enables Ollama integration."""
        result = self._render(
            lobechat_port=3210,
            lobechat_ollama_url="http://ai-ollama:11434",
        )
        assert "ENABLED_OLLAMA=1" in result

    def test_working_directory(self):
        """LobeChat service runs from /opt/lobechat."""
        result = self._render(
            lobechat_port=3210,
            lobechat_ollama_url="http://ai-ollama:11434",
        )
        assert "WorkingDirectory=/opt/lobechat" in result

    def test_hostname_binds_all(self):
        """LobeChat listens on all interfaces."""
        result = self._render(
            lobechat_port=3210,
            lobechat_ollama_url="http://ai-ollama:11434",
        )
        assert "HOSTNAME=0.0.0.0" in result


# ── opencode templates edge cases ───────────────────────────


class TestOpencodeEdgeCases:
    def test_service_custom_host(self):
        """OpenCode service uses custom host binding."""
        tmpl_dir = ROLES_DIR / "opencode_server" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("opencode.service.j2")
        result = template.render(
            opencode_server_port=5000,
            opencode_server_host="127.0.0.1",
            opencode_server_password="mypass",
        )
        assert "--hostname 127.0.0.1" in result
        assert "--port 5000" in result
        assert "OPENCODE_SERVER_PASSWORD=mypass" in result

    def test_config_custom_model(self):
        """OpenCode config renders with custom model name."""
        tmpl_dir = ROLES_DIR / "opencode_server" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("opencode-config.json.j2")
        result = template.render(
            opencode_server_ollama_url="http://localhost:11434/v1",
            opencode_server_model="codellama:70b",
        )
        data = json.loads(result)
        assert "codellama:70b" in data["provider"]["ollama"]["models"]
        model_entry = data["provider"]["ollama"]["models"]["codellama:70b"]
        assert model_entry["name"] == "codellama:70b"

    def test_config_valid_json(self):
        """OpenCode config renders valid JSON with various inputs."""
        tmpl_dir = ROLES_DIR / "opencode_server" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("opencode-config.json.j2")
        result = template.render(
            opencode_server_ollama_url="http://10.0.0.1:11434/v1",
            opencode_server_model="deepseek-coder:6.7b",
        )
        data = json.loads(result)
        assert data["$schema"] == "https://opencode.ai/config.json"
        assert data["provider"]["ollama"]["npm"] == "@ai-sdk/openai-compatible"


# ── claude-settings template edge cases ─────────────────────


class TestClaudeSettingsEdgeCases:
    def _render(self, **kwargs):
        tmpl_dir = ROLES_DIR / "dev_agent_runner" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("claude-settings.json.j2")
        return template.render(**kwargs)

    def test_deny_list_present(self):
        """Claude settings include deny list for dangerous commands."""
        result = self._render(
            dev_agent_runner_enable_teams=True,
            dev_agent_runner_permissions_mode="bypassPermissions",
        )
        data = json.loads(result)
        deny = data["permissions"]["deny"]
        assert "Bash(rm -rf /)" in deny
        assert "Bash(curl * | bash)" in deny
        assert "Bash(wget * | bash)" in deny

    def test_all_expected_permissions(self):
        """Claude settings include all expected tool permissions."""
        result = self._render(
            dev_agent_runner_enable_teams=True,
            dev_agent_runner_permissions_mode="bypassPermissions",
        )
        data = json.loads(result)
        allow = data["permissions"]["allow"]
        expected = [
            "Edit", "MultiEdit", "Write", "Read", "Glob", "Grep",
            "Bash(molecule *)", "Bash(ansible-lint *)", "Bash(yamllint *)",
            "Bash(ruff *)", "Bash(git *)", "Bash(incus *)",
            "Bash(make *)", "Bash(python3 *)", "Bash(pytest *)",
        ]
        for perm in expected:
            assert perm in allow, f"Missing permission: {perm}"

    def test_different_permission_modes(self):
        """Claude settings render different permission modes."""
        for mode in ["bypassPermissions", "default", "plan"]:
            result = self._render(
                dev_agent_runner_enable_teams=True,
                dev_agent_runner_permissions_mode=mode,
            )
            data = json.loads(result)
            assert data["defaultMode"] == mode


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
        """Admin interface on eth0 gets admin-specific deny prefix."""
        ifaces = [
            {"name": "eth0", "bridge": "net-admin"},
            {"name": "eth1", "bridge": "net-pro"},
            {"name": "eth2", "bridge": "net-perso"},
        ]
        result = self._render(
            firewall_router_interfaces=ifaces,
            firewall_router_logging=True,
            firewall_router_log_prefix="FW",
        )
        assert "FW-DENY-ADMIN" in result
        assert "FW-DENY-PRO" in result
        assert "FW-DENY-PERSO" in result

    def test_no_non_admin_interfaces_minimal_ruleset(self):
        """With only one interface, no inter-domain deny rules are generated."""
        result = self._render(
            firewall_router_interfaces=[{"name": "eth0", "bridge": "net-admin"}],
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


# ── PSOT generator edge cases (template-level) ──────────────────
# Tests below exercise scripts/generate.py functions through
# unusual YAML structures, boundary values, and special content.

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from generate import (  # noqa: E402
    MANAGED_BEGIN,
    MANAGED_END,
    _managed_block,
    _write_managed,
    _yaml,
    detect_orphans,
    enrich_infra,
    extract_all_images,
    generate,
    validate,
)


def _minimal_infra(**overrides):
    """Build a minimal valid infra dict with optional overrides."""
    infra = {
        "project_name": "edge-test",
        "global": {"base_subnet": "10.100", "default_os_image": "images:debian/13"},
        "domains": {
            "test": {
                "subnet_id": 1,
                "machines": {
                    "test-m1": {"type": "lxc", "ip": "10.100.1.10"},
                },
            },
        },
    }
    infra.update(overrides)
    return infra


# ── Unusual YAML values in descriptions ──────────────────────


class TestPSOTUnusualYAMLValues:
    """Test the generator with unusual descriptions and string values."""

    def test_description_with_colon(self):
        """Descriptions containing colons don't break YAML output."""
        infra = _minimal_infra()
        infra["domains"]["test"]["description"] = "My domain: the best one"
        errors = validate(infra)
        assert errors == []
        with tempfile.TemporaryDirectory() as d:
            files = generate(infra, d, dry_run=True)
            assert len(files) > 0

    def test_description_with_hash(self):
        """Descriptions containing hash characters don't break YAML."""
        infra = _minimal_infra()
        infra["domains"]["test"]["description"] = "Domain #1 is great"
        errors = validate(infra)
        assert errors == []
        with tempfile.TemporaryDirectory() as d:
            files = generate(infra, d, dry_run=True)
            assert len(files) > 0

    def test_description_with_quotes(self):
        """Descriptions with quotes are handled correctly."""
        infra = _minimal_infra()
        infra["domains"]["test"]["description"] = 'Domain "quoted" description'
        errors = validate(infra)
        assert errors == []
        with tempfile.TemporaryDirectory() as d:
            files = generate(infra, d, dry_run=True)
            assert len(files) > 0

    def test_description_with_unicode(self):
        """Unicode descriptions (French) are preserved."""
        infra = _minimal_infra()
        infra["domains"]["test"]["description"] = "Domaine professionnel avec accents aeio"
        errors = validate(infra)
        assert errors == []
        with tempfile.TemporaryDirectory() as d:
            files = generate(infra, d, dry_run=True)
            # Simply verify generation succeeds
            assert len(files) > 0

    def test_empty_description(self):
        """Empty description is valid."""
        infra = _minimal_infra()
        infra["domains"]["test"]["description"] = ""
        errors = validate(infra)
        assert errors == []

    def test_description_with_newline_in_machine(self):
        """Machine description with embedded newlines is valid."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"]["test-m1"]["description"] = "line1\nline2"
        errors = validate(infra)
        assert errors == []

    def test_config_with_boolean_string(self):
        """Config values like 'true' as string are valid."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"]["test-m1"]["config"] = {
            "security.nesting": "true",
            "security.privileged": "false",
        }
        errors = validate(infra)
        assert errors == []

    def test_config_with_numeric_string(self):
        """Config values like '2' as string are valid."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"]["test-m1"]["config"] = {
            "limits.cpu": "2",
            "limits.memory": "4GiB",
        }
        errors = validate(infra)
        assert errors == []

    def test_roles_as_empty_list(self):
        """Machine with empty roles list is valid."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"]["test-m1"]["roles"] = []
        errors = validate(infra)
        assert errors == []


# ── Deeply nested profile configurations ─────────────────────


class TestPSOTDeeplyNestedConfigs:
    """Test profiles with complex nested config and device structures."""

    def test_profile_with_config_and_devices(self):
        """Profiles with both config and devices are valid."""
        infra = _minimal_infra()
        infra["domains"]["test"]["profiles"] = {
            "complex": {
                "config": {"limits.cpu": "4", "limits.memory": "8GiB"},
                "devices": {
                    "gpu": {"type": "gpu", "gputype": "physical"},
                    "disk": {"type": "disk", "path": "/data", "source": "/mnt/data"},
                },
            },
        }
        infra["domains"]["test"]["machines"]["test-m1"]["profiles"] = ["default", "complex"]
        errors = validate(infra)
        assert errors == []

    def test_multiple_profiles_per_domain(self):
        """Domain with many profiles is valid."""
        infra = _minimal_infra()
        infra["domains"]["test"]["profiles"] = {
            f"profile-{i}": {"config": {f"user.label{i}": f"val{i}"}}
            for i in range(5)
        }
        errors = validate(infra)
        assert errors == []

    def test_machine_references_multiple_profiles(self):
        """Machine referencing multiple domain profiles is valid."""
        infra = _minimal_infra()
        infra["domains"]["test"]["profiles"] = {
            "nesting": {"config": {"security.nesting": "true"}},
            "resources": {"config": {"limits.cpu": "2"}},
        }
        infra["domains"]["test"]["machines"]["test-m1"]["profiles"] = [
            "default", "nesting", "resources",
        ]
        errors = validate(infra)
        assert errors == []

    def test_storage_volumes_in_machine(self):
        """Machine with storage_volumes passes validation."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"]["test-m1"]["storage_volumes"] = {
            "data": {"pool": "default", "size": "10GiB"},
        }
        errors = validate(infra)
        assert errors == []


# ── Subnet boundary values ───────────────────────────────────


class TestPSOTSubnetBoundary:
    """Test subnet_id at boundaries (0, 254) and generation."""

    def test_subnet_id_zero(self):
        """subnet_id=0 is valid."""
        infra = _minimal_infra()
        infra["domains"]["test"]["subnet_id"] = 0
        infra["domains"]["test"]["machines"]["test-m1"]["ip"] = "10.100.0.10"
        errors = validate(infra)
        assert errors == []

    def test_subnet_id_254(self):
        """subnet_id=254 is valid."""
        infra = _minimal_infra()
        infra["domains"]["test"]["subnet_id"] = 254
        infra["domains"]["test"]["machines"]["test-m1"]["ip"] = "10.100.254.10"
        errors = validate(infra)
        assert errors == []

    def test_subnet_id_negative_rejected(self):
        """subnet_id=-1 is rejected."""
        infra = _minimal_infra()
        infra["domains"]["test"]["subnet_id"] = -1
        errors = validate(infra)
        assert any("subnet_id must be 0-254" in e for e in errors)

    def test_subnet_id_255_rejected(self):
        """subnet_id=255 is rejected."""
        infra = _minimal_infra()
        infra["domains"]["test"]["subnet_id"] = 255
        errors = validate(infra)
        assert any("subnet_id must be 0-254" in e for e in errors)

    def test_many_subnets_no_collision(self):
        """Many domains with unique subnet_ids validate successfully."""
        infra = _minimal_infra()
        infra["domains"] = {}
        for i in range(10):
            infra["domains"][f"dom{i}"] = {
                "subnet_id": i * 25,
                "machines": {
                    f"m{i}": {"type": "lxc", "ip": f"10.100.{i*25}.10"},
                },
            }
        errors = validate(infra)
        assert errors == []


# ── Large-scale infrastructure ───────────────────────────────


class TestPSOTLargeScale:
    """Test with many domains and machines."""

    def test_twenty_domains(self):
        """20 domains with unique subnet_ids pass validation."""
        infra = _minimal_infra()
        infra["domains"] = {}
        for i in range(20):
            infra["domains"][f"zone{i}"] = {
                "subnet_id": i,
                "machines": {
                    f"zone{i}-host": {"type": "lxc", "ip": f"10.100.{i}.10"},
                },
            }
        errors = validate(infra)
        assert errors == []

    def test_ten_machines_per_domain(self):
        """Domain with 10 machines passes validation."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"] = {
            f"test-m{i}": {"type": "lxc", "ip": f"10.100.1.{10+i}"}
            for i in range(10)
        }
        errors = validate(infra)
        assert errors == []

    def test_mixed_lxc_and_vm(self):
        """Domain with both LXC and VM machines passes validation."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"] = {
            "test-lxc": {"type": "lxc", "ip": "10.100.1.10"},
            "test-vm": {
                "type": "vm",
                "ip": "10.100.1.20",
                "config": {"limits.cpu": "2", "limits.memory": "2GiB"},
            },
        }
        errors = validate(infra)
        assert errors == []


# ── Managed section preservation ─────────────────────────────


class TestPSOTManagedPreservation:
    """Test _write_managed with various existing file content."""

    def test_multiline_user_content_preserved(self):
        """User content before and after managed section is preserved."""
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "test.yml"
            existing = (
                "---\n"
                "# User header\n"
                f"{MANAGED_BEGIN}\n"
                "# Do not edit this section\n"
                "old: data\n"
                f"{MANAGED_END}\n"
                "\n"
                "# User variable 1\n"
                "custom_var: hello\n"
                "# User variable 2\n"
                "other_var: world\n"
            )
            p.write_text(existing)
            _write_managed(p, {"new": "data"})
            result = p.read_text()
            assert "custom_var: hello" in result
            assert "other_var: world" in result
            assert "User header" in result
            assert "new: data" in result
            assert "old: data" not in result

    def test_unicode_in_managed_content(self):
        """Unicode content in managed section is preserved correctly."""
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "test.yml"
            _write_managed(p, {"description": "Domaine francais"})
            result = p.read_text()
            assert "Domaine francais" in result

    def test_empty_dict_generates_valid_managed(self):
        """Empty dict generates a valid managed section."""
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "test.yml"
            _write_managed(p, {})
            result = p.read_text()
            assert MANAGED_BEGIN in result
            assert MANAGED_END in result
            assert "{}" in result or result.count("\n") >= 2

    def test_no_duplication_on_double_write(self):
        """Writing twice doesn't duplicate the managed section."""
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "test.yml"
            _write_managed(p, {"v": 1})
            _write_managed(p, {"v": 2})
            result = p.read_text()
            assert result.count(MANAGED_BEGIN) == 1
            assert result.count(MANAGED_END) == 1
            assert "v: 2" in result

    def test_write_to_nonexistent_subdirectory(self):
        """Writing to a path with missing parent dirs creates them."""
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "sub" / "deep" / "test.yml"
            _write_managed(p, {"key": "value"})
            assert p.exists()
            assert "key: value" in p.read_text()


# ── Profile inheritance edge cases ───────────────────────────


class TestPSOTProfileInheritance:
    """Test profile reference validation and inheritance."""

    def test_config_only_profile(self):
        """Profile with config but no devices is valid."""
        infra = _minimal_infra()
        infra["domains"]["test"]["profiles"] = {
            "limits": {"config": {"limits.cpu": "4"}},
        }
        infra["domains"]["test"]["machines"]["test-m1"]["profiles"] = ["default", "limits"]
        errors = validate(infra)
        assert errors == []

    def test_device_only_profile(self):
        """Profile with devices but no config is valid."""
        infra = _minimal_infra()
        infra["domains"]["test"]["profiles"] = {
            "gpu-prof": {"devices": {"gpu": {"type": "gpu", "gputype": "physical"}}},
        }
        infra["domains"]["test"]["machines"]["test-m1"]["profiles"] = ["default", "gpu-prof"]
        infra["domains"]["test"]["machines"]["test-m1"]["gpu"] = True
        errors = validate(infra)
        assert errors == []

    def test_empty_profile(self):
        """Empty profile definition is valid (no config, no devices)."""
        infra = _minimal_infra()
        infra["domains"]["test"]["profiles"] = {"empty-prof": {}}
        infra["domains"]["test"]["machines"]["test-m1"]["profiles"] = ["default", "empty-prof"]
        errors = validate(infra)
        assert errors == []

    def test_no_profiles_on_machine(self):
        """Machine without profiles key is valid."""
        infra = _minimal_infra()
        assert "profiles" not in infra["domains"]["test"]["machines"]["test-m1"]
        errors = validate(infra)
        assert errors == []

    def test_default_profile_always_valid(self):
        """Referencing 'default' profile never causes an error."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"]["test-m1"]["profiles"] = ["default"]
        errors = validate(infra)
        assert errors == []

    def test_unknown_profile_rejected(self):
        """Referencing an undefined profile produces an error."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"]["test-m1"]["profiles"] = ["default", "nonexistent"]
        errors = validate(infra)
        assert any("profile 'nonexistent' not defined" in e for e in errors)

    def test_gpu_detected_through_profile_device(self):
        """GPU detection works through profile device scanning."""
        infra = _minimal_infra()
        infra["domains"]["test"]["profiles"] = {
            "nvidia": {"devices": {"gpu": {"type": "gpu"}}},
        }
        infra["domains"]["test"]["machines"]["test-m1"]["profiles"] = ["default", "nvidia"]
        # With exclusive GPU policy, one GPU instance is fine
        errors = validate(infra)
        assert errors == []


# ── Empty sections and minimal structures ────────────────────


class TestPSOTEmptySections:
    """Test with missing, null, or empty sections."""

    def test_domain_with_no_machines_key(self):
        """Domain without 'machines' key passes validation."""
        infra = _minimal_infra()
        del infra["domains"]["test"]["machines"]
        errors = validate(infra)
        assert errors == []

    def test_domain_with_null_machines(self):
        """Domain with machines: null passes validation."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"] = None
        errors = validate(infra)
        assert errors == []

    def test_domain_with_null_profiles(self):
        """Domain with profiles: null passes validation."""
        infra = _minimal_infra()
        infra["domains"]["test"]["profiles"] = None
        errors = validate(infra)
        assert errors == []

    def test_minimal_machine_no_optional_fields(self):
        """Machine with only type and ip is valid."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"]["test-m1"] = {
            "type": "lxc",
            "ip": "10.100.1.10",
        }
        errors = validate(infra)
        assert errors == []

    def test_empty_network_policies(self):
        """Empty network_policies list is valid."""
        infra = _minimal_infra()
        infra["network_policies"] = []
        errors = validate(infra)
        assert errors == []

    def test_minimal_global_section(self):
        """Global with just base_subnet is valid."""
        infra = _minimal_infra()
        infra["global"] = {"base_subnet": "10.100"}
        errors = validate(infra)
        assert errors == []


# ── Special domain and machine names ─────────────────────────


class TestPSOTSpecialNames:
    """Test domain and machine names at edge cases."""

    def test_numeric_domain_name(self):
        """Domain name starting with number is valid if alphanumeric."""
        infra = _minimal_infra()
        infra["domains"]["1lab"] = {
            "subnet_id": 50,
            "machines": {"lab-m1": {"type": "lxc", "ip": "10.100.50.10"}},
        }
        errors = validate(infra)
        # '1lab' starts with a digit which is valid per regex ^[a-z0-9][a-z0-9-]*$
        assert not any("1lab" in e and "invalid name" in e for e in errors)

    def test_domain_name_with_many_hyphens(self):
        """Domain name with multiple hyphens is valid."""
        infra = _minimal_infra()
        infra["domains"]["my-long-domain-name"] = {
            "subnet_id": 60,
            "machines": {
                "my-long-domain-name-m1": {"type": "lxc", "ip": "10.100.60.10"},
            },
        }
        errors = validate(infra)
        name_errors = [e for e in errors if "my-long-domain-name" in e and "invalid name" in e]
        assert len(name_errors) == 0

    def test_ai_tools_domain_name(self):
        """Domain named 'ai-tools' is valid."""
        infra = _minimal_infra()
        infra["domains"]["ai-tools"] = {
            "subnet_id": 10,
            "machines": {
                "ai-ollama": {"type": "lxc", "ip": "10.100.10.10"},
            },
        }
        errors = validate(infra)
        name_errors = [e for e in errors if "ai-tools" in e and "invalid name" in e]
        assert len(name_errors) == 0

    def test_single_letter_domain(self):
        """Single-letter domain name is valid."""
        infra = _minimal_infra()
        infra["domains"]["x"] = {
            "subnet_id": 70,
            "machines": {"x-m1": {"type": "lxc", "ip": "10.100.70.10"}},
        }
        errors = validate(infra)
        name_errors = [e for e in errors if "'x'" in e and "invalid name" in e]
        assert len(name_errors) == 0

    def test_uppercase_domain_rejected(self):
        """Domain with uppercase letters is rejected."""
        infra = _minimal_infra()
        infra["domains"]["MyDomain"] = {
            "subnet_id": 80,
            "machines": {"my-m1": {"type": "lxc", "ip": "10.100.80.10"}},
        }
        errors = validate(infra)
        assert any("MyDomain" in e and "invalid name" in e for e in errors)

    def test_domain_starting_with_hyphen_rejected(self):
        """Domain starting with hyphen is rejected."""
        infra = _minimal_infra()
        infra["domains"]["-bad"] = {
            "subnet_id": 90,
            "machines": {"bad-m1": {"type": "lxc", "ip": "10.100.90.10"}},
        }
        errors = validate(infra)
        assert any("-bad" in e and "invalid name" in e for e in errors)

    def test_domain_with_underscore_rejected(self):
        """Domain with underscore is rejected."""
        infra = _minimal_infra()
        infra["domains"]["my_domain"] = {
            "subnet_id": 91,
            "machines": {"my-m1": {"type": "lxc", "ip": "10.100.91.10"}},
        }
        errors = validate(infra)
        assert any("my_domain" in e and "invalid name" in e for e in errors)

    def test_long_machine_name(self):
        """Long machine name is valid (no length limit in spec)."""
        infra = _minimal_infra()
        long_name = "a" * 63  # DNS label limit
        infra["domains"]["test"]["machines"][long_name] = {
            "type": "lxc", "ip": "10.100.1.20",
        }
        errors = validate(infra)
        # Should be valid (no length validation in generate.py)
        assert not any(long_name in e for e in errors)


# ── Image extraction edge cases ──────────────────────────────


class TestPSOTImageEdgeCases:
    """Test extract_all_images with various configurations."""

    def test_different_images_per_machine(self):
        """Different os_image per machine are all extracted."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"]["test-m1"]["os_image"] = "images:ubuntu/24.04"
        infra["domains"]["test"]["machines"]["test-m2"] = {
            "type": "lxc",
            "ip": "10.100.1.20",
            "os_image": "images:alpine/3.20",
        }
        images = extract_all_images(infra)
        assert "images:ubuntu/24.04" in images
        assert "images:alpine/3.20" in images

    def test_machine_without_image_uses_global(self):
        """Machine without os_image inherits global default."""
        infra = _minimal_infra()
        images = extract_all_images(infra)
        assert "images:debian/13" in images

    def test_no_default_image_no_machine_image(self):
        """No images collected when neither global nor machine has one."""
        infra = _minimal_infra()
        del infra["global"]["default_os_image"]
        # Machine doesn't have os_image either
        images = extract_all_images(infra)
        assert images == []


# ── Nftables template: special bridge name variations ────────


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


# ── Nftables policy descriptions as comments ─────────────────


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
                {"name": "eth0", "bridge": "net-admin"},
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
                {"name": "eth0", "bridge": "net-admin"},
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
                {"name": "eth0", "bridge": "net-admin"},
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
                {"name": "eth0", "bridge": "net-admin"},
                {"name": "eth1", "bridge": "net-perso"},
            ],
            firewall_router_logging=True,
            firewall_router_log_prefix="FW",
        )
        assert "FW-DENY-ADMIN" in result
        assert "FW-DENY-PERSO" in result
        # Should NOT contain "NET-" in the prefix
        assert "FW-DENY-NET-" not in result

    def test_bridge_with_multiple_hyphens(self):
        """Bridge with multiple hyphens extracts correctly."""
        result = self._render(
            firewall_router_interfaces=[
                {"name": "eth0", "bridge": "net-admin"},
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


# ── Speaches: model/quantization combinations ────────────────


class TestSpeachesModelCombinations:
    """Test Speaches template with various model/quantization combos."""

    def _render(self, **kwargs):
        tmpl_dir = ROLES_DIR / "stt_server" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("speaches.service.j2")
        return template.render(ansible_managed="Ansible managed", **kwargs)

    def test_tiny_model_with_int8(self):
        """Tiny model with int8 quantization renders correctly."""
        result = self._render(
            stt_server_host="0.0.0.0",
            stt_server_port=8000,
            stt_server_model="tiny",
            stt_server_quantization="int8",
            stt_server_language="",
        )
        assert "WHISPER__MODEL=tiny" in result
        assert "WHISPER__COMPUTE_TYPE=int8" in result

    def test_large_v3_with_float16(self):
        """large-v3 model with float16 quantization renders correctly."""
        result = self._render(
            stt_server_host="0.0.0.0",
            stt_server_port=8000,
            stt_server_model="large-v3",
            stt_server_quantization="float16",
            stt_server_language="",
        )
        assert "WHISPER__MODEL=large-v3" in result
        assert "WHISPER__COMPUTE_TYPE=float16" in result

    def test_int8_float16_quantization(self):
        """int8_float16 quantization renders correctly."""
        result = self._render(
            stt_server_host="0.0.0.0",
            stt_server_port=8000,
            stt_server_model="medium",
            stt_server_quantization="int8_float16",
            stt_server_language="",
        )
        assert "WHISPER__COMPUTE_TYPE=int8_float16" in result

    def test_english_language(self):
        """English language code renders correctly."""
        result = self._render(
            stt_server_host="0.0.0.0",
            stt_server_port=8000,
            stt_server_model="small",
            stt_server_quantization="float16",
            stt_server_language="en",
        )
        assert "WHISPER__LANGUAGE=en" in result

    def test_japanese_language(self):
        """Japanese language code renders correctly."""
        result = self._render(
            stt_server_host="0.0.0.0",
            stt_server_port=8000,
            stt_server_model="large-v3-turbo",
            stt_server_quantization="float16",
            stt_server_language="ja",
        )
        assert "WHISPER__LANGUAGE=ja" in result

    def test_custom_port_in_exec_start(self):
        """Custom port appears in ExecStart line."""
        result = self._render(
            stt_server_host="0.0.0.0",
            stt_server_port=12345,
            stt_server_model="small",
            stt_server_quantization="float16",
            stt_server_language="",
        )
        assert "--port 12345" in result

    def test_systemd_unit_structure(self):
        """Speaches service has correct systemd structure."""
        result = self._render(
            stt_server_host="0.0.0.0",
            stt_server_port=8000,
            stt_server_model="large-v3-turbo",
            stt_server_quantization="float16",
            stt_server_language="",
        )
        assert "[Unit]" in result
        assert "[Service]" in result
        assert "[Install]" in result
        assert "WantedBy=multi-user.target" in result

    def test_managed_header_present(self):
        """Speaches template includes ansible_managed comment."""
        result = self._render(
            stt_server_host="0.0.0.0",
            stt_server_port=8000,
            stt_server_model="large-v3-turbo",
            stt_server_quantization="float16",
            stt_server_language="",
        )
        assert "Ansible managed" in result


# ── LobeChat additional edge cases ───────────────────────────


class TestLobechatAdditionalEdgeCases:
    """Additional edge case tests for LobeChat template."""

    def _render(self, **kwargs):
        tmpl_dir = ROLES_DIR / "lobechat" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("lobechat.service.j2")
        return template.render(**kwargs)

    def test_large_port_number(self):
        """LobeChat renders with a high port number."""
        result = self._render(
            lobechat_port=65535,
            lobechat_ollama_url="http://localhost:11434",
        )
        assert "PORT=65535" in result

    def test_port_one(self):
        """LobeChat renders with port 1."""
        result = self._render(
            lobechat_port=1,
            lobechat_ollama_url="http://localhost:11434",
        )
        assert "PORT=1" in result

    def test_ip_based_ollama_url(self):
        """LobeChat renders with an IP-based Ollama URL."""
        result = self._render(
            lobechat_port=3210,
            lobechat_ollama_url="http://192.168.1.100:11434",
        )
        assert "192.168.1.100:11434" in result

    def test_systemd_structure(self):
        """LobeChat template has correct systemd unit structure."""
        result = self._render(
            lobechat_port=3210,
            lobechat_ollama_url="http://localhost:11434",
        )
        assert "[Unit]" in result
        assert "[Service]" in result
        assert "[Install]" in result
        assert "WantedBy=multi-user.target" in result

    def test_restart_policy(self):
        """LobeChat has restart=always policy."""
        result = self._render(
            lobechat_port=3210,
            lobechat_ollama_url="http://localhost:11434",
        )
        assert "Restart=always" in result
        assert "RestartSec=5" in result

    def test_node_server_exec(self):
        """LobeChat uses node to run the server."""
        result = self._render(
            lobechat_port=3210,
            lobechat_ollama_url="http://localhost:11434",
        )
        assert "node .next/standalone/server.js" in result


# ── OpenCode additional edge cases ───────────────────────────


class TestOpencodeAdditionalEdgeCases:
    """Additional edge case tests for OpenCode templates."""

    def test_service_all_interfaces(self):
        """OpenCode service with 0.0.0.0 binding."""
        tmpl_dir = ROLES_DIR / "opencode_server" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("opencode.service.j2")
        result = template.render(
            opencode_server_port=8080,
            opencode_server_host="0.0.0.0",
            opencode_server_password="secret",
        )
        assert "--hostname 0.0.0.0" in result
        assert "--port 8080" in result

    def test_config_with_special_model_name(self):
        """OpenCode config with model name containing special chars."""
        tmpl_dir = ROLES_DIR / "opencode_server" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("opencode-config.json.j2")
        result = template.render(
            opencode_server_ollama_url="http://localhost:11434/v1",
            opencode_server_model="qwen2.5-coder:32b-instruct-q4_K_M",
        )
        data = json.loads(result)
        assert "qwen2.5-coder:32b-instruct-q4_K_M" in data["provider"]["ollama"]["models"]

    def test_config_with_different_url(self):
        """OpenCode config with non-localhost URL."""
        tmpl_dir = ROLES_DIR / "opencode_server" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("opencode-config.json.j2")
        result = template.render(
            opencode_server_ollama_url="http://10.100.10.10:11434/v1",
            opencode_server_model="codellama:7b",
        )
        data = json.loads(result)
        assert data["provider"]["ollama"]["options"]["baseURL"] == "http://10.100.10.10:11434/v1"

    def test_service_systemd_structure(self):
        """OpenCode service has correct systemd structure."""
        tmpl_dir = ROLES_DIR / "opencode_server" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("opencode.service.j2")
        result = template.render(
            opencode_server_port=5000,
            opencode_server_host="127.0.0.1",
            opencode_server_password="pass",
        )
        assert "[Unit]" in result
        assert "[Service]" in result
        assert "[Install]" in result
        assert "Restart=always" in result


# ── Claude settings additional edge cases ────────────────────


class TestClaudeSettingsAdditionalEdgeCases:
    """Additional edge case tests for Claude settings template."""

    def _render(self, **kwargs):
        tmpl_dir = ROLES_DIR / "dev_agent_runner" / "templates"
        env = _ansible_env(tmpl_dir)
        template = env.get_template("claude-settings.json.j2")
        return template.render(**kwargs)

    def test_teams_disabled(self):
        """Teams flag not present when disabled."""
        result = self._render(
            dev_agent_runner_enable_teams=False,
            dev_agent_runner_permissions_mode="default",
        )
        data = json.loads(result)
        assert "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS" not in data.get("env", {})

    def test_teams_enabled(self):
        """Teams flag is '1' when enabled."""
        result = self._render(
            dev_agent_runner_enable_teams=True,
            dev_agent_runner_permissions_mode="default",
        )
        data = json.loads(result)
        assert data["env"]["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] == "1"

    def test_valid_json_output(self):
        """Output is always valid JSON regardless of mode."""
        for mode in ["bypassPermissions", "default", "plan"]:
            for teams in [True, False]:
                result = self._render(
                    dev_agent_runner_enable_teams=teams,
                    dev_agent_runner_permissions_mode=mode,
                )
                data = json.loads(result)
                assert isinstance(data, dict)

    def test_plan_mode(self):
        """Plan mode renders correctly."""
        result = self._render(
            dev_agent_runner_enable_teams=True,
            dev_agent_runner_permissions_mode="plan",
        )
        data = json.loads(result)
        assert data["defaultMode"] == "plan"

    def test_permissions_structure(self):
        """Permissions has both allow and deny lists."""
        result = self._render(
            dev_agent_runner_enable_teams=True,
            dev_agent_runner_permissions_mode="bypassPermissions",
        )
        data = json.loads(result)
        assert "allow" in data["permissions"]
        assert "deny" in data["permissions"]
        assert isinstance(data["permissions"]["allow"], list)
        assert isinstance(data["permissions"]["deny"], list)

    def test_no_dangerous_bash_commands(self):
        """Deny list contains dangerous bash patterns."""
        result = self._render(
            dev_agent_runner_enable_teams=True,
            dev_agent_runner_permissions_mode="bypassPermissions",
        )
        data = json.loads(result)
        deny = data["permissions"]["deny"]
        # Check all three dangerous patterns
        assert len(deny) == 3
        assert any("rm -rf" in d for d in deny)
        assert any("curl" in d for d in deny)
        assert any("wget" in d for d in deny)

    def test_essential_tools_in_allow(self):
        """Essential tools (Edit, Read, Write) are in the allow list."""
        result = self._render(
            dev_agent_runner_enable_teams=True,
            dev_agent_runner_permissions_mode="default",
        )
        data = json.loads(result)
        allow = data["permissions"]["allow"]
        for tool in ["Edit", "MultiEdit", "Write", "Read", "Glob", "Grep"]:
            assert tool in allow


# ── PSOT: custom base subnet ────────────────────────────────


class TestPSOTCustomBaseSubnet:
    """Test generation with non-standard base_subnet values."""

    def test_192_168_base_subnet(self):
        """192.168 base subnet validates and generates correctly."""
        infra = _minimal_infra()
        infra["global"]["base_subnet"] = "192.168"
        infra["domains"]["test"]["machines"]["test-m1"]["ip"] = "192.168.1.10"
        errors = validate(infra)
        assert errors == []

    def test_172_16_base_subnet(self):
        """172.16 base subnet validates correctly."""
        infra = _minimal_infra()
        infra["global"]["base_subnet"] = "172.16"
        infra["domains"]["test"]["machines"]["test-m1"]["ip"] = "172.16.1.10"
        errors = validate(infra)
        assert errors == []

    def test_ip_wrong_subnet_with_custom_base(self):
        """IP not matching custom base subnet is rejected."""
        infra = _minimal_infra()
        infra["global"]["base_subnet"] = "192.168"
        # IP uses 10.100 but base is 192.168
        infra["domains"]["test"]["machines"]["test-m1"]["ip"] = "10.100.1.10"
        errors = validate(infra)
        assert any("not in subnet" in e for e in errors)


# ── PSOT: network policies in output ─────────────────────────


class TestPSOTNetworkPoliciesOutput:
    """Test that network policies appear in generated group_vars/all.yml."""

    def test_policies_in_all_yml(self):
        """Network policies are written to group_vars/all.yml."""
        infra = _minimal_infra()
        infra["network_policies"] = [{
            "description": "Test policy",
            "from": "test",
            "to": "test",
            "ports": [80],
            "protocol": "tcp",
        }]
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            all_yml = Path(d) / "group_vars" / "all.yml"
            content = all_yml.read_text()
            assert "network_policies" in content

    def test_no_policies_no_key_in_all_yml(self):
        """Without network policies, the key is absent from all.yml."""
        infra = _minimal_infra()
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            all_yml = Path(d) / "group_vars" / "all.yml"
            content = all_yml.read_text()
            assert "network_policies" not in content


# ── PSOT: inventory structure ────────────────────────────────


class TestPSOTInventoryStructure:
    """Test the structure of generated inventory files."""

    def test_host_without_ip_has_null_entry(self):
        """Host without IP generates a null entry in inventory."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"]["test-m1"] = {"type": "lxc"}
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            inv = Path(d) / "inventory" / "test.yml"
            content = inv.read_text()
            data = yaml.safe_load(content)
            host_entry = data["all"]["children"]["test"]["hosts"]["test-m1"]
            assert host_entry is None

    def test_host_with_ip_has_ansible_host(self):
        """Host with IP has ansible_host in inventory."""
        infra = _minimal_infra()
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            inv = Path(d) / "inventory" / "test.yml"
            data = yaml.safe_load(inv.read_text())
            assert data["all"]["children"]["test"]["hosts"]["test-m1"]["ansible_host"] == "10.100.1.10"

    def test_domain_appears_as_group(self):
        """Domain name is used as inventory group name."""
        infra = _minimal_infra()
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            inv = Path(d) / "inventory" / "test.yml"
            data = yaml.safe_load(inv.read_text())
            assert "test" in data["all"]["children"]


# ── PSOT: ephemeral edge cases ───────────────────────────────


class TestPSOTEphemeralEdgeCases:
    """Test ephemeral inheritance and override edge cases."""

    def test_all_machines_inherit_domain_true(self):
        """Machines inherit ephemeral=true from domain."""
        infra = _minimal_infra()
        infra["domains"]["test"]["ephemeral"] = True
        errors = validate(infra)
        assert errors == []
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            hv = Path(d) / "host_vars" / "test-m1.yml"
            data = yaml.safe_load(hv.read_text())
            assert data["instance_ephemeral"] is True

    def test_machine_overrides_domain_false(self):
        """Machine ephemeral=false overrides domain ephemeral=true."""
        infra = _minimal_infra()
        infra["domains"]["test"]["ephemeral"] = True
        infra["domains"]["test"]["machines"]["test-m1"]["ephemeral"] = False
        errors = validate(infra)
        assert errors == []
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            hv = Path(d) / "host_vars" / "test-m1.yml"
            data = yaml.safe_load(hv.read_text())
            assert data["instance_ephemeral"] is False

    def test_machine_overrides_domain_true(self):
        """Machine ephemeral=true overrides domain ephemeral=false (default)."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"]["test-m1"]["ephemeral"] = True
        errors = validate(infra)
        assert errors == []
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            hv = Path(d) / "host_vars" / "test-m1.yml"
            data = yaml.safe_load(hv.read_text())
            assert data["instance_ephemeral"] is True

    def test_ephemeral_in_group_vars(self):
        """Domain ephemeral flag appears in group_vars."""
        infra = _minimal_infra()
        infra["domains"]["test"]["ephemeral"] = True
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            gv = Path(d) / "group_vars" / "test.yml"
            data = yaml.safe_load(gv.read_text())
            assert data["domain_ephemeral"] is True


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
            firewall_router_interfaces=[{"name": "eth0", "bridge": "net-admin"}],
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
            firewall_router_interfaces=[{"name": "eth0", "bridge": "net-admin"}],
            firewall_router_logging=False,
            firewall_router_log_prefix="FW",
        )
        lines = result.splitlines()
        input_idx = next(i for i, ln in enumerate(lines) if "chain input" in ln)
        assert "policy drop" in lines[input_idx + 1]

    def test_output_policy_accept(self):
        """Output chain has default policy accept."""
        result = self._render(
            firewall_router_interfaces=[{"name": "eth0", "bridge": "net-admin"}],
            firewall_router_logging=False,
            firewall_router_log_prefix="FW",
        )
        lines = result.splitlines()
        output_idx = next(i for i, ln in enumerate(lines) if "chain output" in ln)
        assert "policy accept" in lines[output_idx + 1]

    def test_atomic_replacement_header(self):
        """Firewall router template uses atomic table replacement."""
        result = self._render(
            firewall_router_interfaces=[{"name": "eth0", "bridge": "net-admin"}],
            firewall_router_logging=False,
            firewall_router_log_prefix="FW",
        )
        assert "table inet anklume" in result
        assert "delete table inet anklume" in result


# ── YAML internal edge cases ────────────────────────────────


class TestYamlInternalEdgeCases:
    """Test _yaml() with edge case inputs."""

    def test_empty_list(self):
        """_yaml renders empty list correctly."""
        result = _yaml({"items": []})
        data = yaml.safe_load(result)
        assert data["items"] == []

    def test_nested_none(self):
        """_yaml handles nested None values."""
        result = _yaml({"outer": {"inner": None}})
        assert "null" not in result.lower()
        data = yaml.safe_load(result)
        assert data["outer"]["inner"] is None or data["outer"]["inner"] == ""

    def test_long_string(self):
        """_yaml handles long string values."""
        long_val = "x" * 200
        result = _yaml({"key": long_val})
        data = yaml.safe_load(result)
        assert data["key"] == long_val

    def test_special_yaml_chars(self):
        """_yaml handles values with special YAML characters."""
        result = _yaml({"key": "value: with colon"})
        data = yaml.safe_load(result)
        assert data["key"] == "value: with colon"

    def test_integer_values(self):
        """_yaml preserves integer values."""
        result = _yaml({"port": 8080, "count": 0})
        data = yaml.safe_load(result)
        assert data["port"] == 8080
        assert data["count"] == 0

    def test_float_values(self):
        """_yaml preserves float values."""
        result = _yaml({"ratio": 3.14})
        data = yaml.safe_load(result)
        assert abs(data["ratio"] - 3.14) < 0.001

    def test_roundtrip_consistency(self):
        """_yaml output can be parsed back to the same structure."""
        original = {
            "name": "test",
            "count": 42,
            "nested": {"a": 1, "b": 2},
            "items": ["x", "y", "z"],
        }
        result = _yaml(original)
        data = yaml.safe_load(result)
        assert data == original


# ── PSOT: generate output file paths ────────────────────────


class TestPSOTGenerateOutputPaths:
    """Test that generate() creates the correct set of files."""

    def test_single_domain_creates_expected_files(self):
        """Single domain creates inventory, group_vars, host_vars."""
        infra = _minimal_infra()
        with tempfile.TemporaryDirectory() as d:
            files = generate(infra, d)
            # Should have: all.yml + inventory/test.yml + group_vars/test.yml + host_vars/test-m1.yml
            assert len(files) == 4
            paths = [str(f) for f in files]
            assert any("all.yml" in p for p in paths)
            assert any("inventory" in p and "test.yml" in p for p in paths)
            assert any("group_vars" in p and "test.yml" in p for p in paths)
            assert any("host_vars" in p and "test-m1.yml" in p for p in paths)

    def test_two_domains_create_expected_files(self):
        """Two domains create files for both."""
        infra = _minimal_infra()
        infra["domains"]["other"] = {
            "subnet_id": 2,
            "machines": {
                "other-m1": {"type": "lxc", "ip": "10.100.2.10"},
            },
        }
        with tempfile.TemporaryDirectory() as d:
            files = generate(infra, d)
            # all.yml + 2 inventory + 2 group_vars + 2 host_vars = 7
            assert len(files) == 7

    def test_domain_with_two_machines_creates_two_host_vars(self):
        """Domain with two machines creates two host_vars files."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"]["test-m2"] = {
            "type": "lxc", "ip": "10.100.1.20",
        }
        with tempfile.TemporaryDirectory() as d:
            files = generate(infra, d)
            host_vars = [f for f in files if "host_vars" in str(f)]
            assert len(host_vars) == 2


# ── PSOT: host_vars content validation ──────────────────────


class TestPSOTHostVarsContent:
    """Test the content of generated host_vars files."""

    def test_instance_type_lxc(self):
        """LXC type is written to host_vars."""
        infra = _minimal_infra()
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            hv = Path(d) / "host_vars" / "test-m1.yml"
            data = yaml.safe_load(hv.read_text())
            assert data["instance_type"] == "lxc"

    def test_instance_type_vm(self):
        """VM type is written to host_vars."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"]["test-m1"]["type"] = "vm"
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            hv = Path(d) / "host_vars" / "test-m1.yml"
            data = yaml.safe_load(hv.read_text())
            assert data["instance_type"] == "vm"

    def test_instance_domain(self):
        """Instance domain is written to host_vars."""
        infra = _minimal_infra()
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            hv = Path(d) / "host_vars" / "test-m1.yml"
            data = yaml.safe_load(hv.read_text())
            assert data["instance_domain"] == "test"

    def test_instance_ip(self):
        """Instance IP is written to host_vars."""
        infra = _minimal_infra()
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            hv = Path(d) / "host_vars" / "test-m1.yml"
            data = yaml.safe_load(hv.read_text())
            assert data["instance_ip"] == "10.100.1.10"

    def test_instance_os_image_from_global(self):
        """Instance os_image falls back to global default."""
        infra = _minimal_infra()
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            hv = Path(d) / "host_vars" / "test-m1.yml"
            data = yaml.safe_load(hv.read_text())
            assert data["instance_os_image"] == "images:debian/13"

    def test_instance_os_image_override(self):
        """Machine os_image overrides global default."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"]["test-m1"]["os_image"] = "images:ubuntu/24.04"
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            hv = Path(d) / "host_vars" / "test-m1.yml"
            data = yaml.safe_load(hv.read_text())
            assert data["instance_os_image"] == "images:ubuntu/24.04"

    def test_gpu_flag_in_host_vars(self):
        """GPU flag is written to host_vars."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"]["test-m1"]["gpu"] = True
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            hv = Path(d) / "host_vars" / "test-m1.yml"
            data = yaml.safe_load(hv.read_text())
            assert data["instance_gpu"] is True

    def test_config_in_host_vars(self):
        """Instance config is written to host_vars."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"]["test-m1"]["config"] = {
            "limits.cpu": "4", "limits.memory": "8GiB",
        }
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            hv = Path(d) / "host_vars" / "test-m1.yml"
            data = yaml.safe_load(hv.read_text())
            assert data["instance_config"]["limits.cpu"] == "4"
            assert data["instance_config"]["limits.memory"] == "8GiB"

    def test_roles_in_host_vars(self):
        """Instance roles are written to host_vars."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"]["test-m1"]["roles"] = ["base_system", "ollama_server"]
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            hv = Path(d) / "host_vars" / "test-m1.yml"
            data = yaml.safe_load(hv.read_text())
            assert data["instance_roles"] == ["base_system", "ollama_server"]


# ── PSOT: group_vars content validation ─────────────────────


class TestPSOTGroupVarsContent:
    """Test the content of generated group_vars files."""

    def test_domain_name_in_group_vars(self):
        """Domain name is written to group_vars."""
        infra = _minimal_infra()
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            gv = Path(d) / "group_vars" / "test.yml"
            data = yaml.safe_load(gv.read_text())
            assert data["domain_name"] == "test"

    def test_network_info_in_group_vars(self):
        """Network bridge info is written to group_vars."""
        infra = _minimal_infra()
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            gv = Path(d) / "group_vars" / "test.yml"
            data = yaml.safe_load(gv.read_text())
            assert data["incus_network"]["name"] == "net-test"
            assert data["incus_network"]["subnet"] == "10.100.1.0/24"
            assert data["incus_network"]["gateway"] == "10.100.1.254"

    def test_subnet_id_in_group_vars(self):
        """subnet_id is written to group_vars."""
        infra = _minimal_infra()
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            gv = Path(d) / "group_vars" / "test.yml"
            data = yaml.safe_load(gv.read_text())
            assert data["subnet_id"] == 1

    def test_profiles_in_group_vars(self):
        """Domain profiles are written to group_vars."""
        infra = _minimal_infra()
        infra["domains"]["test"]["profiles"] = {
            "nesting": {"config": {"security.nesting": "true"}},
        }
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            gv = Path(d) / "group_vars" / "test.yml"
            data = yaml.safe_load(gv.read_text())
            assert "incus_profiles" in data
            assert "nesting" in data["incus_profiles"]

    def test_project_name_in_all_yml(self):
        """project_name is written to group_vars/all.yml."""
        infra = _minimal_infra()
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            all_yml = Path(d) / "group_vars" / "all.yml"
            data = yaml.safe_load(all_yml.read_text())
            assert data["project_name"] == "edge-test"


# ── PSOT: orphan detection edge cases ───────────────────────


class TestPSOTOrphanDetection:
    """Test orphan detection with various file configurations."""

    def test_no_orphans_when_files_match(self):
        """No orphans when generated files match infra."""
        infra = _minimal_infra()
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            orphans = detect_orphans(infra, d)
            assert len(orphans) == 0

    def test_extra_inventory_file_is_orphan(self):
        """Extra inventory file not in infra is detected as orphan."""
        infra = _minimal_infra()
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            # Add an extra file
            extra = Path(d) / "inventory" / "deleted-domain.yml"
            extra.write_text("---\n# orphan\n")
            orphans = detect_orphans(infra, d)
            assert len(orphans) == 1
            assert "deleted-domain" in str(orphans[0][0])

    def test_extra_host_vars_file_is_orphan(self):
        """Extra host_vars file not in infra is detected as orphan."""
        infra = _minimal_infra()
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            extra = Path(d) / "host_vars" / "removed-machine.yml"
            extra.write_text("---\ninstance_ephemeral: true\n")
            orphans = detect_orphans(infra, d)
            assert len(orphans) >= 1
            assert any("removed-machine" in str(o[0]) for o in orphans)

    def test_orphan_with_ephemeral_false_is_protected(self):
        """Orphan file with instance_ephemeral: false is marked protected."""
        infra = _minimal_infra()
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            extra = Path(d) / "host_vars" / "protected-machine.yml"
            extra.write_text("---\ninstance_ephemeral: false\n")
            orphans = detect_orphans(infra, d)
            protected_orphans = [o for o in orphans if "protected-machine" in str(o[0])]
            assert len(protected_orphans) == 1
            assert protected_orphans[0][1] is True  # is_protected

    def test_orphan_with_ephemeral_true_not_protected(self):
        """Orphan file with instance_ephemeral: true is not protected."""
        infra = _minimal_infra()
        with tempfile.TemporaryDirectory() as d:
            generate(infra, d)
            extra = Path(d) / "host_vars" / "temp-machine.yml"
            extra.write_text("---\ninstance_ephemeral: true\n")
            orphans = detect_orphans(infra, d)
            temp_orphans = [o for o in orphans if "temp-machine" in str(o[0])]
            assert len(temp_orphans) == 1
            assert temp_orphans[0][1] is False  # not protected


# ── PSOT: enrich_infra edge cases ───────────────────────────


class TestPSOTEnrichEdgeCases:
    """Test enrich_infra with various configurations."""

    def test_enrich_firewall_vm_creates_sys_firewall(self):
        """enrich_infra creates sys-firewall when firewall_mode=vm."""
        infra = _minimal_infra()
        infra["global"]["firewall_mode"] = "vm"
        infra["domains"]["admin"] = {
            "subnet_id": 0,
            "machines": {
                "admin-ctrl": {"type": "lxc", "ip": "10.100.0.10"},
            },
        }
        enrich_infra(infra)
        assert "sys-firewall" in infra["domains"]["admin"]["machines"]
        fw = infra["domains"]["admin"]["machines"]["sys-firewall"]
        assert fw["type"] == "vm"
        assert fw["ip"] == "10.100.0.253"

    def test_enrich_does_not_overwrite_user_sys_firewall(self):
        """enrich_infra does not overwrite user-defined sys-firewall."""
        infra = _minimal_infra()
        infra["global"]["firewall_mode"] = "vm"
        infra["domains"]["admin"] = {
            "subnet_id": 0,
            "machines": {
                "admin-ctrl": {"type": "lxc", "ip": "10.100.0.10"},
                "sys-firewall": {
                    "type": "vm",
                    "ip": "10.100.0.200",
                    "config": {"limits.cpu": "8"},
                },
            },
        }
        enrich_infra(infra)
        fw = infra["domains"]["admin"]["machines"]["sys-firewall"]
        assert fw["ip"] == "10.100.0.200"  # User's IP preserved
        assert fw["config"]["limits.cpu"] == "8"  # User's config preserved

    def test_enrich_ai_access_creates_policy(self):
        """enrich_infra creates AI access policy in exclusive mode."""
        infra = _minimal_infra()
        infra["global"]["ai_access_policy"] = "exclusive"
        infra["global"]["ai_access_default"] = "test"
        infra["domains"]["ai-tools"] = {
            "subnet_id": 10,
            "machines": {
                "ai-ollama": {"type": "lxc", "ip": "10.100.10.10"},
            },
        }
        enrich_infra(infra)
        policies = infra.get("network_policies", [])
        assert len(policies) == 1
        assert policies[0]["to"] == "ai-tools"
        assert policies[0]["from"] == "test"

    def test_enrich_ai_access_does_not_duplicate(self):
        """enrich_infra does not add a second AI policy if one exists."""
        infra = _minimal_infra()
        infra["global"]["ai_access_policy"] = "exclusive"
        infra["global"]["ai_access_default"] = "test"
        infra["domains"]["ai-tools"] = {
            "subnet_id": 10,
            "machines": {"ai-ollama": {"type": "lxc", "ip": "10.100.10.10"}},
        }
        infra["network_policies"] = [{
            "description": "Existing",
            "from": "test",
            "to": "ai-tools",
            "ports": "all",
            "bidirectional": True,
        }]
        enrich_infra(infra)
        ai_policies = [p for p in infra["network_policies"] if p.get("to") == "ai-tools"]
        assert len(ai_policies) == 1

    def test_enrich_host_mode_does_nothing(self):
        """enrich_infra does nothing when firewall_mode=host."""
        infra = _minimal_infra()
        infra["global"]["firewall_mode"] = "host"
        original_machines = dict(infra["domains"]["test"]["machines"])
        enrich_infra(infra)
        assert infra["domains"]["test"]["machines"] == original_machines

    def test_enrich_open_ai_policy_does_nothing(self):
        """enrich_infra does nothing when ai_access_policy=open."""
        infra = _minimal_infra()
        infra["global"]["ai_access_policy"] = "open"
        enrich_infra(infra)
        assert "network_policies" not in infra


# ── PSOT: validation error messages ─────────────────────────


class TestPSOTValidationErrors:
    """Test that validation produces correct and clear error messages."""

    def test_missing_project_name(self):
        """Missing project_name produces clear error."""
        infra = _minimal_infra()
        del infra["project_name"]
        errors = validate(infra)
        assert any("project_name" in e for e in errors)

    def test_missing_global(self):
        """Missing global section produces clear error."""
        infra = _minimal_infra()
        del infra["global"]
        errors = validate(infra)
        assert any("global" in e for e in errors)

    def test_missing_domains(self):
        """Missing domains section produces clear error."""
        infra = _minimal_infra()
        del infra["domains"]
        errors = validate(infra)
        assert any("domains" in e for e in errors)

    def test_duplicate_machine_name(self):
        """Duplicate machine name across domains produces error."""
        infra = _minimal_infra()
        infra["domains"]["other"] = {
            "subnet_id": 2,
            "machines": {
                "test-m1": {"type": "lxc", "ip": "10.100.2.10"},  # Same name as in test domain
            },
        }
        errors = validate(infra)
        assert any("duplicate" in e.lower() for e in errors)

    def test_duplicate_ip(self):
        """Duplicate IP across domains produces error."""
        infra = _minimal_infra()
        infra["domains"]["other"] = {
            "subnet_id": 2,
            "machines": {
                "other-m1": {"type": "lxc", "ip": "10.100.1.10"},  # Same IP as test-m1
            },
        }
        errors = validate(infra)
        assert any("IP" in e and "already used" in e for e in errors)

    def test_duplicate_subnet_id(self):
        """Duplicate subnet_id produces error."""
        infra = _minimal_infra()
        infra["domains"]["other"] = {
            "subnet_id": 1,  # Same as test domain
            "machines": {
                "other-m1": {"type": "lxc", "ip": "10.100.1.20"},
            },
        }
        errors = validate(infra)
        assert any("subnet_id 1 already used" in e for e in errors)

    def test_invalid_type(self):
        """Invalid machine type produces error."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"]["test-m1"]["type"] = "docker"
        errors = validate(infra)
        assert any("type must be 'lxc' or 'vm'" in e for e in errors)

    def test_invalid_gpu_policy(self):
        """Invalid gpu_policy produces error."""
        infra = _minimal_infra()
        infra["global"]["gpu_policy"] = "invalid"
        errors = validate(infra)
        assert any("gpu_policy must be" in e for e in errors)

    def test_invalid_firewall_mode(self):
        """Invalid firewall_mode produces error."""
        infra = _minimal_infra()
        infra["global"]["firewall_mode"] = "docker"
        errors = validate(infra)
        assert any("firewall_mode must be" in e for e in errors)

    def test_ephemeral_non_boolean_domain(self):
        """Non-boolean domain ephemeral produces error."""
        infra = _minimal_infra()
        infra["domains"]["test"]["ephemeral"] = "yes"
        errors = validate(infra)
        assert any("ephemeral must be a boolean" in e for e in errors)

    def test_ephemeral_non_boolean_machine(self):
        """Non-boolean machine ephemeral produces error."""
        infra = _minimal_infra()
        infra["domains"]["test"]["machines"]["test-m1"]["ephemeral"] = "no"
        errors = validate(infra)
        assert any("ephemeral must be a boolean" in e for e in errors)


# ── PSOT: network policy validation ─────────────────────────


class TestPSOTNetworkPolicyValidation:
    """Test network policy validation edge cases."""

    def test_valid_policy_no_error(self):
        """Valid network policy produces no error."""
        infra = _minimal_infra()
        infra["network_policies"] = [{
            "description": "Valid",
            "from": "test",
            "to": "test",
            "ports": [80],
            "protocol": "tcp",
        }]
        errors = validate(infra)
        assert errors == []

    def test_policy_from_host_valid(self):
        """Policy with from=host is valid."""
        infra = _minimal_infra()
        infra["network_policies"] = [{
            "from": "host",
            "to": "test",
            "ports": [80],
            "protocol": "tcp",
        }]
        errors = validate(infra)
        assert errors == []

    def test_policy_unknown_from_rejected(self):
        """Policy with unknown 'from' domain is rejected."""
        infra = _minimal_infra()
        infra["network_policies"] = [{
            "from": "nonexistent",
            "to": "test",
            "ports": [80],
            "protocol": "tcp",
        }]
        errors = validate(infra)
        assert any("nonexistent" in e for e in errors)

    def test_policy_unknown_to_rejected(self):
        """Policy with unknown 'to' domain is rejected."""
        infra = _minimal_infra()
        infra["network_policies"] = [{
            "from": "test",
            "to": "nonexistent",
            "ports": [80],
            "protocol": "tcp",
        }]
        errors = validate(infra)
        assert any("nonexistent" in e for e in errors)

    def test_policy_invalid_port_zero(self):
        """Port 0 in policy is rejected."""
        infra = _minimal_infra()
        infra["network_policies"] = [{
            "from": "test",
            "to": "test",
            "ports": [0],
            "protocol": "tcp",
        }]
        errors = validate(infra)
        assert any("invalid port" in e for e in errors)

    def test_policy_invalid_port_too_high(self):
        """Port 65536 in policy is rejected."""
        infra = _minimal_infra()
        infra["network_policies"] = [{
            "from": "test",
            "to": "test",
            "ports": [65536],
            "protocol": "tcp",
        }]
        errors = validate(infra)
        assert any("invalid port" in e for e in errors)

    def test_policy_invalid_protocol(self):
        """Invalid protocol in policy is rejected."""
        infra = _minimal_infra()
        infra["network_policies"] = [{
            "from": "test",
            "to": "test",
            "ports": [80],
            "protocol": "icmp",
        }]
        errors = validate(infra)
        assert any("protocol must be 'tcp' or 'udp'" in e for e in errors)

    def test_policy_ports_all_is_valid(self):
        """Policy with ports='all' is valid."""
        infra = _minimal_infra()
        infra["network_policies"] = [{
            "from": "test",
            "to": "test",
            "ports": "all",
        }]
        errors = validate(infra)
        assert errors == []

    def test_policy_from_machine_name_valid(self):
        """Policy with from=machine_name is valid."""
        infra = _minimal_infra()
        infra["network_policies"] = [{
            "from": "test-m1",
            "to": "test",
            "ports": [80],
            "protocol": "tcp",
        }]
        errors = validate(infra)
        assert errors == []


# ── PSOT: AI access policy validation ───────────────────────


class TestPSOTAiAccessValidation:
    """Test AI access policy validation edge cases."""

    def test_exclusive_without_default_rejected(self):
        """exclusive without ai_access_default is rejected."""
        infra = _minimal_infra()
        infra["global"]["ai_access_policy"] = "exclusive"
        infra["domains"]["ai-tools"] = {
            "subnet_id": 10,
            "machines": {"ai-m": {"type": "lxc", "ip": "10.100.10.10"}},
        }
        errors = validate(infra)
        assert any("ai_access_default is required" in e for e in errors)

    def test_exclusive_default_is_ai_tools_rejected(self):
        """exclusive with ai_access_default=ai-tools is rejected."""
        infra = _minimal_infra()
        infra["global"]["ai_access_policy"] = "exclusive"
        infra["global"]["ai_access_default"] = "ai-tools"
        infra["domains"]["ai-tools"] = {
            "subnet_id": 10,
            "machines": {"ai-m": {"type": "lxc", "ip": "10.100.10.10"}},
        }
        errors = validate(infra)
        assert any("cannot be 'ai-tools'" in e for e in errors)

    def test_exclusive_without_ai_tools_domain_rejected(self):
        """exclusive without ai-tools domain is rejected."""
        infra = _minimal_infra()
        infra["global"]["ai_access_policy"] = "exclusive"
        infra["global"]["ai_access_default"] = "test"
        errors = validate(infra)
        assert any("no 'ai-tools' domain exists" in e for e in errors)

    def test_exclusive_valid_setup(self):
        """Valid exclusive setup passes validation."""
        infra = _minimal_infra()
        infra["global"]["ai_access_policy"] = "exclusive"
        infra["global"]["ai_access_default"] = "test"
        infra["domains"]["ai-tools"] = {
            "subnet_id": 10,
            "machines": {"ai-m": {"type": "lxc", "ip": "10.100.10.10"}},
        }
        errors = validate(infra)
        assert errors == []

    def test_open_policy_no_constraints(self):
        """open policy imposes no additional constraints."""
        infra = _minimal_infra()
        infra["global"]["ai_access_policy"] = "open"
        errors = validate(infra)
        assert errors == []

    def test_invalid_ai_policy_rejected(self):
        """Invalid ai_access_policy is rejected."""
        infra = _minimal_infra()
        infra["global"]["ai_access_policy"] = "custom"
        errors = validate(infra)
        assert any("ai_access_policy must be" in e for e in errors)


# ── PSOT: managed block content ─────────────────────────────


class TestPSOTManagedBlockContent:
    """Test _managed_block formatting."""

    def test_managed_block_has_begin_end(self):
        """Managed block contains BEGIN and END markers."""
        block = _managed_block("key: value\n")
        assert MANAGED_BEGIN in block
        assert MANAGED_END in block

    def test_managed_block_has_notice(self):
        """Managed block contains the do-not-edit notice."""
        block = _managed_block("key: value\n")
        assert "Do not edit this section" in block

    def test_managed_block_content_inside(self):
        """Managed block contains the provided YAML content."""
        block = _managed_block("my_key: my_value\n")
        assert "my_key: my_value" in block

    def test_managed_block_trailing_newline_stripped(self):
        """Managed block strips trailing whitespace from content."""
        block = _managed_block("key: value\n\n\n")
        # Should not have multiple newlines before END marker
        lines = block.split("\n")
        end_idx = next(i for i, ln in enumerate(lines) if MANAGED_END in ln)
        # Line before END should have content (not be blank)
        assert lines[end_idx - 1].strip() != ""


# ── PSOT: GPU policy edge cases ─────────────────────────────


class TestPSOTGPUPolicyEdgeCases:
    """Test GPU policy validation edge cases."""

    def test_zero_gpu_exclusive_ok(self):
        """No GPU instances in exclusive mode is fine."""
        infra = _minimal_infra()
        infra["global"]["gpu_policy"] = "exclusive"
        errors = validate(infra)
        assert errors == []

    def test_one_gpu_exclusive_ok(self):
        """One GPU instance in exclusive mode is fine."""
        infra = _minimal_infra()
        infra["global"]["gpu_policy"] = "exclusive"
        infra["domains"]["test"]["machines"]["test-m1"]["gpu"] = True
        errors = validate(infra)
        assert errors == []

    def test_two_gpu_exclusive_rejected(self):
        """Two GPU instances in exclusive mode are rejected."""
        infra = _minimal_infra()
        infra["global"]["gpu_policy"] = "exclusive"
        infra["domains"]["test"]["machines"]["test-m1"]["gpu"] = True
        infra["domains"]["test"]["machines"]["test-m2"] = {
            "type": "lxc", "ip": "10.100.1.20", "gpu": True,
        }
        errors = validate(infra)
        assert any("GPU policy is 'exclusive'" in e for e in errors)

    def test_two_gpu_shared_ok(self):
        """Two GPU instances in shared mode pass validation."""
        infra = _minimal_infra()
        infra["global"]["gpu_policy"] = "shared"
        infra["domains"]["test"]["machines"]["test-m1"]["gpu"] = True
        infra["domains"]["test"]["machines"]["test-m2"] = {
            "type": "lxc", "ip": "10.100.1.20", "gpu": True,
        }
        errors = validate(infra)
        assert errors == []
