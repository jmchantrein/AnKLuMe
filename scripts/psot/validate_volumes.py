"""Validation of shared volumes and persistent data collisions."""

import re


def _validate_shared_volumes(infra, errors, domains, all_machines):
    """Validate shared_volumes section. Returns sv_mount_paths dict."""
    shared_volumes = infra.get("shared_volumes") or {}
    if shared_volumes and not isinstance(shared_volumes, dict):
        errors.append("shared_volumes must be a mapping")
        return {}

    domain_names = set(domains)
    sv_domain_machines = {}
    sv_machine_to_domain = {}
    for dname, domain in domains.items():
        machines_in_domain = list(
            (domain.get("machines") or {}).keys()
        )
        sv_domain_machines[dname] = machines_in_domain
        for mname in machines_in_domain:
            sv_machine_to_domain[mname] = dname

    sv_mount_paths = {}
    for vname, vconfig in shared_volumes.items():
        if not isinstance(vconfig, dict):
            errors.append(
                f"shared_volumes.{vname}: must be a mapping"
            )
            continue
        _validate_sv_fields(vname, vconfig, errors)
        consumers = vconfig.get("consumers")
        if consumers is None or not isinstance(consumers, dict):
            errors.append(
                f"shared_volumes.{vname}: consumers must be a "
                f"non-empty mapping"
            )
            continue
        if len(consumers) == 0:
            errors.append(
                f"shared_volumes.{vname}: consumers must be a "
                f"non-empty mapping"
            )
            continue
        device_name = f"sv-{vname}"
        path = vconfig.get("path")
        mount_path = path if path else f"/shared/{vname}"
        _validate_sv_consumers(
            vname, consumers, device_name, mount_path,
            errors, domain_names, all_machines,
            sv_domain_machines, sv_machine_to_domain,
            domains, sv_mount_paths,
        )

    return sv_mount_paths


def _validate_sv_fields(vname, vconfig, errors):
    """Validate shared_volume scalar fields."""
    if not re.match(
        r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", vname
    ):
        errors.append(
            f"shared_volumes.{vname}: invalid name "
            f"(lowercase alphanumeric + hyphen, no trailing hyphen)"
        )
    source = vconfig.get("source")
    if source is not None and (
        not isinstance(source, str) or not source.startswith("/")
    ):
        errors.append(
            f"shared_volumes.{vname}: source must be an absolute path"
        )
    path = vconfig.get("path")
    if path is not None and (
        not isinstance(path, str) or not path.startswith("/")
    ):
        errors.append(
            f"shared_volumes.{vname}: path must be an absolute path"
        )
    shift = vconfig.get("shift")
    if shift is not None and not isinstance(shift, bool):
        errors.append(
            f"shared_volumes.{vname}: shift must be a boolean, "
            f"got {type(shift).__name__}"
        )
    propagate = vconfig.get("propagate")
    if propagate is not None and not isinstance(propagate, bool):
        errors.append(
            f"shared_volumes.{vname}: propagate must be a "
            f"boolean, got {type(propagate).__name__}"
        )


def _validate_sv_consumers(
    vname, consumers, device_name, mount_path,
    errors, domain_names, all_machines,
    sv_domain_machines, sv_machine_to_domain,
    domains, sv_mount_paths,
):
    """Validate shared_volume consumers for collisions."""
    for cname, access in consumers.items():
        if access not in ("ro", "rw"):
            errors.append(
                f"shared_volumes.{vname}: consumer '{cname}' "
                f"access must be 'ro' or 'rw', got '{access}'"
            )
        if (
            cname not in domain_names
            and cname not in all_machines
        ):
            errors.append(
                f"shared_volumes.{vname}: consumer '{cname}' "
                f"is not a known domain or machine"
            )
        if cname in domain_names:
            resolved = sv_domain_machines.get(cname, [])
        elif cname in all_machines:
            resolved = [cname]
        else:
            resolved = []
        for mname in resolved:
            dname_for_m = sv_machine_to_domain.get(mname)
            if dname_for_m:
                m_devices = (
                    domains.get(dname_for_m, {})
                    .get("machines", {})
                    .get(mname, {})
                    .get("devices")
                    or {}
                )
                if device_name in m_devices:
                    errors.append(
                        f"shared_volumes.{vname}: device name "
                        f"'{device_name}' conflicts with existing "
                        f"device on machine '{mname}'"
                    )
            path_key = (mname, mount_path)
            if path_key in sv_mount_paths:
                errors.append(
                    f"shared_volumes.{vname}: duplicate mount "
                    f"path '{mount_path}' on machine '{mname}' "
                    f"(already used by volume "
                    f"'{sv_mount_paths[path_key]}')"
                )
            else:
                sv_mount_paths[path_key] = vname


def _validate_persistent_data_collisions(
    domains, errors, sv_mount_paths,
):
    """Check persistent_data paths don't collide with shared_volumes."""
    for _dname, domain in domains.items():
        for mname, machine in (domain.get("machines") or {}).items():
            pd = machine.get("persistent_data")
            if not pd or not isinstance(pd, dict):
                continue
            for vname, vconfig in pd.items():
                if not isinstance(vconfig, dict):
                    continue
                pd_path = vconfig.get("path")
                if pd_path:
                    path_key = (mname, pd_path)
                    if path_key in sv_mount_paths:
                        errors.append(
                            f"Machine '{mname}': "
                            f"persistent_data.{vname}: "
                            f"duplicate mount path '{pd_path}' "
                            f"(already used by shared_volume "
                            f"'{sv_mount_paths[path_key]}')"
                        )
