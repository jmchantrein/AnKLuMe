#!/usr/bin/env python3
"""Create host directories for shared_volumes declared in infra.yml."""

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
    sv_base = g.get("shared_volumes_base", "/srv/anklume/shares")
    shared_volumes = infra.get("shared_volumes") or {}

    if not shared_volumes:
        print("No shared_volumes defined.")
        return

    created = []
    for vname, vconfig in shared_volumes.items():
        if not isinstance(vconfig, dict):
            continue
        source = vconfig.get("source") or f"{sv_base}/{vname}"
        p = Path(source)
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True)
            created.append(str(p))
            print(f"  Created: {p}")
        else:
            print(f"  Exists:  {p}")

    if created:
        print(f"\n{len(created)} director(y|ies) created.")
    else:
        print("\nAll directories already exist.")


if __name__ == "__main__":
    main()
