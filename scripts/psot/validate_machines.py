"""Validation of machine definitions (IP, fields)."""

import re

from psot.validate_persist import _validate_persistent_data


def _validate_machine(
    mname, machine, dname, errors, g, base_subnet, sid,
    has_addressing, computed_addressing, all_machines,
    all_ips, valid_types, domain_profile_names,
    vm_nested, yolo,
):
    """Validate a single machine definition."""
    if not re.match(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", mname):
        errors.append(
            f"Machine '{mname}': invalid name "
            f"(lowercase alphanumeric + hyphen, no trailing hyphen)"
        )
    if mname in all_machines:
        errors.append(
            f"Machine '{mname}': duplicate "
            f"(already in '{all_machines[mname]}')"
        )
    else:
        all_machines[mname] = dname
    mtype = machine.get("type", "lxc")
    if mtype not in valid_types:
        errors.append(
            f"Machine '{mname}': type must be 'lxc' or 'vm', "
            f"got '{mtype}'"
        )
    # Privileged LXC policy (ADR-020)
    mconfig = machine.get("config") or {}
    is_privileged = (
        str(mconfig.get("security.privileged", "false")).lower()
        == "true"
    )
    if is_privileged and mtype == "lxc" and vm_nested is False:
        if yolo:
            pass  # YOLO mode: warnings handled in get_warnings()
        else:
            errors.append(
                f"Machine '{mname}': security.privileged=true on "
                f"LXC is forbidden when vm_nested=false (no VM in "
                f"parent chain). Use a VM or enable --YOLO to bypass."
            )
    _validate_machine_ip(
        mname, machine, dname, errors, g, base_subnet, sid,
        has_addressing, computed_addressing, all_ips,
    )
    _validate_machine_fields(
        mname, machine, dname, errors, domain_profile_names,
    )
    _validate_persistent_data(mname, machine, errors)


def _validate_machine_ip(
    mname, machine, dname, errors, g, base_subnet, sid,
    has_addressing, computed_addressing, all_ips,
):
    """Validate machine IP address."""
    ip = machine.get("ip")
    if not ip:
        return
    if ip in all_ips:
        errors.append(
            f"Machine '{mname}': IP {ip} already used "
            f"by '{all_ips[ip]}'"
        )
    else:
        all_ips[ip] = mname
    if has_addressing and dname in computed_addressing:
        info = computed_addressing[dname]
        addr_cfg = g["addressing"]
        bo = addr_cfg.get("base_octet", 10)
        expected_prefix = (
            f"{bo}.{info['second_octet']}.{info['domain_seq']}."
        )
        if not ip.startswith(expected_prefix):
            errors.append(
                f"Machine '{mname}': IP {ip} not in subnet "
                f"{expected_prefix}0/24"
            )
    elif (
        not has_addressing
        and sid is not None
        and not ip.startswith(f"{base_subnet}.{sid}.")
    ):
        errors.append(
            f"Machine '{mname}': IP {ip} not in subnet "
            f"{base_subnet}.{sid}.0/24"
        )


def _validate_machine_fields(
    mname, machine, dname, errors, domain_profile_names,
):
    """Validate machine scalar fields."""
    machine_eph = machine.get("ephemeral")
    if machine_eph is not None and not isinstance(machine_eph, bool):
        errors.append(
            f"Machine '{mname}': ephemeral must be a boolean, "
            f"got {type(machine_eph).__name__}"
        )
    for p in machine.get("profiles") or []:
        if p != "default" and p not in domain_profile_names:
            errors.append(
                f"Machine '{mname}': profile '{p}' not defined "
                f"in domain '{dname}'"
            )
    boot_autostart = machine.get("boot_autostart")
    if boot_autostart is not None and not isinstance(
        boot_autostart, bool
    ):
        errors.append(
            f"Machine '{mname}': boot_autostart must be a boolean, "
            f"got {type(boot_autostart).__name__}"
        )
    boot_priority = machine.get("boot_priority")
    if boot_priority is not None and (
        isinstance(boot_priority, bool)
        or not isinstance(boot_priority, int)
        or not 0 <= boot_priority <= 100
    ):
        errors.append(
            f"Machine '{mname}': boot_priority must be an integer "
            f"0-100, got {boot_priority}"
        )
    snap_sched = machine.get("snapshots_schedule")
    if snap_sched is not None and (
        not isinstance(snap_sched, str)
        or not re.match(r"^(\S+\s+){4}\S+$", snap_sched)
    ):
        errors.append(
            f"Machine '{mname}': snapshots_schedule must be a cron "
            f"expression (5 fields), got '{snap_sched}'"
        )
    snap_expiry = machine.get("snapshots_expiry")
    if snap_expiry is not None and (
        not isinstance(snap_expiry, str)
        or not re.match(r"^\d+[dhm]$", snap_expiry)
    ):
        errors.append(
            f"Machine '{mname}': snapshots_expiry must be a "
            f"duration (e.g., '30d', '24h', '60m'), "
            f"got '{snap_expiry}'"
        )
    weight = machine.get("weight")
    if weight is not None and (
        isinstance(weight, bool)
        or not isinstance(weight, int)
        or weight < 1
    ):
        errors.append(
            f"Machine '{mname}': weight must be a positive "
            f"integer, got {weight}"
        )
