"""Ansible file generation from enriched infra data."""

from pathlib import Path

from psot.constants import MANAGED_BEGIN, MANAGED_END, MANAGED_NOTICE, MANAGED_RE
from psot.context import _get_nesting_prefix
from psot.gen_hostvars import _generate_hostvars
from psot.yaml_utils import _yaml


def extract_all_images(infra):
    """Collect all unique OS image references from infra.yml.

    Scans every machine's os_image (falling back to
    global.default_os_image) and returns a sorted list of unique image
    references.  Used to populate incus_all_images in
    group_vars/all.yml for the incus_images pre-download role.
    """
    g = infra.get("global", {})
    default_image = g.get("default_os_image")
    images = set()

    for domain in (infra.get("domains") or {}).values():
        for machine in (domain.get("machines") or {}).values():
            image = machine.get("os_image", default_image)
            if image:
                images.add(image)

    return sorted(images)


def _managed_block(content_yaml):
    return (
        f"{MANAGED_BEGIN}\n{MANAGED_NOTICE}\n"
        f"{content_yaml.rstrip()}\n{MANAGED_END}"
    )


def _write_managed(filepath, content_dict, dry_run=False):
    """Write or update a file, replacing only the managed section."""
    filepath = Path(filepath)
    block = _managed_block(_yaml(content_dict))

    if filepath.exists():
        existing = filepath.read_text()
        if MANAGED_RE.search(existing):
            new_content = MANAGED_RE.sub(block, existing, count=1)
        else:
            prefix = "" if existing.startswith("---") else "---\n"
            new_content = f"{prefix}{block}\n\n{existing}"
    else:
        new_content = f"---\n{block}\n\n# Your custom variables below:\n"

    if dry_run:
        return filepath, new_content
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(new_content)
    return filepath, new_content


def generate(infra, base_dir, dry_run=False):
    """Generate all Ansible files. Returns list of written file paths."""
    base = Path(base_dir)
    domains = infra.get("domains") or {}
    g = infra.get("global", {})
    prefix = _get_nesting_prefix(infra)
    written = []

    # group_vars/all.yml
    all_images = extract_all_images(infra)
    network_policies = infra.get("network_policies")
    has_addressing = "addressing" in g
    all_vars = {
        k: v
        for k, v in {
            "project_name": infra.get("project_name"),
            "addressing": (
                g.get("addressing") if has_addressing else None
            ),
            "base_subnet": (
                g.get("base_subnet", "10.100")
                if not has_addressing
                else None
            ),
            "default_os_image": g.get("default_os_image"),
            "psot_default_connection": g.get("default_connection"),
            "psot_default_user": g.get("default_user"),
            "incus_all_images": all_images if all_images else None,
            "network_policies": (
                network_policies if network_policies else None
            ),
        }.items()
        if v is not None
    }
    fp, _ = _write_managed(
        base / "group_vars" / "all.yml", all_vars, dry_run
    )
    written.append(fp)

    for dname, domain in domains.items():
        # Skip disabled domains
        if domain.get("enabled", True) is False:
            continue

        machines = domain.get("machines") or {}

        # Compute subnet/gateway from addressing or legacy base_subnet
        if (
            has_addressing
            and "_addressing" in infra
            and dname in infra["_addressing"]
        ):
            addr_info = infra["_addressing"][dname]
            addr_cfg = g["addressing"]
            bo = addr_cfg.get("base_octet", 10)
            so = addr_info["second_octet"]
            ds = addr_info["domain_seq"]
            subnet_str = f"{bo}.{so}.{ds}.0/24"
            gateway_str = f"{bo}.{so}.{ds}.254"
            sid = ds  # For subnet_id in group_vars
        else:
            sid = domain.get("subnet_id")
            bs = g.get("base_subnet", "10.100")
            subnet_str = f"{bs}.{sid}.0/24"
            gateway_str = f"{bs}.{sid}.254"

        # inventory/<domain>.yml
        hosts = {}
        for mname, m in machines.items():
            hosts[mname] = (
                {"ansible_host": m["ip"]} if m.get("ip") else None
            )
        inv = {
            "all": {"children": {dname: {"hosts": hosts or None}}}
        }
        fp, _ = _write_managed(
            base / "inventory" / f"{dname}.yml", inv, dry_run
        )
        written.append(fp)

        # group_vars/<domain>.yml
        domain_ephemeral = domain.get("ephemeral", False)
        ai_provider = domain.get("ai_provider", "local")
        ai_sanitize = domain.get("ai_sanitize")
        if ai_sanitize is None:
            ai_sanitize = ai_provider in ("cloud", "local-first")
        gvars = {
            k: v
            for k, v in {
                "domain_name": dname,
                "domain_description": domain.get(
                    "description", ""
                ),
                "domain_ephemeral": domain_ephemeral,
                "domain_trust_level": domain.get("trust_level"),
                "domain_ai_provider": ai_provider,
                "domain_ai_sanitize": ai_sanitize,
                "incus_project": f"{prefix}{dname}",
                "incus_network": {
                    "name": f"{prefix}net-{dname}",
                    "subnet": subnet_str,
                    "gateway": gateway_str,
                },
                "subnet_id": sid,
            }.items()
            if v is not None
        }
        if domain.get("profiles"):
            gvars["incus_profiles"] = domain["profiles"]
        fp, _ = _write_managed(
            base / "group_vars" / f"{dname}.yml", gvars, dry_run
        )
        written.append(fp)

        # host_vars/<machine>.yml
        written.extend(
            _generate_hostvars(
                machines, dname, domain_ephemeral, infra, g,
                prefix, base, dry_run, _write_managed,
            )
        )

    return written
