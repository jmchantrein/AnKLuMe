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
import binascii
import os
import re
import subprocess
import tempfile

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("anklume-mcp")

# ── Security: constrained paths and clipboard ──────────────────────

# file_accept / file_provide are restricted to this directory tree.
# The MCP server MUST NOT allow arbitrary filesystem access.
MCP_PORTAL_DIR = os.environ.get("ANKLUME_MCP_PORTAL", "/srv/anklume/mcp-portal")

# Clipboard stored with restricted permissions (not world-readable /tmp).
_CLIP_DIR = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/run/user/0"), "anklume")
CLIPBOARD_FILE = os.path.join(_CLIP_DIR, "clipboard")

# Allowed permission bits — no setuid (4xxx), setgid (2xxx), sticky (1xxx).
_MAX_MODE = 0o777


def _safe_portal_path(path: str) -> str | None:
    """Resolve *path* within MCP_PORTAL_DIR. Return None if it escapes."""
    real = os.path.realpath(os.path.join(MCP_PORTAL_DIR, path))
    portal_real = os.path.realpath(MCP_PORTAL_DIR)
    if not real.startswith(portal_real + os.sep) and real != portal_real:
        return None
    return real


# ── Tool implementations ─────────────────────────────────────────


@mcp.tool()
def gpg_sign(data: str, key_id: str = "") -> str:
    """Sign data with GPG. Input is base64-encoded, returns base64 signature."""
    try:
        raw = base64.b64decode(data)
    except (ValueError, binascii.Error) as exc:
        return f"ERROR: Invalid base64 data: {exc}"

    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tmp:
        tmp.write(raw)
        tmp_path = tmp.name

    try:
        cmd = ["gpg", "--batch", "--yes", "--detach-sign", "--armor"]
        if key_id:
            if not re.fullmatch(r"[A-Fa-f0-9]{8,40}|[\w.@<> -]+", key_id):
                return f"ERROR: Invalid key_id format: {key_id}"
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
    os.makedirs(_CLIP_DIR, mode=0o700, exist_ok=True)
    fd = os.open(CLIPBOARD_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, content.encode())
    finally:
        os.close(fd)
    return "Clipboard updated"


@mcp.tool()
def file_accept(path: str, data: str, mode: str = "") -> str:
    """Accept an incoming file into the portal directory. Data is base64-encoded."""
    if not path:
        return "ERROR: path is required"
    safe = _safe_portal_path(path)
    if safe is None:
        return f"ERROR: path escapes portal directory: {path}"
    try:
        raw = base64.b64decode(data)
    except (ValueError, binascii.Error) as exc:
        return f"ERROR: Invalid base64 data: {exc}"

    os.makedirs(os.path.dirname(safe) or ".", exist_ok=True)
    with open(safe, "wb") as f:
        f.write(raw)
    if mode:
        bits = int(mode, 8)
        if bits > _MAX_MODE:
            return f"ERROR: mode {mode} sets special bits (setuid/setgid/sticky)"
        os.chmod(safe, bits)
    return f"Written {len(raw)} bytes to {safe}"


@mcp.tool()
def file_provide(path: str) -> str:
    """Read a file from the portal directory and return its content as base64."""
    if not path:
        return "ERROR: path is required"
    safe = _safe_portal_path(path)
    if safe is None:
        return f"ERROR: path escapes portal directory: {path}"
    try:
        with open(safe, "rb") as f:
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
