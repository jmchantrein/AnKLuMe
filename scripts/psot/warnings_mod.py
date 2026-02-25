"""Non-fatal warning generation for the PSOT generator."""

import sys

from psot.validation import _collect_gpu_instances


def _resolve(name):
    """Look up a patchable function on the ``generate`` module.

    See psot.validation._resolve for rationale.
    """
    gen = sys.modules.get("generate")
    if gen and hasattr(gen, name):
        return getattr(gen, name)
    import psot  # noqa: PLC0415

    return getattr(psot, name)


def get_warnings(infra):
    """Return non-fatal warnings about the infra configuration."""
    warnings = []
    g = infra.get("global", {})
    gpu_policy = g.get("gpu_policy", "exclusive")
    domains = infra.get("domains") or {}
    gpu_instances = _collect_gpu_instances(infra)
    yolo = _resolve("_read_yolo")()
    vm_nested = _resolve("_read_vm_nested")()

    for domain in domains.values():
        for mname, machine in (domain.get("machines") or {}).items():
            # YOLO mode: privileged LXC warning instead of error
            mconfig = machine.get("config") or {}
            is_privileged = (
                str(
                    mconfig.get("security.privileged", "false")
                ).lower()
                == "true"
            )
            mtype = machine.get("type", "lxc")
            if (
                is_privileged
                and mtype == "lxc"
                and vm_nested is False
                and yolo
            ):
                warnings.append(
                    f"YOLO: Machine '{mname}' has "
                    f"security.privileged=true on LXC without VM "
                    f"isolation. This is unsafe for production."
                )

    if len(gpu_instances) > 1 and gpu_policy == "shared":
        warnings.append(
            f"GPU policy is 'shared': {len(gpu_instances)} instances "
            f"share GPU access ({', '.join(gpu_instances)}). "
            f"No VRAM isolation on consumer GPUs."
        )

    # Warn if network_policies reference disabled domains
    disabled_domains = {
        dname
        for dname, d in domains.items()
        if d.get("enabled", True) is False
    }
    if disabled_domains:
        for i, policy in enumerate(
            infra.get("network_policies") or []
        ):
            if not isinstance(policy, dict):
                continue
            for field in ("from", "to"):
                ref = policy.get(field)
                if ref in disabled_domains:
                    warnings.append(
                        f"network_policies[{i}]: '{field}: {ref}' "
                        f"references disabled domain '{ref}'"
                    )

    # Warn if openclaw_server role has no network path to an LLM backend
    all_machines = {}  # name -> domain_name
    openclaw_machines = []
    for dname, domain in domains.items():
        for mname, machine in (domain.get("machines") or {}).items():
            all_machines[mname] = dname
            roles = machine.get("roles") or []
            if "openclaw_server" in roles:
                openclaw_machines.append((mname, dname))

    if openclaw_machines:
        policies = infra.get("network_policies") or []
        for mname, dname in openclaw_machines:
            has_llm_access = False
            for policy in policies:
                if not isinstance(policy, dict):
                    continue
                pfrom = policy.get("from", "")
                if pfrom in (dname, mname):
                    has_llm_access = True
                    break
            if not has_llm_access:
                warnings.append(
                    f"Machine '{mname}' has role 'openclaw_server' "
                    f"but no network_policy grants access from "
                    f"domain '{dname}' to an LLM backend. Add a "
                    f"network_policy if AI access is needed."
                )

    return warnings
