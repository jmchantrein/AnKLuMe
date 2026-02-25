"""Zone-based IP addressing computation (ADR-038)."""

import ipaddress
import json
import subprocess

from psot.constants import DEFAULT_TRUST_LEVEL, ZONE_OFFSETS


def _detect_host_subnets():
    """Detect network subnets on host interfaces via `ip -json addr show`.

    Returns a list of (interface_name, network) tuples where network is an
    ipaddress.IPv4Network. Returns empty list if detection fails.
    """
    try:
        result = subprocess.run(
            ["ip", "-json", "addr", "show"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return []
        data = json.loads(result.stdout)
    except (
        FileNotFoundError,
        subprocess.TimeoutExpired,
        json.JSONDecodeError,
    ):
        return []

    subnets = []
    for iface in data:
        ifname = iface.get("ifname", "")
        # Skip loopback and Incus bridges (net-*)
        if ifname == "lo" or ifname.startswith("net-"):
            continue
        for addr_info in iface.get("addr_info", []):
            if addr_info.get("family") != "inet":
                continue
            try:
                net = ipaddress.IPv4Network(
                    f"{addr_info['local']}/{addr_info['prefixlen']}",
                    strict=False,
                )
                subnets.append((ifname, net))
            except (KeyError, ValueError):
                continue
    return subnets


def _compute_addressing(infra):
    """Compute zone-based addressing from trust levels.

    Groups domains by trust_level, computes second_octet from zone_base +
    offset, and assigns domain_seq (third octet) alphabetically within each
    zone.  Explicit subnet_id overrides auto-assignment.

    Returns dict: {domain_name: {"second_octet": int, "domain_seq": int}}
    """
    g = infra.get("global", {})
    addr = g.get("addressing", {})
    zone_base = addr.get("zone_base", 100)
    domains = infra.get("domains") or {}

    # Group domains by trust_level
    zones = {}
    for dname, domain in domains.items():
        trust = domain.get("trust_level", DEFAULT_TRUST_LEVEL)
        zones.setdefault(trust, []).append(dname)

    result = {}
    for trust_level, domain_names in zones.items():
        zone_offset = ZONE_OFFSETS.get(
            trust_level, ZONE_OFFSETS[DEFAULT_TRUST_LEVEL]
        )
        second_octet = zone_base + zone_offset

        # Separate explicit subnet_id from auto-assign
        explicit_seqs = {}
        auto_names = []
        for dname in sorted(domain_names):
            sid = domains[dname].get("subnet_id")
            if sid is not None:
                explicit_seqs[sid] = dname
            else:
                auto_names.append(dname)

        # Auto-assign domain_seq, skipping explicit values
        seq = 0
        for dname in auto_names:
            while seq in explicit_seqs:
                seq += 1
            explicit_seqs[seq] = dname
            seq += 1

        for seq_val, dname in explicit_seqs.items():
            result[dname] = {
                "second_octet": second_octet,
                "domain_seq": seq_val,
            }

    return result


def _auto_assign_ips(domain, base_octet, second_octet, domain_seq):
    """Auto-assign IPs to machines without explicit ip: field.

    Assigns addresses starting from .1 in the static range (.1-.99),
    skipping already-used host numbers. Machines are processed in
    declaration order.
    """
    machines = domain.get("machines") or {}
    subnet_prefix = f"{base_octet}.{second_octet}.{domain_seq}"

    # Collect already-used host numbers in this subnet
    used = set()
    for m in machines.values():
        ip = m.get("ip")
        if ip and ip.startswith(f"{subnet_prefix}."):
            try:
                host = int(ip.rsplit(".", 1)[1])
                used.add(host)
            except (ValueError, IndexError):
                pass

    # Assign IPs to machines without one (declaration order)
    next_host = 1
    for mname, m in machines.items():
        if not m.get("ip"):
            while next_host in used and next_host <= 99:
                next_host += 1
            if next_host > 99:
                raise ValueError(
                    f"Domain ran out of static IPs (.1-.99) for "
                    f"machine '{mname}'"
                )
            m["ip"] = f"{subnet_prefix}.{next_host}"
            used.add(next_host)
            next_host += 1
