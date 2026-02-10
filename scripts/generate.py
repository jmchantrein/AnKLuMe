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
    base_subnet = infra.get("global", {}).get("base_subnet", "192.168")
    subnet_ids, all_machines, all_ips = {}, {}, {}

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

        domain_profiles = set(domain.get("profiles") or {})
        for mname, machine in (domain.get("machines") or {}).items():
            if mname in all_machines:
                errors.append(f"Machine '{mname}': duplicate (already in '{all_machines[mname]}')")
            else:
                all_machines[mname] = dname
            ip = machine.get("ip")
            if ip:
                if ip in all_ips:
                    errors.append(f"Machine '{mname}': IP {ip} already used by '{all_ips[ip]}'")
                else:
                    all_ips[ip] = mname
                if sid is not None and not ip.startswith(f"{base_subnet}.{sid}."):
                    errors.append(f"Machine '{mname}': IP {ip} not in subnet {base_subnet}.{sid}.0/24")
            for p in machine.get("profiles") or []:
                if p != "default" and p not in domain_profiles:
                    errors.append(f"Machine '{mname}': profile '{p}' not defined in domain '{dname}'")

    return errors


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
    all_vars = {k: v for k, v in {
        "project_name": infra.get("project_name"),
        "base_subnet": g.get("base_subnet", "192.168"),
        "default_os_image": g.get("default_os_image"),
        "default_connection": g.get("default_connection"),
        "default_user": g.get("default_user"),
    }.items() if v is not None}
    fp, _ = _write_managed(base / "group_vars" / "all.yml", all_vars, dry_run)
    written.append(fp)

    for dname, domain in domains.items():
        machines = domain.get("machines") or {}
        sid = domain.get("subnet_id")
        bs = g.get("base_subnet", "192.168")

        # inventory/<domain>.yml
        hosts = {}
        for mname, m in machines.items():
            hosts[mname] = {"ansible_host": m["ip"]} if m.get("ip") else None
        inv = {"all": {"children": {dname: {"hosts": hosts or None}}}}
        fp, _ = _write_managed(base / "inventory" / f"{dname}.yml", inv, dry_run)
        written.append(fp)

        # group_vars/<domain>.yml
        gvars = {k: v for k, v in {
            "domain_name": dname,
            "domain_description": domain.get("description", ""),
            "incus_project": dname,
            "incus_network": {"name": f"net-{dname}", "subnet": f"{bs}.{sid}.0/24", "gateway": f"{bs}.{sid}.1"},
            "subnet_id": sid,
            "ansible_connection": g.get("default_connection"),
            "ansible_user": g.get("default_user"),
        }.items() if v is not None}
        if domain.get("profiles"):
            gvars["incus_profiles"] = domain["profiles"]
        fp, _ = _write_managed(base / "group_vars" / f"{dname}.yml", gvars, dry_run)
        written.append(fp)

        # host_vars/<machine>.yml
        for mname, m in machines.items():
            hvars = {k: v for k, v in {
                "instance_name": mname,
                "instance_type": m.get("type", "lxc"),
                "instance_description": m.get("description", ""),
                "instance_domain": dname,
                "instance_os_image": m.get("os_image", g.get("default_os_image")),
                "instance_ip": m.get("ip"),
                "instance_gpu": m.get("gpu"),
                "instance_profiles": m.get("profiles"),
                "instance_config": m.get("config"),
                "instance_storage_volumes": m.get("storage_volumes"),
                "instance_roles": m.get("roles"),
            }.items() if v is not None}
            fp, _ = _write_managed(base / "host_vars" / f"{mname}.yml", hvars, dry_run)
            written.append(fp)

    return written


def detect_orphans(infra, base_dir):
    """Return file paths that exist on disk but no longer match infra.yml."""
    base = Path(base_dir)
    domains = infra.get("domains") or {}
    domain_names = set(domains)
    machine_names = {m for d in domains.values() for m in (d.get("machines") or {})}
    orphans = []

    for subdir, valid_names in [("inventory", domain_names), ("group_vars", domain_names | {"all"})]:
        d = base / subdir
        if d.exists():
            orphans.extend(f for f in d.glob("*.yml") if f.stem not in valid_names)

    hv = base / "host_vars"
    if hv.exists():
        orphans.extend(f for f in hv.glob("*.yml") if f.stem not in machine_names)
    return orphans


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
        for o in orphans:
            print(f"  ORPHAN: {o}")
        if args.clean_orphans and not args.dry_run:
            for o in orphans:
                Path(o).unlink()
                print(f"  Deleted: {o}")

    if not args.dry_run:
        print("\nDone. Run `make lint` to validate.")


if __name__ == "__main__":
    main()
