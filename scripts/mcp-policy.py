#!/usr/bin/env python3
"""MCP policy engine for anklume inter-container services.

Simple allow-list policy engine that reads the `services:` section
from infra.yml machine declarations and validates whether a caller
(instance name) is authorized to access a specific service.

Exit 0 = allowed, Exit 1 = denied or error.

See docs/mcp-services.md and ROADMAP.md Phase 20c.
"""

import argparse
import sys
from pathlib import Path

import yaml

# ── Known MCP tool names (must match mcp-server.py) ─────────────

KNOWN_TOOLS = {"gpg_sign", "clipboard_get", "clipboard_set", "file_accept", "file_provide"}


def load_infra(path):
    """Load infra.yml (file) or infra/ (directory)."""
    p = Path(path)
    if p.is_file():
        with open(p) as f:
            return yaml.safe_load(f)
    if p.is_dir():
        base = p / "base.yml"
        if not base.exists():
            print(f"ERROR: {base} not found", file=sys.stderr)
            sys.exit(1)
        with open(base) as f:
            infra = yaml.safe_load(f) or {}
        domains_dir = p / "domains"
        if domains_dir.is_dir():
            infra.setdefault("domains", {})
            for df in sorted(domains_dir.glob("*.yml")):
                with open(df) as f:
                    dd = yaml.safe_load(f) or {}
                for dname, dconf in dd.items():
                    infra["domains"][dname] = dconf
        return infra
    print(f"ERROR: {path} not found", file=sys.stderr)
    sys.exit(1)


def build_policy_map(infra):
    """Build a map of (provider_machine, service_name) -> set(allowed_consumers).

    Scans all machines for `services:` declarations and builds an
    allow-list keyed by (machine_name, service_name).
    """
    policy = {}
    for _dname, domain in (infra.get("domains") or {}).items():
        for mname, machine in (domain.get("machines") or {}).items():
            for svc in machine.get("services") or []:
                name = svc.get("name", "")
                consumers = set(svc.get("consumers") or [])
                policy[(mname, name)] = consumers
    return policy


def check_access(infra, caller, service, provider=None):
    """Check if caller is authorized to access service.

    Args:
        infra: Parsed infra.yml dict
        caller: Instance name of the caller
        service: Service name to access
        provider: Provider instance name (optional, checks all if omitted)

    Returns:
        (allowed: bool, reason: str)
    """
    policy = build_policy_map(infra)

    if not policy:
        return False, "No services declared in infra.yml"

    if provider:
        key = (provider, service)
        if key not in policy:
            return False, f"Service '{service}' not declared on '{provider}'"
        if caller in policy[key]:
            return True, f"'{caller}' is authorized to access '{service}' on '{provider}'"
        return False, f"'{caller}' is not in consumers list for '{service}' on '{provider}'"

    # Check all providers
    for (prov, svc_name), consumers in policy.items():
        if svc_name == service and caller in consumers:
            return True, f"'{caller}' is authorized to access '{service}' on '{prov}'"

    return False, f"'{caller}' is not authorized to access '{service}' on any provider"


def cmd_check(args):
    """Check access policy."""
    infra = load_infra(args.infra)
    allowed, reason = check_access(infra, args.caller, args.service, args.provider)
    print(reason)
    return 0 if allowed else 1


def cmd_list_services(args):
    """List all declared services."""
    infra = load_infra(args.infra)
    policy = build_policy_map(infra)
    if not policy:
        print("No services declared in infra.yml")
        return 0
    print("Declared MCP services:")
    for (provider, service), consumers in sorted(policy.items()):
        consumers_str = ", ".join(sorted(consumers)) if consumers else "(none)"
        print(f"  {provider}:{service}  consumers=[{consumers_str}]")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="anklume MCP policy engine — validate service access"
    )
    sub = parser.add_subparsers(dest="command")

    check_p = sub.add_parser("check", help="Check if a caller can access a service")
    check_p.add_argument("--caller", required=True, help="Caller instance name")
    check_p.add_argument("--service", required=True, help="Service name")
    check_p.add_argument("--provider", help="Provider instance name (optional)")
    check_p.add_argument("--infra", default="infra.yml", help="Path to infra.yml or infra/ directory")

    list_p = sub.add_parser("list", help="List all declared services")
    list_p.add_argument("--infra", default="infra.yml", help="Path to infra.yml or infra/ directory")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    if args.command == "check":
        return cmd_check(args)
    if args.command == "list":
        return cmd_list_services(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
