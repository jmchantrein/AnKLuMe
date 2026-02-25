"""Volume enrichment — shared volumes and persistent data devices."""


def _enrich_shared_volumes(infra):
    """Resolve shared_volumes into per-machine disk devices.

    Builds infra['_shared_volume_devices']:
    {machine_name: {device_name: device_dict}}.
    Called from enrich_infra() after addressing enrichment.
    """
    shared_volumes = infra.get("shared_volumes")
    if not shared_volumes:
        return

    g = infra.get("global", {})
    sv_base = g.get("shared_volumes_base", "/srv/anklume/shares")
    domains = infra.get("domains") or {}

    # Build domain -> machine list mapping
    domain_machines = {}
    for dname, domain in domains.items():
        machines_in_domain = list(
            (domain.get("machines") or {}).keys()
        )
        domain_machines[dname] = machines_in_domain

    # Resolve consumers and build device map
    sv_devices = {}  # {machine_name: {device_name: device_dict}}

    for vname, vconfig in shared_volumes.items():
        if not isinstance(vconfig, dict):
            continue
        source = vconfig.get("source") or f"{sv_base}/{vname}"
        path = vconfig.get("path") or f"/shared/{vname}"
        shift = vconfig.get("shift", True)
        device_name = f"sv-{vname}"
        consumers = vconfig.get("consumers") or {}

        # First pass: collect domain-level defaults
        domain_access = {}  # domain_name -> access
        machine_access = {}  # machine_name -> access (overrides)
        for cname, access in consumers.items():
            if cname in domains:
                domain_access[cname] = access
            else:
                machine_access[cname] = access

        # Resolve to per-machine access
        resolved = {}  # machine_name -> access
        for dname, access in domain_access.items():
            for mname in domain_machines.get(dname, []):
                resolved[mname] = access
        # Machine-level overrides domain-level
        for mname, access in machine_access.items():
            resolved[mname] = access

        # Build device dict for each resolved machine
        for mname, access in resolved.items():
            device = {
                "type": "disk",
                "source": source,
                "path": path,
            }
            if shift:
                device["shift"] = "true"
            if access == "ro":
                device["readonly"] = "true"
            sv_devices.setdefault(mname, {})[device_name] = device

    infra["_shared_volume_devices"] = sv_devices


def _enrich_persistent_data(infra):
    """Resolve persistent_data into per-machine disk devices (ADR-041).

    Builds infra['_persistent_data_devices']:
    {machine_name: {device_name: device_dict}}.
    Called from enrich_infra() after shared_volumes enrichment.
    """
    g = infra.get("global", {})
    pd_base = g.get("persistent_data_base", "/srv/anklume/data")
    domains = infra.get("domains") or {}

    pd_devices = {}  # {machine_name: {device_name: device_dict}}

    for dname, domain in domains.items():
        for mname, machine in (
            domain.get("machines") or {}
        ).items():
            pd = machine.get("persistent_data")
            if not pd or not isinstance(pd, dict):
                continue
            for vname, vconfig in pd.items():
                if not isinstance(vconfig, dict):
                    continue
                path = vconfig.get("path")
                if not path:
                    continue
                source = f"{pd_base}/{dname}/{mname}/{vname}"
                readonly = vconfig.get("readonly", False)
                device_name = f"pd-{vname}"
                device = {
                    "type": "disk",
                    "source": source,
                    "path": path,
                    "shift": "true",
                }
                if readonly:
                    device["readonly"] = "true"
                pd_devices.setdefault(mname, {})[
                    device_name
                ] = device

    infra["_persistent_data_devices"] = pd_devices
