"""Enrichment functions — auto-generate resources after validation."""

import sys

from psot.addressing import _auto_assign_ips, _compute_addressing
from psot.constants import DEFAULT_TRUST_LEVEL
from psot.enrich_volumes import (
    _enrich_persistent_data,
    _enrich_shared_volumes,
)
from psot.resource_alloc import _enrich_resources


def enrich_infra(infra):
    """Enrich infra dict with auto-generated resources.

    Called after validate() and before generate(). Mutates infra in place.
    Handles: auto-creation of anklume-firewall VM, AI access policy
    enrichment.
    """
    _enrich_addressing(infra)
    _enrich_firewall(infra)
    _enrich_ai_access(infra)
    _enrich_resources(infra)
    _enrich_shared_volumes(infra)
    _enrich_persistent_data(infra)


def _enrich_addressing(infra):
    """Compute zone-based addressing and auto-assign IPs.

    Runs when global.addressing is present. Sets default trust_level,
    computes zone addressing, and auto-assigns IPs to machines without
    explicit ip: fields. Stores results in infra['_addressing'].
    """
    g = infra.get("global", {})
    if "addressing" not in g:
        return  # Legacy mode (base_subnet), no zone addressing

    addr = g["addressing"]
    base_octet = addr.get("base_octet", 10)

    # Default trust_level to semi-trusted for domains that don't have one
    for domain in (infra.get("domains") or {}).values():
        domain.setdefault("trust_level", DEFAULT_TRUST_LEVEL)

    # Compute zone-based addressing
    addressing = _compute_addressing(infra)
    infra["_addressing"] = addressing

    # Auto-assign IPs per domain
    for dname, domain in (infra.get("domains") or {}).items():
        if dname in addressing:
            info = addressing[dname]
            _auto_assign_ips(
                domain,
                base_octet,
                info["second_octet"],
                info["domain_seq"],
            )


def _enrich_firewall(infra):
    """Auto-create anklume-firewall VM when firewall_mode is 'vm'."""
    g = infra.get("global", {})
    firewall_mode = g.get("firewall_mode", "host")
    if firewall_mode != "vm":
        return

    domains = infra.get("domains") or {}

    # Check if anklume-firewall (or legacy sys-firewall) already exists
    for domain in domains.values():
        for mname in domain.get("machines") or {}:
            if mname in ("anklume-firewall", "sys-firewall"):
                return

    # Require anklume domain
    if "anklume" not in domains:
        raise ValueError(
            "firewall_mode is 'vm' but no 'anklume' domain exists. "
            "Cannot auto-create anklume-firewall."
        )

    anklume_domain = domains["anklume"]

    # Compute firewall IP from addressing or legacy base_subnet
    if "_addressing" in infra and "anklume" in infra.get(
        "_addressing", {}
    ):
        info = infra["_addressing"]["anklume"]
        addr_cfg = g.get("addressing", {})
        bo = addr_cfg.get("base_octet", 10)
        fw_ip = (
            f"{bo}.{info['second_octet']}.{info['domain_seq']}.253"
        )
    else:
        base_subnet = g.get("base_subnet", "10.100")
        anklume_subnet_id = anklume_domain.get("subnet_id", 0)
        fw_ip = f"{base_subnet}.{anklume_subnet_id}.253"

    sys_fw = {
        "description": (
            "Centralized firewall VM (auto-created by generator)"
        ),
        "type": "vm",
        "ip": fw_ip,
        "config": {
            "limits.cpu": "2",
            "limits.memory": "2GiB",
        },
        "roles": ["base_system", "firewall_router"],
        "ephemeral": False,
    }

    if (
        "machines" not in anklume_domain
        or anklume_domain["machines"] is None
    ):
        anklume_domain["machines"] = {}
    anklume_domain["machines"]["anklume-firewall"] = sys_fw

    print(
        "INFO: firewall_mode is 'vm' — auto-created "
        "anklume-firewall in anklume domain "
        f"(ip: {fw_ip})",
        file=sys.stderr,
    )


def _enrich_ai_access(infra):
    """Auto-create network policy for exclusive AI access if missing."""
    g = infra.get("global", {})
    ai_access_policy = g.get("ai_access_policy", "open")
    if ai_access_policy != "exclusive":
        return

    ai_access_default = g.get("ai_access_default")
    if not ai_access_default or "ai-tools" not in (
        infra.get("domains") or {}
    ):
        return

    existing_policies = infra.get("network_policies") or []
    has_ai_policy = any(
        isinstance(p, dict) and p.get("to") == "ai-tools"
        for p in existing_policies
    )
    if has_ai_policy:
        return

    infra.setdefault("network_policies", [])
    infra["network_policies"].append(
        {
            "description": (
                f"AI access: {ai_access_default} -> ai-tools "
                f"(auto-created)"
            ),
            "from": ai_access_default,
            "to": "ai-tools",
            "ports": "all",
            "bidirectional": True,
        }
    )
    print(
        f"INFO: ai_access_policy is 'exclusive' — auto-created "
        f"network policy from '{ai_access_default}' to 'ai-tools'",
        file=sys.stderr,
    )
