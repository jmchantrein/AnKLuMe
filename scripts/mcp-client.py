#!/usr/bin/env python3
"""MCP client CLI for AnKLuMe inter-container services.

Connects to an MCP server via stdin/stdout (JSON-RPC) and provides
a CLI for listing and calling tools. Designed for use with
`incus exec` or Incus proxy device Unix sockets.

Uses stdlib only (no external MCP SDK dependency).

See docs/mcp-services.md and ROADMAP.md Phase 20c.
"""

import argparse
import contextlib
import json
import subprocess
import sys

# ── JSON-RPC helpers ─────────────────────────────────────────────


def _make_request(method, params=None, req_id=1):
    msg = {"jsonrpc": "2.0", "method": method, "id": req_id}
    if params:
        msg["params"] = params
    return msg


def _send_receive(messages, server_cmd):
    """Send JSON-RPC messages to a server process, return responses."""
    input_data = "\n".join(json.dumps(m) for m in messages) + "\n"
    result = subprocess.run(  # noqa: S603
        server_cmd, input=input_data, capture_output=True, text=True, timeout=30,
    )
    responses = []
    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if line:
            with contextlib.suppress(json.JSONDecodeError):
                responses.append(json.loads(line))
    return responses


def _build_server_cmd(instance=None, project=None):
    """Build the command to reach the MCP server."""
    if instance:
        cmd = ["incus", "exec"]
        if project:
            cmd += ["--project", project]
        cmd += [instance, "--", "python3", "/opt/anklume/mcp-server.py"]
        return cmd
    return ["python3", "scripts/mcp-server.py"]


# ── Commands ─────────────────────────────────────────────────────


def cmd_list(args):
    """List available MCP tools."""
    server_cmd = _build_server_cmd(args.instance, args.project)
    messages = [
        _make_request("initialize", req_id=1),
        _make_request("tools/list", req_id=2),
    ]

    if args.dry_run:
        print("Would send to server:")
        for m in messages:
            print(f"  {json.dumps(m)}")
        return 0

    try:
        responses = _send_receive(messages, server_cmd)
    except FileNotFoundError:
        print("ERROR: Cannot reach MCP server. Is the instance running?", file=sys.stderr)
        return 1
    except subprocess.TimeoutExpired:
        print("ERROR: MCP server timed out.", file=sys.stderr)
        return 1

    for resp in responses:
        if resp.get("id") == 2:
            result = resp.get("result", {})
            tools = result.get("tools", [])
            if not tools:
                print("No tools available.")
                return 0
            print("Available MCP tools:")
            for tool in tools:
                name = tool.get("name", "?")
                desc = tool.get("description", "")
                print(f"  {name:<20s} {desc}")
            return 0

    print("ERROR: No tools/list response received.", file=sys.stderr)
    return 1


def cmd_call(args):
    """Call an MCP tool."""
    tool_name = args.tool_name
    try:
        arguments = json.loads(args.arguments) if args.arguments else {}
    except json.JSONDecodeError as exc:
        print(f"ERROR: Invalid JSON arguments: {exc}", file=sys.stderr)
        return 1

    server_cmd = _build_server_cmd(args.instance, args.project)
    messages = [
        _make_request("initialize", req_id=1),
        _make_request("tools/call", {"name": tool_name, "arguments": arguments}, req_id=2),
    ]

    if args.dry_run:
        print("Would send to server:")
        for m in messages:
            print(f"  {json.dumps(m)}")
        return 0

    try:
        responses = _send_receive(messages, server_cmd)
    except FileNotFoundError:
        print("ERROR: Cannot reach MCP server. Is the instance running?", file=sys.stderr)
        return 1
    except subprocess.TimeoutExpired:
        print("ERROR: MCP server timed out.", file=sys.stderr)
        return 1

    for resp in responses:
        if resp.get("id") == 2:
            if "error" in resp:
                err = resp["error"]
                print(f"ERROR: {err.get('message', 'Unknown error')}", file=sys.stderr)
                return 1
            result = resp.get("result", {})
            is_error = result.get("isError", False)
            for content in result.get("content", []):
                print(content.get("text", ""))
            return 1 if is_error else 0

    print("ERROR: No tools/call response received.", file=sys.stderr)
    return 1


def main():
    parser = argparse.ArgumentParser(
        description="AnKLuMe MCP client — call inter-container services"
    )
    parser.add_argument("--instance", "-i", help="Target instance name")
    parser.add_argument("--project", "-p", help="Incus project for the target instance")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be sent without executing")

    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list", help="List available MCP tools")

    call_parser = sub.add_parser("call", help="Call an MCP tool")
    call_parser.add_argument("tool_name", help="Tool name to call")
    call_parser.add_argument("arguments", nargs="?", default="{}", help="JSON arguments (default: {})")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    if args.command == "list":
        return cmd_list(args)
    if args.command == "call":
        return cmd_call(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
