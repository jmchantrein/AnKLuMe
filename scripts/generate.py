#!/usr/bin/env python3
"""PSOT Generator — generates Ansible file tree from infra.yml."""

import argparse
import re
import sys
from pathlib import Path

import yaml

MANAGED_BEGIN = "# === MANAGED BY infra.yml ==="
MANAGED_END = "# === END MANAGED ==="
MANAGED_NOTICE = "# Do not edit this section — it will be overwritten by `make sync`"
MANAGED_RE = re.compile(re.escape(MANAGED_BEGIN) + r".*?" + re.escape(MANAGED_END), re.DOTALL)


class _Dumper(yaml.SafeDumper):
    """YAML dumper: None as empty, preserves insertion order, proper list indent."""

    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


_Dumper.add_representer(type(None), lambda d, _: d.represent_scalar("tag:yaml.org,2002:null", ""))


def _yaml(data):
    return yaml.dump(data, Dumper=_Dumper, default_flow_style=False, sort_keys=False, allow_unicode=True)


def load_infra(path):
    """Load infra.yml and return parsed dict."""
    with open(path) as f:
        return yaml.safe_load(f)


def validate(infra):
    """Validate infra.yml constraints. Returns list of error strings (empty = OK)."""
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
    gpu_instances = []  # Track machines with GPU access

    valid_types = ("lxc", "vm")
    valid_gpu_policies = ("exclusive", "shared")
    valid_firewall_modes = ("host", "vm")
    firewall_mode = g.get("firewall_mode", "host")

    if gpu_policy not in valid_gpu_policies:
        errors.append(f"global.gpu_policy must be 'exclusive' or 'shared', got '{gpu_policy}'")
    if firewall_mode not in valid_firewall_modes:
        errors.append(f"global.firewall_mode must be 'host' or 'vm', got '{firewall_mode}'")

    for dname, domain in domains.items():
        if not re.match(r"^[a-z0-9][a-z0-9-]*$", dname):
            errors.append(f"Domain '{dname}': invalid name (lowercase alphanumeric + hyphen)")
        sid = domain.get("subnet_id")
        if sid is None:
            errors.append(f"Domain '{dname}': missing subnet_id")
        elif not isinstance(sid, int) or not 0 <= sid <= 254:
            errors.append(f"Domain '{dname}': subnet_id must be 0-254, got {sid}")
        elif sid in subnet_ids:
            errors.append(f"Domain '{dname}': subnet_id {sid} already used by '{subnet_ids[sid]}'")
        else:
            subnet_ids[sid] = dname

        domain_eph = domain.get("ephemeral")
        if domain_eph is not None and not isinstance(domain_eph, bool):
            errors.append(f"Domain '{dname}': ephemeral must be a boolean, got {type(domain_eph).__name__}")

        domain_profiles = domain.get("profiles") or {}
        domain_profile_names = set(domain_profiles)
        for mname, machine in (domain.get("machines") or {}).items():
            if mname in all_machines:
                errors.append(f"Machine '{mname}': duplicate (already in '{all_machines[mname]}')")
            else:
                all_machines[mname] = dname

            # Validate instance type
            mtype = machine.get("type", "lxc")
            if mtype not in valid_types:
                errors.append(f"Machine '{mname}': type must be 'lxc' or 'vm', got '{mtype}'")

            # Track GPU instances (direct flag or profile with gpu device)
            has_gpu = machine.get("gpu", False)
            if not has_gpu:
                for pname in machine.get("profiles") or []:
                    if pname in domain_profiles:
                        pdevices = domain_profiles[pname].get("devices") or {}
                        if any(d.get("type") == "gpu" for d in pdevices.values()):
                            has_gpu = True
                            break
            if has_gpu:
                gpu_instances.append(mname)

            ip = machine.get("ip")
            if ip:
                if ip in all_ips:
                    errors.append(f"Machine '{mname}': IP {ip} already used by '{all_ips[ip]}'")
                else:
                    all_ips[ip] = mname
                if sid is not None and not ip.startswith(f"{base_subnet}.{sid}."):
                    errors.append(f"Machine '{mname}': IP {ip} not in subnet {base_subnet}.{sid}.0/24")
            machine_eph = machine.get("ephemeral")
            if machine_eph is not None and not isinstance(machine_eph, bool):
                errors.append(f"Machine '{mname}': ephemeral must be a boolean, got {type(machine_eph).__name__}")
            for p in machine.get("profiles") or []:
                if p != "default" and p not in domain_profile_names:
                    errors.append(f"Machine '{mname}': profile '{p}' not defined in domain '{dname}'")

    # GPU policy enforcement (ADR-018)
    if len(gpu_instances) > 1 and gpu_policy == "exclusive":
        errors.append(
            f"GPU policy is 'exclusive' but {len(gpu_instances)} instances have GPU access: "
            f"{', '.join(gpu_instances)}. Set global.gpu_policy: shared to allow this."
        )

    return errors


def get_warnings(infra):
    """Return non-fatal warnings about the infra configuration."""
    warnings = []
    g = infra.get("global", {})
    gpu_policy = g.get("gpu_policy", "exclusive")
    domains = infra.get("domains") or {}
    gpu_instances = []

    for domain in domains.values():
        domain_profiles = domain.get("profiles") or {}
        for mname, machine in (domain.get("machines") or {}).items():
            has_gpu = machine.get("gpu", False)
            if not has_gpu:
                for pname in machine.get("profiles") or []:
                    if pname in domain_profiles:
                        pdevices = domain_profiles[pname].get("devices") or {}
                        if any(d.get("type") == "gpu" for d in pdevices.values()):
                            has_gpu = True
                            break
            if has_gpu:
                gpu_instances.append(mname)

    if len(gpu_instances) > 1 and gpu_policy == "shared":
        warnings.append(
            f"GPU policy is 'shared': {len(gpu_instances)} instances share GPU access "
            f"({', '.join(gpu_instances)}). No VRAM isolation on consumer GPUs."
        )

    return warnings


def enrich_infra(infra):
    """Enrich infra dict with auto-generated resources.

    Called after validate() and before generate(). Mutates infra in place.
    Currently handles: auto-creation of sys-firewall VM when firewall_mode is 'vm'.
    """
    g = infra.get("global", {})
    firewall_mode = g.get("firewall_mode", "host")
    if firewall_mode != "vm":
        return

    domains = infra.get("domains") or {}

    # Check if sys-firewall already exists in any domain (user override)
    for domain in domains.values():
        for mname in (domain.get("machines") or {}):
            if mname == "sys-firewall":
                return

    # Require admin domain
    if "admin" not in domains:
        print("ERROR: firewall_mode is 'vm' but no 'admin' domain exists. "
              "Cannot auto-create sys-firewall.", file=sys.stderr)
        sys.exit(1)

    admin_domain = domains["admin"]
    base_subnet = g.get("base_subnet", "10.100")
    admin_subnet_id = admin_domain.get("subnet_id", 0)

    sys_fw = {
        "description": "Centralized firewall VM (auto-created by generator)",
        "type": "vm",
        "ip": f"{base_subnet}.{admin_subnet_id}.253",
        "config": {
            "limits.cpu": "2",
            "limits.memory": "2GiB",
        },
        "roles": ["base_system", "firewall_router"],
        "ephemeral": False,
    }

    if "machines" not in admin_domain or admin_domain["machines"] is None:
        admin_domain["machines"] = {}
    admin_domain["machines"]["sys-firewall"] = sys_fw

    print("INFO: firewall_mode is 'vm' — auto-created sys-firewall in admin domain "
          f"(ip: {sys_fw['ip']})", file=sys.stderr)


def extract_all_images(infra):
    """Collect all unique OS image references from infra.yml.

    Scans every machine's os_image (falling back to global.default_os_image)
    and returns a sorted list of unique image references.
    Used to populate incus_all_images in group_vars/all.yml for the
    incus_images pre-download role.
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
    return f"{MANAGED_BEGIN}\n{MANAGED_NOTICE}\n{content_yaml.rstrip()}\n{MANAGED_END}"


def _write_managed(filepath, content_dict, dry_run=False):
    """Write or update a file, replacing only the managed section."""
    filepath = Path(filepath)
    block = _managed_block(_yaml(content_dict))

    if filepath.exists():
        existing = filepath.read_text()
        if MANAGED_RE.search(existing):
            new_content = MANAGED_RE.sub(block, existing)
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
    written = []

    # group_vars/all.yml
    # Connection params stored as psot_* (informational only).
    # They must NOT be named ansible_connection / ansible_user because
    # inventory variables override play-level keywords (Ansible precedence).
    all_images = extract_all_images(infra)
    all_vars = {k: v for k, v in {
        "project_name": infra.get("project_name"),
        "base_subnet": g.get("base_subnet", "10.100"),
        "default_os_image": g.get("default_os_image"),
        "psot_default_connection": g.get("default_connection"),
        "psot_default_user": g.get("default_user"),
        "incus_all_images": all_images if all_images else None,
    }.items() if v is not None}
    fp, _ = _write_managed(base / "group_vars" / "all.yml", all_vars, dry_run)
    written.append(fp)

    for dname, domain in domains.items():
        machines = domain.get("machines") or {}
        sid = domain.get("subnet_id")
        bs = g.get("base_subnet", "10.100")

        # inventory/<domain>.yml
        hosts = {}
        for mname, m in machines.items():
            hosts[mname] = {"ansible_host": m["ip"]} if m.get("ip") else None
        inv = {"all": {"children": {dname: {"hosts": hosts or None}}}}
        fp, _ = _write_managed(base / "inventory" / f"{dname}.yml", inv, dry_run)
        written.append(fp)

        # group_vars/<domain>.yml
        domain_ephemeral = domain.get("ephemeral", False)
        gvars = {k: v for k, v in {
            "domain_name": dname,
            "domain_description": domain.get("description", ""),
            "domain_ephemeral": domain_ephemeral,
            "incus_project": dname,
            "incus_network": {"name": f"net-{dname}", "subnet": f"{bs}.{sid}.0/24", "gateway": f"{bs}.{sid}.254"},
            "subnet_id": sid,
        }.items() if v is not None}
        if domain.get("profiles"):
            gvars["incus_profiles"] = domain["profiles"]
        fp, _ = _write_managed(base / "group_vars" / f"{dname}.yml", gvars, dry_run)
        written.append(fp)

        # host_vars/<machine>.yml
        for mname, m in machines.items():
            machine_eph = m.get("ephemeral")
            instance_ephemeral = machine_eph if machine_eph is not None else domain_ephemeral
            hvars = {k: v for k, v in {
                "instance_name": mname,
                "instance_type": m.get("type", "lxc"),
                "instance_description": m.get("description", ""),
                "instance_domain": dname,
                "instance_ephemeral": instance_ephemeral,
                "instance_os_image": m.get("os_image", g.get("default_os_image")),
                "instance_ip": m.get("ip"),
                "instance_gpu": m.get("gpu"),
                "instance_profiles": m.get("profiles"),
                "instance_config": m.get("config"),
                "instance_devices": m.get("devices"),
                "instance_storage_volumes": m.get("storage_volumes"),
                "instance_roles": m.get("roles"),
            }.items() if v is not None}
            fp, _ = _write_managed(base / "host_vars" / f"{mname}.yml", hvars, dry_run)
            written.append(fp)

    return written


def detect_orphans(infra, base_dir):
    """Return orphan files as list of (filepath, is_protected) tuples.

    Protected orphans (ephemeral=false) should be reported but never auto-deleted.
    """
    base = Path(base_dir)
    domains = infra.get("domains") or {}
    domain_names = set(domains)
    machine_names = {m for d in domains.values() for m in (d.get("machines") or {})}

    # Build protection map from last known state in files
    protected_domains = set()
    protected_machines = set()
    for dname, domain in domains.items():
        domain_eph = domain.get("ephemeral", False)
        if not domain_eph:
            protected_domains.add(dname)
        for mname, machine in (domain.get("machines") or {}).items():
            machine_eph = machine.get("ephemeral")
            resolved = machine_eph if machine_eph is not None else domain_eph
            if not resolved:
                protected_machines.add(mname)

    orphans = []

    for subdir, valid_names in [("inventory", domain_names), ("group_vars", domain_names | {"all"})]:
        d = base / subdir
        if d.exists():
            for f in d.glob("*.yml"):
                if f.stem not in valid_names:
                    # Check if the orphan file corresponds to a previously protected domain
                    is_protected = _is_orphan_protected(f)
                    orphans.append((f, is_protected))

    hv = base / "host_vars"
    if hv.exists():
        for f in hv.glob("*.yml"):
            if f.stem not in machine_names:
                is_protected = _is_orphan_protected(f)
                orphans.append((f, is_protected))

    return orphans


def _is_orphan_protected(filepath):
    """Check if an orphan file contains ephemeral: false (protected)."""
    try:
        content = Path(filepath).read_text()
        data = yaml.safe_load(content)
        if not isinstance(data, dict):
            return False
        # Check domain-level or instance-level ephemeral
        for key in ("domain_ephemeral", "instance_ephemeral"):
            if key in data:
                return not data[key]
        # Default: not protected (no ephemeral info found)
        return False
    except Exception:
        return False


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate Ansible files from infra.yml")
    parser.add_argument("infra_file", help="Path to infra.yml")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--clean-orphans", action="store_true", help="Remove orphan files")
    parser.add_argument("--base-dir", default=".", help="Output base directory")
    args = parser.parse_args(argv)

    infra = load_infra(args.infra_file)
    errors = validate(infra)
    if errors:
        print("Validation errors:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)

    enrich_infra(infra)

    warnings = get_warnings(infra)
    for w in warnings:
        print(f"WARNING: {w}", file=sys.stderr)

    domains = infra.get("domains") or {}
    if not domains:
        print("No domains defined. Nothing to generate.")
        return

    prefix = "[DRY-RUN] " if args.dry_run else ""
    print(f"{prefix}Generating files for {len(domains)} domain(s)...")
    written = generate(infra, args.base_dir, args.dry_run)
    for fp in written:
        print(f"  {prefix}{'Would write' if args.dry_run else 'Written'}: {fp}")

    orphans = detect_orphans(infra, args.base_dir)
    if orphans:
        print(f"\nOrphan files ({len(orphans)}):")
        for filepath, is_protected in orphans:
            if is_protected:
                print(f"  PROTECTED (ephemeral=false): {filepath} — manual removal required")
            else:
                print(f"  ORPHAN: {filepath}")
        if args.clean_orphans and not args.dry_run:
            for filepath, is_protected in orphans:
                if is_protected:
                    print(f"  Skipped (protected): {filepath}")
                else:
                    Path(filepath).unlink()
                    print(f"  Deleted: {filepath}")

    if not args.dry_run:
        print("\nDone. Run `make lint` to validate.")


if __name__ == "__main__":
    main()
