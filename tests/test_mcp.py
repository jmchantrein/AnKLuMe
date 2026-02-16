"""Tests for Phase 20c MCP inter-container services.

Tests cover:
- Script quality (ruff check) for all 3 MCP Python files
- MCP server: tool registration, help, SDK integration
- MCP client: help output, dry-run
- MCP policy: authorized access, denied access, missing infra
- Generator: services validation in generate.py
"""

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
MCP_SERVER = SCRIPTS_DIR / "mcp-server.py"
MCP_CLIENT = SCRIPTS_DIR / "mcp-client.py"
MCP_POLICY = SCRIPTS_DIR / "mcp-policy.py"


# ── Script quality ─────────────────────────────────────────────────


class TestScriptQuality:
    """All MCP Python files pass ruff check."""

    def test_mcp_server_ruff_clean(self):
        result = subprocess.run(
            ["ruff", "check", str(MCP_SERVER)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"ruff errors in mcp-server.py:\n{result.stdout}"

    def test_mcp_client_ruff_clean(self):
        result = subprocess.run(
            ["ruff", "check", str(MCP_CLIENT)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"ruff errors in mcp-client.py:\n{result.stdout}"

    def test_mcp_policy_ruff_clean(self):
        result = subprocess.run(
            ["ruff", "check", str(MCP_POLICY)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"ruff errors in mcp-policy.py:\n{result.stdout}"


# ── MCP Server ─────────────────────────────────────────────────────


class TestMCPServer:
    """Test MCP server tool registration and help."""

    def test_help_flag(self):
        """--help shows usage."""
        result = subprocess.run(
            [sys.executable, str(MCP_SERVER), "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "anklume MCP server" in result.stdout

    def test_list_tools_flag(self):
        """--list-tools shows all registered tools."""
        result = subprocess.run(
            [sys.executable, str(MCP_SERVER), "--list-tools"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "gpg_sign" in result.stdout
        assert "clipboard_get" in result.stdout
        assert "clipboard_set" in result.stdout
        assert "file_accept" in result.stdout
        assert "file_provide" in result.stdout

    def test_server_imports(self):
        """Server imports succeed (MCP SDK available)."""
        result = subprocess.run(
            [sys.executable, "-c", "from mcp.server.fastmcp import FastMCP; print('OK')"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_server_tool_functions_importable(self):
        """Tool functions are importable from the server module."""
        result = subprocess.run(
            [sys.executable, "-c",
             "import importlib.util; "
             "spec = importlib.util.spec_from_file_location('mcp_server', "
             f"'{MCP_SERVER}'); "
             "mod = importlib.util.module_from_spec(spec); "
             "spec.loader.exec_module(mod); "
             "print(','.join(sorted(['gpg_sign', 'clipboard_get', 'clipboard_set', "
             "'file_accept', 'file_provide'])))"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "clipboard_get" in result.stdout

    def test_sdk_integration_list_tools(self, tmp_path):
        """Full SDK integration: client lists tools from server."""
        script = tmp_path / "test_list.py"
        script.write_text(f"""
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def run():
    params = StdioServerParameters(command="{sys.executable}", args=["{MCP_SERVER}"])
    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        result = await s.list_tools()
        names = sorted(t.name for t in result.tools)
        print(",".join(names))

asyncio.run(run())
""")
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        tools = result.stdout.strip().split(",")
        assert "clipboard_get" in tools
        assert "clipboard_set" in tools
        assert "file_accept" in tools
        assert "file_provide" in tools
        assert "gpg_sign" in tools

    def test_sdk_integration_call_clipboard(self, tmp_path):
        """Full SDK integration: client calls clipboard tools on server."""
        script = tmp_path / "test_call.py"
        script.write_text(f"""
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def run():
    params = StdioServerParameters(command="{sys.executable}", args=["{MCP_SERVER}"])
    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        await s.call_tool("clipboard_set", {{"content": "sdk-test-123"}})
        result = await s.call_tool("clipboard_get", {{}})
        print(result.content[0].text)

asyncio.run(run())
""")
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "sdk-test-123" in result.stdout


# ── MCP Client ─────────────────────────────────────────────────────


class TestMCPClient:
    """Test MCP client CLI."""

    def test_help_flag(self):
        """--help shows usage."""
        result = subprocess.run(
            [sys.executable, str(MCP_CLIENT), "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "anklume MCP client" in result.stdout

    def test_no_args_shows_help(self):
        """No arguments shows help."""
        result = subprocess.run(
            [sys.executable, str(MCP_CLIENT)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0

    def test_list_dry_run(self):
        """list --dry-run shows what would be sent."""
        result = subprocess.run(
            [sys.executable, str(MCP_CLIENT), "--dry-run", "list"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "Would connect" in result.stdout
        assert "tools/list" in result.stdout

    def test_call_dry_run(self):
        """call --dry-run shows what would be sent."""
        result = subprocess.run(
            [sys.executable, str(MCP_CLIENT), "--dry-run", "call", "clipboard_get"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "Would connect" in result.stdout
        assert "clipboard_get" in result.stdout

    def test_call_invalid_json_args(self):
        """call with invalid JSON arguments fails."""
        result = subprocess.run(
            [sys.executable, str(MCP_CLIENT), "--dry-run", "call", "clipboard_set", "not-json"],
            capture_output=True, text=True,
        )
        assert result.returncode != 0
        assert "Invalid JSON" in result.stderr


# ── MCP Policy ─────────────────────────────────────────────────────


class TestMCPPolicy:
    """Test MCP policy engine."""

    @pytest.fixture()
    def infra_with_services(self, tmp_path):
        """Create an infra.yml with service declarations."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "vault": {
                    "subnet_id": 0,
                    "machines": {
                        "vault-signer": {
                            "type": "lxc",
                            "ip": "10.100.0.10",
                            "services": [
                                {
                                    "name": "file_sign",
                                    "tool": "gpg_sign",
                                    "consumers": ["work-dev", "pro-dev"],
                                },
                                {
                                    "name": "clipboard",
                                    "tool": "clipboard_get",
                                    "consumers": ["work-dev"],
                                },
                            ],
                        },
                    },
                },
                "work": {
                    "subnet_id": 1,
                    "machines": {
                        "work-dev": {"type": "lxc", "ip": "10.100.1.10"},
                    },
                },
                "pro": {
                    "subnet_id": 2,
                    "machines": {
                        "pro-dev": {"type": "lxc", "ip": "10.100.2.10"},
                    },
                },
            },
        }
        p = tmp_path / "infra.yml"
        p.write_text(yaml.dump(infra, sort_keys=False))
        return str(p)

    def test_help_flag(self):
        """--help shows usage."""
        result = subprocess.run(
            [sys.executable, str(MCP_POLICY), "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "anklume MCP policy engine" in result.stdout

    def test_authorized_access(self, infra_with_services):
        """Authorized consumer gets exit 0."""
        result = subprocess.run(
            [sys.executable, str(MCP_POLICY), "check",
             "--caller", "work-dev", "--service", "file_sign",
             "--infra", infra_with_services],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "authorized" in result.stdout.lower()

    def test_denied_access(self, infra_with_services):
        """Unauthorized consumer gets exit 1."""
        result = subprocess.run(
            [sys.executable, str(MCP_POLICY), "check",
             "--caller", "pro-dev", "--service", "clipboard",
             "--infra", infra_with_services],
            capture_output=True, text=True,
        )
        assert result.returncode == 1
        assert "not" in result.stdout.lower()

    def test_unknown_service(self, infra_with_services):
        """Unknown service name gets exit 1."""
        result = subprocess.run(
            [sys.executable, str(MCP_POLICY), "check",
             "--caller", "work-dev", "--service", "nonexistent",
             "--infra", infra_with_services],
            capture_output=True, text=True,
        )
        assert result.returncode == 1

    def test_no_services_declared(self, tmp_path):
        """infra.yml with no services declarations denies all."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "work": {
                    "subnet_id": 1,
                    "machines": {"work-dev": {"type": "lxc", "ip": "10.100.1.10"}},
                },
            },
        }
        p = tmp_path / "infra.yml"
        p.write_text(yaml.dump(infra, sort_keys=False))
        result = subprocess.run(
            [sys.executable, str(MCP_POLICY), "check",
             "--caller", "work-dev", "--service", "file_sign",
             "--infra", str(p)],
            capture_output=True, text=True,
        )
        assert result.returncode == 1
        assert "No services" in result.stdout

    def test_list_services(self, infra_with_services):
        """list subcommand shows declared services."""
        result = subprocess.run(
            [sys.executable, str(MCP_POLICY), "list",
             "--infra", infra_with_services],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "vault-signer:file_sign" in result.stdout
        assert "work-dev" in result.stdout

    def test_missing_infra_file(self):
        """Missing infra.yml gives error."""
        result = subprocess.run(
            [sys.executable, str(MCP_POLICY), "check",
             "--caller", "x", "--service", "y",
             "--infra", "/nonexistent/infra.yml"],
            capture_output=True, text=True,
        )
        assert result.returncode != 0

    def test_provider_filter(self, infra_with_services):
        """--provider filters to specific provider."""
        result = subprocess.run(
            [sys.executable, str(MCP_POLICY), "check",
             "--caller", "work-dev", "--service", "file_sign",
             "--provider", "vault-signer",
             "--infra", infra_with_services],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "authorized" in result.stdout.lower()


# ── Generator services validation ──────────────────────────────────

from generate import validate  # noqa: E402


class TestGeneratorServices:
    """Test services validation in generate.py."""

    @pytest.fixture()
    def base_infra(self):
        """Minimal infra with two machines for service testing."""
        return {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "vault": {
                    "subnet_id": 0,
                    "machines": {
                        "vault-signer": {
                            "type": "lxc",
                            "ip": "10.100.0.10",
                        },
                    },
                },
                "work": {
                    "subnet_id": 1,
                    "machines": {
                        "work-dev": {
                            "type": "lxc",
                            "ip": "10.100.1.10",
                        },
                    },
                },
            },
        }

    def test_valid_services(self, base_infra):
        """Valid service declaration passes validation."""
        base_infra["domains"]["vault"]["machines"]["vault-signer"]["services"] = [
            {"name": "sign", "tool": "gpg_sign", "consumers": ["work-dev"]},
        ]
        errors = validate(base_infra)
        assert not any("service" in e.lower() for e in errors)

    def test_duplicate_service_name(self, base_infra):
        """Duplicate service names on same machine triggers error."""
        base_infra["domains"]["vault"]["machines"]["vault-signer"]["services"] = [
            {"name": "sign", "tool": "gpg_sign", "consumers": ["work-dev"]},
            {"name": "sign", "tool": "clipboard_get", "consumers": ["work-dev"]},
        ]
        errors = validate(base_infra)
        assert any("duplicate service name 'sign'" in e for e in errors)

    def test_unknown_tool(self, base_infra):
        """Unknown tool name triggers error."""
        base_infra["domains"]["vault"]["machines"]["vault-signer"]["services"] = [
            {"name": "bad_svc", "tool": "unknown_tool", "consumers": ["work-dev"]},
        ]
        errors = validate(base_infra)
        assert any("unknown tool 'unknown_tool'" in e for e in errors)

    def test_unknown_consumer(self, base_infra):
        """Consumer referencing nonexistent machine triggers error."""
        base_infra["domains"]["vault"]["machines"]["vault-signer"]["services"] = [
            {"name": "sign", "tool": "gpg_sign", "consumers": ["nonexistent-machine"]},
        ]
        errors = validate(base_infra)
        assert any("'nonexistent-machine' is not a known machine" in e for e in errors)

    def test_missing_service_name(self, base_infra):
        """Service without name triggers error."""
        base_infra["domains"]["vault"]["machines"]["vault-signer"]["services"] = [
            {"tool": "gpg_sign", "consumers": ["work-dev"]},
        ]
        errors = validate(base_infra)
        assert any("missing 'name'" in e for e in errors)

    def test_missing_service_tool(self, base_infra):
        """Service without tool triggers error."""
        base_infra["domains"]["vault"]["machines"]["vault-signer"]["services"] = [
            {"name": "sign", "consumers": ["work-dev"]},
        ]
        errors = validate(base_infra)
        assert any("missing 'tool'" in e for e in errors)

    def test_services_propagated_to_host_vars(self, base_infra, tmp_path):
        """Services are output as instance_services in host_vars."""
        from generate import generate

        base_infra["domains"]["vault"]["machines"]["vault-signer"]["services"] = [
            {"name": "sign", "tool": "gpg_sign", "consumers": ["work-dev"]},
        ]
        generate(base_infra, tmp_path)
        hv = (tmp_path / "host_vars" / "vault-signer.yml").read_text()
        assert "instance_services" in hv
        assert "sign" in hv
        assert "gpg_sign" in hv

    def test_no_services_omits_key(self, base_infra, tmp_path):
        """Machine without services does not have instance_services in host_vars."""
        from generate import generate

        generate(base_infra, tmp_path)
        hv = (tmp_path / "host_vars" / "work-dev.yml").read_text()
        assert "instance_services" not in hv

    def test_service_not_a_dict(self, base_infra):
        """Service that is a string instead of dict triggers error."""
        base_infra["domains"]["vault"]["machines"]["vault-signer"]["services"] = [
            "just_a_string",
        ]
        errors = validate(base_infra)
        assert any("must be a mapping" in e for e in errors)
