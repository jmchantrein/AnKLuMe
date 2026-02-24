#!/usr/bin/env python3
"""Behavior matrix test coverage checker.

Scans test files for matrix ID references (# Matrix: XX-NNN pattern)
and reports coverage against tests/behavior_matrix.yml.
"""

import argparse
import re
import sys
from pathlib import Path

import yaml

MATRIX_REF_RE = re.compile(r"#\s*Matrix:\s*([\w-]+(?:,\s*[\w-]+)*)")
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_matrix(path=None):
    """Load behavior matrix and return all cell IDs grouped by capability+depth."""
    if path is None:
        path = PROJECT_ROOT / "tests" / "behavior_matrix.yml"
    with open(path) as f:
        data = yaml.safe_load(f)

    cells = {}  # {capability: {depth: [ids]}}
    all_ids = set()
    for cap_key, cap in (data.get("capabilities") or {}).items():
        cells[cap_key] = {}
        for depth in ("depth_1", "depth_2", "depth_3"):
            ids = []
            for item in cap.get(depth) or []:
                cell_id = item.get("id")
                if cell_id:
                    ids.append(cell_id)
                    all_ids.add(cell_id)
            cells[cap_key][depth] = ids
    return cells, all_ids


def scan_test_files():
    """Scan test files for matrix ID references.

    Excludes test_matrix_coverage.py because it contains fake matrix IDs
    used as test fixtures for the coverage checker itself.
    """
    covered = set()
    skip = {"test_matrix_coverage.py"}
    patterns = [
        PROJECT_ROOT / "tests" / "*.py",
        PROJECT_ROOT / "roles" / "*" / "molecule" / "*" / "verify.yml",
    ]
    for pattern in patterns:
        for filepath in sorted(PROJECT_ROOT.glob(str(pattern.relative_to(PROJECT_ROOT)))):
            if filepath.name in skip:
                continue
            try:
                text = filepath.read_text()
            except OSError:
                continue
            for match in MATRIX_REF_RE.finditer(text):
                for ref in match.group(1).split(","):
                    covered.add(ref.strip())
    return covered


def report(cells, covered_ids, all_ids):
    """Print coverage report table. Returns total coverage percentage."""
    print(f"{'Capability':<25} {'Depth':<10} {'Total':>6} {'Covered':>8} {'%':>6}")
    print("-" * 60)

    total_all = 0
    total_covered = 0

    for cap_key, depths in sorted(cells.items()):
        for depth_key in ("depth_1", "depth_2", "depth_3"):
            ids = depths.get(depth_key, [])
            if not ids:
                continue
            count = len(ids)
            cov = sum(1 for i in ids if i in covered_ids)
            pct = (cov / count * 100) if count else 0
            depth_label = depth_key.replace("_", " ")
            print(f"{cap_key:<25} {depth_label:<10} {count:>6} {cov:>8} {pct:>5.0f}%")
            total_all += count
            total_covered += cov

    print("-" * 60)
    total_pct = (total_covered / total_all * 100) if total_all else 0
    print(f"{'TOTAL':<25} {'':10} {total_all:>6} {total_covered:>8} {total_pct:>5.0f}%")

    # Check for unknown refs (IDs in tests not in matrix)
    unknown = covered_ids - all_ids
    if unknown:
        print(f"\nUnknown matrix references (not in matrix): {', '.join(sorted(unknown))}")

    return total_pct


def main(argv=None):
    parser = argparse.ArgumentParser(description="Behavior matrix test coverage checker")
    parser.add_argument("--matrix", default=None, help="Path to behavior_matrix.yml")
    parser.add_argument("--threshold", type=float, default=0, help="Minimum coverage %% (default: 0)")
    args = parser.parse_args(argv)

    cells, all_ids = load_matrix(args.matrix)
    covered_ids = scan_test_files()
    total_pct = report(cells, covered_ids, all_ids)

    if total_pct < args.threshold:
        print(f"\nFAIL: Coverage {total_pct:.0f}% < threshold {args.threshold:.0f}%")
        sys.exit(1)
    else:
        print(f"\nOK: Coverage {total_pct:.0f}% >= threshold {args.threshold:.0f}%")


if __name__ == "__main__":
    main()
