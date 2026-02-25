"""Host vars generation for individual machines."""


def _generate_hostvars(
    machines, dname, domain_ephemeral, infra, g, prefix,
    base, dry_run, write_fn,
):
    """Generate host_vars/<machine>.yml for each machine. Returns paths."""
    written = []
    sv_devices_map = infra.get("_shared_volume_devices") or {}
    pd_devices_map = infra.get("_persistent_data_devices") or {}

    for mname, m in machines.items():
        machine_eph = m.get("ephemeral")
        instance_ephemeral = (
            machine_eph
            if machine_eph is not None
            else domain_ephemeral
        )

        # Merge devices: sv-* + pd-* + user
        user_devices = m.get("devices")
        sv_devs = sv_devices_map.get(mname)
        pd_devs = pd_devices_map.get(mname)
        merged_devices = {}
        if sv_devs:
            merged_devices.update(sv_devs)
        if pd_devs:
            merged_devices.update(pd_devs)
        if user_devices:
            merged_devices.update(user_devices)
        final_devices = (
            merged_devices if merged_devices else user_devices
        )

        hvars = {
            k: v
            for k, v in {
                "instance_name": f"{prefix}{mname}",
                "instance_type": m.get("type", "lxc"),
                "instance_description": m.get(
                    "description", ""
                ),
                "instance_domain": dname,
                "instance_ephemeral": instance_ephemeral,
                "instance_os_image": m.get(
                    "os_image", g.get("default_os_image")
                ),
                "instance_ip": m.get("ip"),
                "instance_gpu": m.get("gpu"),
                "instance_profiles": m.get("profiles"),
                "instance_config": m.get("config"),
                "instance_devices": final_devices,
                "instance_storage_volumes": m.get(
                    "storage_volumes"
                ),
                "instance_roles": m.get("roles"),
                "instance_boot_autostart": m.get(
                    "boot_autostart"
                ),
                "instance_boot_priority": m.get(
                    "boot_priority"
                ),
                "instance_snapshots_schedule": m.get(
                    "snapshots_schedule"
                ),
                "instance_snapshots_expiry": m.get(
                    "snapshots_expiry"
                ),
            }.items()
            if v is not None
        }
        fp, _ = write_fn(
            base / "host_vars" / f"{mname}.yml", hvars, dry_run
        )
        written.append(fp)

    return written
