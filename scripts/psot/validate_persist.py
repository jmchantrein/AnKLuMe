"""Validation of persistent_data on individual machines."""

import re


def _validate_persistent_data(mname, machine, errors):
    """Validate persistent_data on a single machine."""
    pd = machine.get("persistent_data")
    if pd is None:
        return
    if not isinstance(pd, dict):
        errors.append(
            f"Machine '{mname}': persistent_data must be a mapping"
        )
        return
    user_devices = machine.get("devices") or {}
    for vname, vconfig in pd.items():
        if not isinstance(vconfig, dict):
            errors.append(
                f"Machine '{mname}': persistent_data.{vname} "
                f"must be a mapping"
            )
            continue
        if not re.match(
            r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", vname
        ):
            errors.append(
                f"Machine '{mname}': persistent_data.{vname}: "
                f"invalid name (lowercase alphanumeric + hyphen)"
            )
        pd_path = vconfig.get("path")
        if pd_path is None:
            errors.append(
                f"Machine '{mname}': persistent_data.{vname}: "
                f"path is required"
            )
        elif (
            not isinstance(pd_path, str)
            or not pd_path.startswith("/")
        ):
            errors.append(
                f"Machine '{mname}': persistent_data.{vname}: "
                f"path must be an absolute path"
            )
        pd_ro = vconfig.get("readonly")
        if pd_ro is not None and not isinstance(pd_ro, bool):
            errors.append(
                f"Machine '{mname}': persistent_data.{vname}: "
                f"readonly must be a boolean, "
                f"got {type(pd_ro).__name__}"
            )
        device_name = f"pd-{vname}"
        if device_name in user_devices:
            errors.append(
                f"Machine '{mname}': persistent_data.{vname}: "
                f"device name '{device_name}' collision with "
                f"existing device"
            )
