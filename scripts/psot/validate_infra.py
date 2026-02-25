"""Validation of resource policy and host subnet conflicts."""

import ipaddress
import os

from psot.resources import _parse_memory_value


def _validate_resource_policy(g, errors):
    """Validate resource_policy section."""
    resource_policy = g.get("resource_policy")
    if resource_policy is None or resource_policy is True:
        return
    if not isinstance(resource_policy, dict):
        errors.append(
            "global.resource_policy must be a mapping or true"
        )
        return
    rp_mode = resource_policy.get("mode", "proportional")
    if rp_mode not in ("proportional", "equal"):
        errors.append(
            f"resource_policy.mode must be 'proportional' or "
            f"'equal', got '{rp_mode}'"
        )
    rp_cpu_mode = resource_policy.get("cpu_mode", "allowance")
    if rp_cpu_mode not in ("allowance", "count"):
        errors.append(
            f"resource_policy.cpu_mode must be 'allowance' or "
            f"'count', got '{rp_cpu_mode}'"
        )
    rp_mem_enforce = resource_policy.get("memory_enforce", "soft")
    if rp_mem_enforce not in ("soft", "hard"):
        errors.append(
            f"resource_policy.memory_enforce must be 'soft' or "
            f"'hard', got '{rp_mem_enforce}'"
        )
    rp_overcommit = resource_policy.get("overcommit", False)
    if not isinstance(rp_overcommit, bool):
        errors.append("resource_policy.overcommit must be a boolean")
    hr = resource_policy.get("host_reserve")
    if hr is not None:
        _validate_host_reserve(hr, errors)


def _validate_host_reserve(hr, errors):
    """Validate resource_policy.host_reserve section."""
    if not isinstance(hr, dict):
        errors.append(
            "resource_policy.host_reserve must be a mapping"
        )
        return
    for field in ("cpu", "memory"):
        val = hr.get(field)
        if val is None:
            continue
        if isinstance(val, str) and val.endswith("%"):
            try:
                pct = int(val.rstrip("%"))
                if not 0 < pct < 100:
                    errors.append(
                        f"resource_policy.host_reserve."
                        f"{field}: percentage must be "
                        f"1-99, got {pct}"
                    )
            except ValueError:
                errors.append(
                    f"resource_policy.host_reserve."
                    f"{field}: invalid format '{val}'"
                )
        elif isinstance(val, (int, float)):
            if val <= 0:
                errors.append(
                    f"resource_policy.host_reserve."
                    f"{field}: must be positive, got {val}"
                )
        elif isinstance(val, str) and field == "memory":
            if _parse_memory_value(val) <= 0:
                errors.append(
                    f"resource_policy.host_reserve.memory: "
                    f"invalid value '{val}'"
                )
        else:
            errors.append(
                f"resource_policy.host_reserve.{field}: "
                f"must be 'N%' or a positive number, "
                f"got '{val}'"
            )


def _validate_host_subnets(
    errors, g, has_addressing, computed_addressing,
    subnet_ids, base_subnet, check_host_subnets,
    resolve_fn,
):
    """Detect host subnet conflicts that would cause routing loops."""
    skip_host_check = (
        not check_host_subnets
        or os.environ.get("ANKLUME_SKIP_HOST_SUBNET_CHECK") == "1"
    )
    host_subnets = (
        [] if skip_host_check else resolve_fn("_detect_host_subnets")()
    )
    if not host_subnets:
        return

    subnets_to_check = []
    if has_addressing and computed_addressing:
        addr_cfg = g.get("addressing", {})
        bo = addr_cfg.get("base_octet", 10)
        for dname, info in computed_addressing.items():
            try:
                net = ipaddress.IPv4Network(
                    f"{bo}.{info['second_octet']}."
                    f"{info['domain_seq']}.0/24"
                )
                subnets_to_check.append((dname, net))
            except ValueError:
                continue
    else:
        for sid, dname in subnet_ids.items():
            try:
                net = ipaddress.IPv4Network(
                    f"{base_subnet}.{sid}.0/24"
                )
                subnets_to_check.append((dname, net))
            except ValueError:
                continue

    for dname, domain_net in subnets_to_check:
        for ifname, host_net in host_subnets:
            if domain_net.overlaps(host_net):
                if has_addressing:
                    fix_hint = (
                        "Adjust global.addressing.zone_base or "
                        "use a different subnet_id."
                    )
                else:
                    alt_base = (
                        "10.200"
                        if base_subnet == "10.100"
                        else "10.100"
                    )
                    fix_hint = (
                        f"Change global.base_subnet to "
                        f"'{alt_base}' or use a different "
                        f"subnet_id for this domain."
                    )
                errors.append(
                    f"SUBNET CONFLICT: Domain '{dname}' uses "
                    f"{domain_net} which overlaps with host "
                    f"interface '{ifname}' ({host_net}). Incus "
                    f"would create a bridge on the same subnet, "
                    f"causing a routing loop and total loss of "
                    f"network connectivity. {fix_hint}"
                )
