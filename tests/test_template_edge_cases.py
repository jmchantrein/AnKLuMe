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
