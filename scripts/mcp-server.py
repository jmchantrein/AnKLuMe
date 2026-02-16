#!/usr/bin/env python3
"""MCP server template for anklume inter-container services.

Implements an MCP server using the official Python SDK (FastMCP).
Provides tools for controlled service exposure between containers
via Incus proxy devices.

Only exposes: initialize, tools/list, tools/call (no prompts,
resources, or sampling — per SPEC.md Phase 20c).

Requires: pip install mcp

See docs/mcp-services.md and ROADMAP.md Phase 20c.
"""

import argparse
import base64
import os
import subprocess
import tempfile

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("anklume-mcp")

CLIPBOARD_FILE = "/tmp/anklume-clipboard"  # noqa: S108


# ── Tool implementations ─────────────────────────────────────────


@mcp.tool()
def gpg_sign(data: str, key_id: str = "") -> str:
    """Sign data with GPG. Input is base64-encoded, returns base64 signature."""
    try:
        raw = base64.b64decode(data)
    except Exception as exc:
        return f"ERROR: Invalid base64 data: {exc}"

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
            return f"ERROR: GPG sign failed: {result.stderr.decode()}"
        sig_b64 = base64.b64encode(result.stdout).decode()
        return f"Signature (base64): {sig_b64}"
    finally:
        os.unlink(tmp_path)


@mcp.tool()
def clipboard_get() -> str:
    """Get the current clipboard content."""
    try:
        with open(CLIPBOARD_FILE) as f:
            return f.read()
    except FileNotFoundError:
        return ""


@mcp.tool()
def clipboard_set(content: str) -> str:
    """Set the clipboard content."""
    with open(CLIPBOARD_FILE, "w") as f:
        f.write(content)
    return "Clipboard updated"


@mcp.tool()
def file_accept(path: str, data: str, mode: str = "") -> str:
    """Accept an incoming file. Data is base64-encoded."""
    if not path:
        return "ERROR: path is required"
    try:
        raw = base64.b64decode(data)
    except Exception as exc:
        return f"ERROR: Invalid base64 data: {exc}"

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as f:
        f.write(raw)
    if mode:
        os.chmod(path, int(mode, 8))
    return f"Written {len(raw)} bytes to {path}"


@mcp.tool()
def file_provide(path: str) -> str:
    """Read a file and return its content as base64."""
    if not path:
        return "ERROR: path is required"
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except FileNotFoundError:
        return f"ERROR: File not found: {path}"
    except PermissionError:
        return f"ERROR: Permission denied: {path}"
    return base64.b64encode(raw).decode()


# ── Entry point ───────────────────────────────────────────────────


def list_tools():
    """Print registered tools and exit."""
    tools = [
        ("gpg_sign", "Sign data with GPG (base64 input/output)"),
        ("clipboard_get", "Get the current clipboard content"),
        ("clipboard_set", "Set the clipboard content"),
        ("file_accept", "Accept an incoming file (base64-encoded)"),
        ("file_provide", "Read a file and return as base64"),
    ]
    for name, desc in tools:
        print(f"  {name:<20s} {desc}")


def main():
    parser = argparse.ArgumentParser(
        description="anklume MCP server — inter-container services via MCP SDK"
    )
    parser.add_argument(
        "--list-tools", action="store_true",
        help="List available tools and exit",
    )
    parser.add_argument(
        "--transport", default="stdio", choices=["stdio"],
        help="MCP transport (default: stdio)",
    )
    args = parser.parse_args()

    if args.list_tools:
        list_tools()
        return

    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
