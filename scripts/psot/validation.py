"""Validation of infra.yml constraints — hub module.

Delegates to sub-validators for domain, policy, and infra-level checks.
"""

import sys

from psot.addressing import _compute_addressing
from psot.validate_domains import _validate_domains
from psot.validate_infra import (
    _validate_host_subnets,
    _validate_resource_policy,
)
from psot.validate_policies import (
    _validate_ai_access,
    _validate_network_policies,
)
from psot.validate_volumes import (
    _validate_persistent_data_collisions,
    _validate_shared_volumes,
)


def _resolve(name):
    """Late-bind a function via ``generate`` module for monkeypatch compat."""
    gen = sys.modules.get("generate")
    if gen and hasattr(gen, name):
        return getattr(gen, name)
    # Fallback: resolve from the psot sub-modules directly
    import psot  # noqa: PLC0415

    return getattr(psot, name)


def _collect_gpu_instances(infra):
    """Collect machine names that have GPU access."""
    gpu_instances = []
    for domain in (infra.get("domains") or {}).values():
        domain_profiles = domain.get("profiles") or {}
        for mname, machine in (
            domain.get("machines") or {}
        ).items():
            has_gpu = machine.get("gpu", False)
            if not has_gpu:
                for pname in machine.get("profiles") or []:
                    if pname in domain_profiles:
                        pdevices = (
                            domain_profiles[pname].get("devices")
                            or {}
                        )
                        if any(
                            d.get("type") == "gpu"
                            for d in pdevices.values()
                        ):
                            has_gpu = True
                            break
            if has_gpu:
                gpu_instances.append(mname)
    return gpu_instances


def validate(infra, *, check_host_subnets=True):
    """Validate infra.yml constraints. Returns list of errors."""
    errors = []
    for key in ("project_name", "global", "domains"):
        if key not in infra:
            errors.append(f"Missing required key: {key}")
    if errors:
        return errors

    domains = infra.get("domains") or {}
    g = infra.get("global", {})
    base_subnet = g.get("base_subnet", "10.100")
    gpu_policy = g.get("gpu_policy", "exclusive")
    subnet_ids, all_machines, all_ips = {}, {}, {}

    # Addressing mode detection (ADR-038)
    has_addressing = "addressing" in g
    computed_addressing = {}
    zone_subnet_ids = {}
    if has_addressing:
        addr_cfg = g["addressing"]
        if not isinstance(addr_cfg, dict):
            errors.append("global.addressing must be a mapping")
        else:
            base_octet = addr_cfg.get("base_octet", 10)
            if base_octet != 10:
                errors.append(
                    f"global.addressing.base_octet must be 10 "
                    f"(only RFC 1918 /8), got {base_octet}"
                )
            zone_base = addr_cfg.get("zone_base", 100)
            if (
                not isinstance(zone_base, int)
                or not 0 <= zone_base <= 245
            ):
                errors.append(
                    f"global.addressing.zone_base must be 0-245, "
                    f"got {zone_base}"
                )
            zone_step = addr_cfg.get("zone_step", 10)
            if not isinstance(zone_step, int) or zone_step < 1:
                errors.append(
                    f"global.addressing.zone_step must be a "
                    f"positive integer, got {zone_step}"
                )
            computed_addressing = _compute_addressing(infra)

    valid_types = ("lxc", "vm")
    valid_gpu_policies = ("exclusive", "shared")
    valid_firewall_modes = ("host", "vm")
    firewall_mode = g.get("firewall_mode", "host")
    vm_nested = _resolve("_read_vm_nested")()
    yolo = _resolve("_read_yolo")()

    nesting_prefix = g.get("nesting_prefix")
    if nesting_prefix is not None and not isinstance(
        nesting_prefix, bool
    ):
        errors.append(
            f"global.nesting_prefix must be a boolean, "
            f"got {type(nesting_prefix).__name__}"
        )

    if gpu_policy not in valid_gpu_policies:
        errors.append(
            f"global.gpu_policy must be 'exclusive' or 'shared', "
            f"got '{gpu_policy}'"
        )
    if firewall_mode not in valid_firewall_modes:
        errors.append(
            f"global.firewall_mode must be 'host' or 'vm', "
            f"got '{firewall_mode}'"
        )

    ai_access_policy = g.get("ai_access_policy", "open")
    valid_ai_policies = ("exclusive", "open")
    if ai_access_policy not in valid_ai_policies:
        errors.append(
            f"global.ai_access_policy must be 'exclusive' or "
            f"'open', got '{ai_access_policy}'"
        )

    _validate_domains(
        domains, errors, g, base_subnet, has_addressing,
        computed_addressing, zone_subnet_ids, subnet_ids,
        all_machines, all_ips, valid_types, vm_nested, yolo,
    )

    # GPU policy enforcement (ADR-018)
    gpu_instances = _collect_gpu_instances(infra)
    if len(gpu_instances) > 1 and gpu_policy == "exclusive":
        errors.append(
            f"GPU policy is 'exclusive' but "
            f"{len(gpu_instances)} instances have GPU access: "
            f"{', '.join(gpu_instances)}. "
            f"Set global.gpu_policy: shared to allow this."
        )

    domain_names = set(domains)
    _validate_network_policies(
        infra, errors, domain_names, all_machines,
    )
    _validate_ai_access(
        infra, errors, g, ai_access_policy, domain_names,
    )

    # Base path validations
    sv_base = g.get("shared_volumes_base")
    if sv_base is not None and (
        not isinstance(sv_base, str) or not sv_base.startswith("/")
    ):
        errors.append(
            "global.shared_volumes_base must be an absolute path"
        )
    pd_base = g.get("persistent_data_base")
    if pd_base is not None and (
        not isinstance(pd_base, str) or not pd_base.startswith("/")
    ):
        errors.append(
            "global.persistent_data_base must be an absolute path"
        )

    sv_mount_paths = _validate_shared_volumes(
        infra, errors, domains, all_machines,
    )
    _validate_persistent_data_collisions(
        domains, errors, sv_mount_paths,
    )
    _validate_resource_policy(g, errors)
    _validate_host_subnets(
        errors, g, has_addressing, computed_addressing,
        subnet_ids, base_subnet, check_host_subnets,
        _resolve,
    )

    return errors
