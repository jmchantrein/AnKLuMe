"""Tests for Phase 20c MCP inter-container services.

Tests cover:
- Script quality (ruff check) for all 3 MCP Python files
- MCP server: tool registration, message processing, help
- MCP client: help output, list, call with mock server
- MCP policy: authorized access, denied access, missing infra
- Generator: services validation in generate.py
"""

import json
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
    """Test MCP server tool registration and message processing."""

    def test_help_flag(self):
        """--help shows usage."""
        result = subprocess.run(
            [sys.executable, str(MCP_SERVER), "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "AnKLuMe MCP server" in result.stdout

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

    def test_initialize_response(self):
        """Server responds to initialize with protocol version and capabilities."""
        msg = json.dumps({"jsonrpc": "2.0", "method": "initialize", "id": 1, "params": {}})
        result = subprocess.run(
            [sys.executable, str(MCP_SERVER)],
            input=msg + "\n", capture_output=True, text=True, timeout=5,
        )
        resp = json.loads(result.stdout.strip())
        assert resp["id"] == 1
        assert "protocolVersion" in resp["result"]
        assert "tools" in resp["result"]["capabilities"]
        assert resp["result"]["serverInfo"]["name"] == "anklume-mcp"

    def test_tools_list_response(self):
        """Server returns all tools on tools/list."""
        messages = [
            json.dumps({"jsonrpc": "2.0", "method": "initialize", "id": 1, "params": {}}),
            json.dumps({"jsonrpc": "2.0", "method": "tools/list", "id": 2, "params": {}}),
        ]
        result = subprocess.run(
            [sys.executable, str(MCP_SERVER)],
            input="\n".join(messages) + "\n",
            capture_output=True, text=True, timeout=5,
        )
        lines = [line for line in result.stdout.strip().splitlines() if line.strip()]
        assert len(lines) == 2
        resp = json.loads(lines[1])
        assert resp["id"] == 2
        tools = resp["result"]["tools"]
        tool_names = {t["name"] for t in tools}
        assert tool_names == {"gpg_sign", "clipboard_get", "clipboard_set", "file_accept", "file_provide"}

    def test_tools_call_clipboard_roundtrip(self):
        """clipboard_set then clipboard_get returns the same content."""
        messages = [
            json.dumps({"jsonrpc": "2.0", "method": "initialize", "id": 1, "params": {}}),
            json.dumps({
                "jsonrpc": "2.0", "method": "tools/call", "id": 2,
                "params": {"name": "clipboard_set", "arguments": {"content": "test-data-42"}},
            }),
            json.dumps({
                "jsonrpc": "2.0", "method": "tools/call", "id": 3,
                "params": {"name": "clipboard_get", "arguments": {}},
            }),
        ]
        result = subprocess.run(
            [sys.executable, str(MCP_SERVER)],
            input="\n".join(messages) + "\n",
            capture_output=True, text=True, timeout=5,
        )
        lines = [line for line in result.stdout.strip().splitlines() if line.strip()]
        assert len(lines) == 3
        get_resp = json.loads(lines[2])
        assert get_resp["id"] == 3
        text = get_resp["result"]["content"][0]["text"]
        assert "test-data-42" in text

    def test_tools_call_file_roundtrip(self, tmp_path):
        """file_accept then file_provide returns the same data."""
        import base64

        test_data = b"Hello AnKLuMe MCP"
        data_b64 = base64.b64encode(test_data).decode()
        test_file = str(tmp_path / "mcp-test-file.txt")

        messages = [
            json.dumps({"jsonrpc": "2.0", "method": "initialize", "id": 1, "params": {}}),
            json.dumps({
                "jsonrpc": "2.0", "method": "tools/call", "id": 2,
                "params": {"name": "file_accept", "arguments": {"path": test_file, "data": data_b64}},
            }),
            json.dumps({
                "jsonrpc": "2.0", "method": "tools/call", "id": 3,
                "params": {"name": "file_provide", "arguments": {"path": test_file}},
            }),
        ]
        result = subprocess.run(
            [sys.executable, str(MCP_SERVER)],
            input="\n".join(messages) + "\n",
            capture_output=True, text=True, timeout=5,
        )
        lines = [line for line in result.stdout.strip().splitlines() if line.strip()]
        assert len(lines) == 3
        provide_resp = json.loads(lines[2])
        returned_b64 = provide_resp["result"]["content"][0]["text"]
        assert base64.b64decode(returned_b64) == test_data

    def test_unknown_tool_returns_error(self):
        """Calling an unknown tool returns a JSON-RPC error."""
        messages = [
            json.dumps({"jsonrpc": "2.0", "method": "initialize", "id": 1, "params": {}}),
            json.dumps({
                "jsonrpc": "2.0", "method": "tools/call", "id": 2,
                "params": {"name": "nonexistent_tool", "arguments": {}},
            }),
        ]
        result = subprocess.run(
            [sys.executable, str(MCP_SERVER)],
            input="\n".join(messages) + "\n",
            capture_output=True, text=True, timeout=5,
        )
        lines = [line for line in result.stdout.strip().splitlines() if line.strip()]
        assert len(lines) == 2
        resp = json.loads(lines[1])
        assert "error" in resp
        assert "Unknown tool" in resp["error"]["message"]

    def test_unknown_method_returns_error(self):
        """Unknown JSON-RPC method returns method-not-found error."""
        msg = json.dumps({"jsonrpc": "2.0", "method": "resources/list", "id": 1, "params": {}})
        result = subprocess.run(
            [sys.executable, str(MCP_SERVER)],
            input=msg + "\n", capture_output=True, text=True, timeout=5,
        )
        resp = json.loads(result.stdout.strip())
        assert "error" in resp
        assert resp["error"]["code"] == -32601

    def test_invalid_json_returns_parse_error(self):
        """Malformed JSON returns parse error."""
        result = subprocess.run(
            [sys.executable, str(MCP_SERVER)],
            input="not valid json\n", capture_output=True, text=True, timeout=5,
        )
        resp = json.loads(result.stdout.strip())
        assert "error" in resp
        assert resp["error"]["code"] == -32700


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
        assert "AnKLuMe MCP client" in result.stdout

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
        assert "Would send" in result.stdout
        assert "tools/list" in result.stdout

    def test_call_dry_run(self):
        """call --dry-run shows what would be sent."""
        result = subprocess.run(
            [sys.executable, str(MCP_CLIENT), "--dry-run", "call", "clipboard_get"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "Would send" in result.stdout
        assert "tools/call" in result.stdout
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
        assert "AnKLuMe MCP policy engine" in result.stdout

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
