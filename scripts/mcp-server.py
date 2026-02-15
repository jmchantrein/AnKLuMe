#!/usr/bin/env python3
"""MCP server template for AnKLuMe inter-container services.

Implements a minimal MCP (Model Context Protocol) server over JSON-RPC
on stdio. Provides tools for controlled service exposure between
containers via Incus proxy devices.

Only supports: initialize, tools/list, tools/call (no prompts,
resources, or sampling — per SPEC.md Phase 20c).

Uses stdlib only (no external MCP SDK dependency).

See docs/mcp-services.md and ROADMAP.md Phase 20c.
"""

import argparse
import json
import os
import subprocess
import sys

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "anklume-mcp"
SERVER_VERSION = "0.1.0"

# ── Tool definitions ─────────────────────────────────────────────


TOOLS = [
    {
        "name": "gpg_sign",
        "description": "Sign a file with GPG. The file content is passed as base64-encoded input.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "data": {"type": "string", "description": "Base64-encoded file content to sign"},
                "key_id": {"type": "string", "description": "GPG key ID to use (optional, uses default if omitted)"},
            },
            "required": ["data"],
        },
    },
    {
        "name": "clipboard_get",
        "description": "Get the current clipboard content.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "clipboard_set",
        "description": "Set the clipboard content.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Content to place on the clipboard"},
            },
            "required": ["content"],
        },
    },
    {
        "name": "file_accept",
        "description": "Accept an incoming file and write it to a specified path.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Destination file path"},
                "data": {"type": "string", "description": "Base64-encoded file content"},
                "mode": {"type": "string", "description": "File permissions (octal, e.g. '0644')"},
            },
            "required": ["path", "data"],
        },
    },
    {
        "name": "file_provide",
        "description": "Read a file and return its content as base64.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Source file path to read"},
            },
            "required": ["path"],
        },
    },
]

TOOL_MAP = {t["name"]: t for t in TOOLS}

# ── Tool implementations ─────────────────────────────────────────

CLIPBOARD_FILE = "/tmp/anklume-clipboard"  # noqa: S108


def _tool_gpg_sign(arguments):
    import base64
    import tempfile

    data_b64 = arguments.get("data", "")
    key_id = arguments.get("key_id")
    try:
        raw = base64.b64decode(data_b64)
    except Exception as exc:
        return _error_result(f"Invalid base64 data: {exc}")

    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tmp:
        tmp.write(raw)
        tmp_path = tmp.name

    try:
        cmd = ["gpg", "--batch", "--yes", "--detach-sign", "--armor"]
        if key_id:
            cmd += ["--local-user", key_id]
        cmd += ["--output", "-", tmp_path]
        result = subprocess.run(cmd, capture_output=True, timeout=30)  # noqa: S603
        if result.returncode != 0:
            return _error_result(f"GPG sign failed: {result.stderr.decode()}")
        sig_b64 = base64.b64encode(result.stdout).decode()
        return _text_result(f"Signature (base64): {sig_b64}")
    finally:
        os.unlink(tmp_path)


def _tool_clipboard_get(_arguments):
    try:
        content = open(CLIPBOARD_FILE).read()  # noqa: SIM115
    except FileNotFoundError:
        content = ""
    return _text_result(content)


def _tool_clipboard_set(arguments):
    content = arguments.get("content", "")
    with open(CLIPBOARD_FILE, "w") as f:
        f.write(content)
    return _text_result("Clipboard updated")


def _tool_file_accept(arguments):
    import base64

    path = arguments.get("path", "")
    data_b64 = arguments.get("data", "")
    mode = arguments.get("mode")

    if not path:
        return _error_result("path is required")
    try:
        raw = base64.b64decode(data_b64)
    except Exception as exc:
        return _error_result(f"Invalid base64 data: {exc}")

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as f:
        f.write(raw)
    if mode:
        os.chmod(path, int(mode, 8))
    return _text_result(f"Written {len(raw)} bytes to {path}")


def _tool_file_provide(arguments):
    import base64

    path = arguments.get("path", "")
    if not path:
        return _error_result("path is required")
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except FileNotFoundError:
        return _error_result(f"File not found: {path}")
    except PermissionError:
        return _error_result(f"Permission denied: {path}")
    return _text_result(base64.b64encode(raw).decode())


TOOL_HANDLERS = {
    "gpg_sign": _tool_gpg_sign,
    "clipboard_get": _tool_clipboard_get,
    "clipboard_set": _tool_clipboard_set,
    "file_accept": _tool_file_accept,
    "file_provide": _tool_file_provide,
}

# ── JSON-RPC helpers ─────────────────────────────────────────────


def _text_result(text):
    return {"content": [{"type": "text", "text": text}]}


def _error_result(text):
    return {"content": [{"type": "text", "text": text}], "isError": True}


def _jsonrpc_response(req_id, result):
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _jsonrpc_error(req_id, code, message):
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


# ── MCP request handlers ─────────────────────────────────────────


def handle_initialize(req_id, _params):
    return _jsonrpc_response(req_id, {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {"tools": {}},
        "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
    })


def handle_tools_list(req_id, _params):
    return _jsonrpc_response(req_id, {"tools": TOOLS})


def handle_tools_call(req_id, params):
    tool_name = params.get("name", "")
    arguments = params.get("arguments", {})

    if tool_name not in TOOL_MAP:
        return _jsonrpc_error(req_id, -32602, f"Unknown tool: {tool_name}")

    handler = TOOL_HANDLERS.get(tool_name)
    if not handler:
        return _jsonrpc_error(req_id, -32603, f"No handler for tool: {tool_name}")

    try:
        result = handler(arguments)
    except Exception as exc:
        return _jsonrpc_response(req_id, _error_result(str(exc)))

    return _jsonrpc_response(req_id, result)


HANDLERS = {
    "initialize": handle_initialize,
    "notifications/initialized": None,  # notification, no response
    "tools/list": handle_tools_list,
    "tools/call": handle_tools_call,
}

# ── Main loop ─────────────────────────────────────────────────────


def process_message(line):
    """Process a single JSON-RPC message. Returns response dict or None."""
    try:
        msg = json.loads(line)
    except json.JSONDecodeError:
        return _jsonrpc_error(None, -32700, "Parse error")

    method = msg.get("method", "")
    req_id = msg.get("id")
    params = msg.get("params", {})

    handler = HANDLERS.get(method)
    if handler is None:
        if req_id is None:
            return None  # notification — no response
        return _jsonrpc_error(req_id, -32601, f"Method not found: {method}")

    return handler(req_id, params)


def serve():
    """Run the MCP server on stdin/stdout."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        response = process_message(line)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser(
        description="AnKLuMe MCP server — inter-container services via JSON-RPC over stdio"
    )
    parser.add_argument(
        "--list-tools", action="store_true",
        help="List available tools and exit",
    )
    args = parser.parse_args()

    if args.list_tools:
        for tool in TOOLS:
            print(f"  {tool['name']:<20s} {tool['description']}")
        return

    serve()


if __name__ == "__main__":
    main()
