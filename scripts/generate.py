#!/usr/bin/env python3
"""PSOT Generator — generates Ansible file tree from infra.yml.

This module is a thin wrapper around the ``psot`` package.  All logic
lives in ``psot/`` sub-modules; this file re-exports every public and
private symbol so that existing ``from generate import ...`` statements
continue to work without modification.
"""

import argparse
import sys
from pathlib import Path

# Ensure the psot package (sibling directory) is importable when
# running as ``python3 scripts/generate.py`` from any working directory.
_scripts_dir = str(Path(__file__).resolve().parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from psot import (  # noqa: F401, E402
    DEFAULT_TRUST_LEVEL,
    MANAGED_BEGIN,
    MANAGED_END,
    MANAGED_NOTICE,
    MANAGED_RE,
    ZONE_OFFSETS,
    _apply_memory_enforce,
    _auto_assign_ips,
    _collect_gpu_instances,
    _compute_addressing,
    _detect_host_resources,
    _detect_host_subnets,
    _Dumper,
    _enrich_addressing,
    _enrich_ai_access,
    _enrich_firewall,
    _enrich_persistent_data,
    _enrich_resources,
    _enrich_shared_volumes,
    _format_memory,
    _get_nesting_prefix,
    _is_orphan_protected,
    _load_infra_dir,
    _managed_block,
    _parse_memory_value,
    _read_absolute_level,
    _read_vm_nested,
    _read_yolo,
    _write_managed,
    _yaml,
    detect_orphans,
    enrich_infra,
    extract_all_images,
    generate,
    get_warnings,
    load_infra,
    validate,
)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate Ansible files from infra.yml"
    )
    parser.add_argument(
        "infra_file", help="Path to infra.yml or infra/ directory"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without writing",
    )
    parser.add_argument(
        "--clean-orphans",
        action="store_true",
        help="Remove orphan files",
    )
    parser.add_argument(
        "--base-dir", default=".", help="Output base directory"
    )
    args = parser.parse_args(argv)

    try:
        infra = load_infra(args.infra_file)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    errors = validate(infra)
    if errors:
        print("Validation errors:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)

    try:
        enrich_infra(infra)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # Re-validate after enrichment
    post_errors = validate(infra, check_host_subnets=False)
    if post_errors:
        print("Post-enrichment validation errors:", file=sys.stderr)
        for e in post_errors:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)

    warnings = get_warnings(infra)
    for w in warnings:
        print(f"WARNING: {w}", file=sys.stderr)

    domains = infra.get("domains") or {}
    if not domains:
        print("No domains defined. Nothing to generate.")
        return

    enabled_count = sum(
        1
        for d in domains.values()
        if d.get("enabled", True) is not False
    )
    prefix = "[DRY-RUN] " if args.dry_run else ""
    print(f"{prefix}Generating files for {enabled_count} domain(s)...")
    written = generate(infra, args.base_dir, args.dry_run)
    for fp in written:
        print(
            f"  {prefix}"
            f"{'Would write' if args.dry_run else 'Written'}: {fp}"
        )

    orphans = detect_orphans(infra, args.base_dir)
    if orphans:
        print(f"\nOrphan files ({len(orphans)}):")
        for filepath, is_protected in orphans:
            if is_protected:
                print(
                    f"  PROTECTED (ephemeral=false): {filepath} "
                    f"— manual removal required"
                )
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
