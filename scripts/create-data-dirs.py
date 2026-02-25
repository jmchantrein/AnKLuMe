#!/usr/bin/env python3
"""Create host directories for persistent_data declared in infra.yml (ADR-041)."""

import sys
from pathlib import Path

import yaml


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <infra.yml|infra/>", file=sys.stderr)
        sys.exit(1)

    infra_path = Path(sys.argv[1])
    if infra_path.is_dir():
        base_path = infra_path / "base.yml"
        if not base_path.exists():
            print(f"ERROR: {base_path} not found", file=sys.stderr)
            sys.exit(1)
        with open(base_path) as f:
            infra = yaml.safe_load(f) or {}
    else:
        with open(infra_path) as f:
            infra = yaml.safe_load(f) or {}

    g = infra.get("global", {})
    pd_base = g.get("persistent_data_base", "/srv/anklume/data")
    domains = infra.get("domains") or {}

    created = []
    for dname, domain in domains.items():
        for mname, machine in (domain.get("machines") or {}).items():
            pd = machine.get("persistent_data")
            if not pd or not isinstance(pd, dict):
                continue
            for vname in pd:
                source = f"{pd_base}/{dname}/{mname}/{vname}"
                p = Path(source)
                if not p.exists():
                    p.mkdir(parents=True, exist_ok=True)
                    created.append(str(p))
                    print(f"  Created: {p}")
                else:
                    print(f"  Exists:  {p}")

    if not created and not any(
        m.get("persistent_data") for d in domains.values() for m in (d.get("machines") or {}).values()
    ):
        print("No persistent_data defined.")
    elif created:
        print(f"\n{len(created)} director(y|ies) created.")
    else:
        print("\nAll directories already exist.")


if __name__ == "__main__":
    main()
