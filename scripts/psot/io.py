"""Loading infra.yml and orphan detection."""

import sys
from pathlib import Path

import yaml


def load_infra(path):
    """Load infra.yml (file) or infra/ (directory) and return parsed dict.

    Directory mode merges: base.yml + domains/*.yml + policies.yml.
    Auto-detects format based on whether path is a file or directory.
    """
    p = Path(path)

    if p.is_file():
        with open(p) as f:
            return yaml.safe_load(f)

    if p.is_dir():
        return _load_infra_dir(p)

    # Path does not exist -- try both conventions
    yml_path = (
        Path(str(p).removesuffix("/") + ".yml")
        if not str(p).endswith(".yml")
        else p
    )
    dir_path = (
        Path(str(p).removesuffix(".yml"))
        if str(p).endswith(".yml")
        else p
    )

    if yml_path.is_file():
        with open(yml_path) as f:
            return yaml.safe_load(f)
    if dir_path.is_dir():
        return _load_infra_dir(dir_path)

    # Fall back to original behavior (will raise FileNotFoundError)
    with open(path) as f:
        return yaml.safe_load(f)


def _load_infra_dir(dirpath):
    """Load infra/ directory: base.yml + domains/*.yml + policies.yml."""
    dirpath = Path(dirpath)
    base_path = dirpath / "base.yml"
    if not base_path.exists():
        raise ValueError(
            f"{base_path} not found in infra directory."
        )

    with open(base_path) as f:
        infra = yaml.safe_load(f) or {}

    # Merge domain files
    domains_dir = dirpath / "domains"
    if domains_dir.is_dir():
        infra.setdefault("domains", {})
        for domain_file in sorted(domains_dir.glob("*.yml")):
            with open(domain_file) as f:
                domain_data = yaml.safe_load(f) or {}
            for dname, dconfig in domain_data.items():
                if dname in infra["domains"]:
                    print(
                        f"WARNING: Domain '{dname}' in "
                        f"{domain_file.name} overrides existing "
                        f"definition.",
                        file=sys.stderr,
                    )
                infra["domains"][dname] = dconfig

    # Merge policies
    policies_path = dirpath / "policies.yml"
    if policies_path.exists():
        with open(policies_path) as f:
            policies_data = yaml.safe_load(f) or {}
        if "network_policies" in policies_data:
            infra["network_policies"] = policies_data[
                "network_policies"
            ]

    return infra


def detect_orphans(infra, base_dir):
    """Return orphan files as list of (filepath, is_protected) tuples.

    Protected orphans (ephemeral=false) should be reported but never
    auto-deleted.
    """
    base = Path(base_dir)
    domains = infra.get("domains") or {}
    domain_names = set(domains)
    machine_names = {
        m
        for d in domains.values()
        for m in (d.get("machines") or {})
    }

    orphans = []

    for subdir, valid_names in [
        ("inventory", domain_names),
        ("group_vars", domain_names | {"all"}),
    ]:
        d = base / subdir
        if d.exists():
            for f in d.glob("*.yml"):
                if f.stem not in valid_names:
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
