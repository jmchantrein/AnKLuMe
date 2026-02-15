#!/usr/bin/env python3
"""MCP client CLI for AnKLuMe inter-container services.

Connects to an MCP server using the official Python SDK and provides
a CLI for listing and calling tools. Designed for use with
`incus exec` or Incus proxy device Unix sockets.

Requires: pip install mcp

See docs/mcp-services.md and ROADMAP.md Phase 20c.
"""

import argparse
import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# ── Server connection ─────────────────────────────────────────────


def _build_server_params(instance=None, project=None):
    """Build StdioServerParameters for the MCP server."""
    if instance:
        args = ["exec"]
        if project:
            args += ["--project", project]
        args += [instance, "--", "python3", "/opt/anklume/mcp-server.py"]
        return StdioServerParameters(command="incus", args=args)
    return StdioServerParameters(
        command=sys.executable,
        args=["scripts/mcp-server.py"],
    )


# ── Commands ─────────────────────────────────────────────────────


async def _cmd_list(args):
    """List available MCP tools."""
    server_params = _build_server_params(args.instance, args.project)

    if args.dry_run:
        print("Would connect to MCP server:")
        print(f"  command: {server_params.command}")
        print(f"  args: {list(server_params.args)}")
        print("  action: tools/list")
        return 0

    try:
        async with stdio_client(server_params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            tools = result.tools
            if not tools:
                print("No tools available.")
                return 0
            print("Available MCP tools:")
            for tool in tools:
                print(f"  {tool.name:<20s} {tool.description or ''}")
            return 0
    except Exception as exc:
        print(f"ERROR: Cannot reach MCP server: {exc}", file=sys.stderr)
        return 1


async def _cmd_call(args):
    """Call an MCP tool."""
    tool_name = args.tool_name
    try:
        arguments = json.loads(args.arguments) if args.arguments else {}
    except json.JSONDecodeError as exc:
        print(f"ERROR: Invalid JSON arguments: {exc}", file=sys.stderr)
        return 1

    server_params = _build_server_params(args.instance, args.project)

    if args.dry_run:
        print("Would connect to MCP server:")
        print(f"  command: {server_params.command}")
        print(f"  args: {list(server_params.args)}")
        print(f"  action: tools/call {tool_name}")
        print(f"  arguments: {json.dumps(arguments)}")
        return 0

    try:
        async with stdio_client(server_params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            for content in result.content:
                print(content.text if hasattr(content, "text") else str(content))
            return 1 if result.isError else 0
    except Exception as exc:
        print(f"ERROR: Cannot reach MCP server: {exc}", file=sys.stderr)
        return 1


# ── Entry point ───────────────────────────────────────────────────


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
        return asyncio.run(_cmd_list(args))
    if args.command == "call":
        return asyncio.run(_cmd_call(args))
    return 0


if __name__ == "__main__":
    sys.exit(main())
