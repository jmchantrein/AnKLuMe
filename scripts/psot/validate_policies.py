"""Validation of network policies and AI access."""


def _validate_network_policies(
    infra, errors, domain_names, all_machines,
):
    """Validate network_policies section."""
    for i, policy in enumerate(infra.get("network_policies") or []):
        if not isinstance(policy, dict):
            errors.append(f"network_policies[{i}]: must be a mapping")
            continue
        for field in ("from", "to"):
            ref = policy.get(field)
            if ref is None:
                errors.append(
                    f"network_policies[{i}]: missing '{field}'"
                )
            elif (
                ref != "host"
                and ref not in domain_names
                and ref not in all_machines
            ):
                errors.append(
                    f"network_policies[{i}]: '{field}: {ref}' is not "
                    f"a known domain, machine, or 'host'"
                )
        ports = policy.get("ports")
        if ports is not None and ports != "all":
            if isinstance(ports, list):
                for port in ports:
                    if (
                        not isinstance(port, int)
                        or not 1 <= port <= 65535
                    ):
                        errors.append(
                            f"network_policies[{i}]: invalid port "
                            f"{port} (must be 1-65535)"
                        )
            else:
                errors.append(
                    f"network_policies[{i}]: ports must be a list "
                    f"or 'all'"
                )
        protocol = policy.get("protocol")
        if protocol is not None and protocol not in ("tcp", "udp"):
            errors.append(
                f"network_policies[{i}]: protocol must be 'tcp' or "
                f"'udp', got '{protocol}'"
            )
        bidirectional = policy.get("bidirectional")
        if bidirectional is not None and not isinstance(
            bidirectional, bool
        ):
            errors.append(
                f"network_policies[{i}]: bidirectional must be a "
                f"boolean, got {type(bidirectional).__name__}"
            )


def _validate_ai_access(
    infra, errors, g, ai_access_policy, domain_names,
):
    """Validate exclusive AI access policy constraints."""
    if ai_access_policy != "exclusive":
        return

    ai_access_default = g.get("ai_access_default")
    if ai_access_default is None:
        errors.append(
            "global.ai_access_default is required when "
            "ai_access_policy is 'exclusive'"
        )
    elif ai_access_default == "ai-tools":
        errors.append(
            "global.ai_access_default cannot be 'ai-tools' "
            "(must be a client domain)"
        )
    elif ai_access_default not in domain_names:
        errors.append(
            f"global.ai_access_default '{ai_access_default}' "
            f"is not a known domain"
        )

    if "ai-tools" not in domain_names:
        errors.append(
            "ai_access_policy is 'exclusive' but no 'ai-tools' "
            "domain exists"
        )

    ai_tools_policies = [
        p
        for p in (infra.get("network_policies") or [])
        if isinstance(p, dict) and p.get("to") == "ai-tools"
    ]
    if len(ai_tools_policies) > 1:
        errors.append(
            f"ai_access_policy is 'exclusive' but "
            f"{len(ai_tools_policies)} network_policies target "
            f"ai-tools (max 1 allowed)"
        )
