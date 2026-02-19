#!/usr/bin/env python3
"""code-audit.py — Codebase audit report for AnKLuMe.

Produces a structured report with:
- Dead code detection (delegates to scripts/code-analysis.sh dead-code)
- Line count per file type (Python, Shell, YAML, Tests)
- Test-to-implementation ratio per module
- Scripts without test coverage
- Roles sorted by size with simplification candidates flagged

Usage:
    scripts/code-audit.py [--json] [--output FILE]
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent


def count_lines(filepath):
    """Count non-empty, non-comment lines in a file."""
    try:
        total = 0
        with open(filepath) as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    total += 1
        return total
    except (OSError, UnicodeDecodeError):
        return 0


def count_lines_raw(filepath):
    """Count total lines in a file."""
    try:
        with open(filepath) as f:
            return sum(1 for _ in f)
    except (OSError, UnicodeDecodeError):
        return 0


def collect_file_metrics(project_dir):
    """Collect line counts grouped by file type."""
    categories = {
        "python_impl": {"pattern": "scripts/*.py", "lines": 0, "files": []},
        "python_test": {"pattern": "tests/*.py", "lines": 0, "files": []},
        "shell": {"pattern": "scripts/*.sh", "lines": 0, "files": []},
        "yaml_roles": {"pattern": "roles/**/*.yml", "lines": 0, "files": []},
        "yaml_config": {"pattern": "*.yml", "lines": 0, "files": []},
    }

    # Python implementation scripts
    scripts_dir = project_dir / "scripts"
    if scripts_dir.is_dir():
        for f in sorted(scripts_dir.glob("*.py")):
            lines = count_lines_raw(f)
            categories["python_impl"]["files"].append(
                {"path": str(f.relative_to(project_dir)), "lines": lines}
            )
            categories["python_impl"]["lines"] += lines

    # Python tests
    tests_dir = project_dir / "tests"
    if tests_dir.is_dir():
        for f in sorted(tests_dir.glob("*.py")):
            lines = count_lines_raw(f)
            categories["python_test"]["files"].append(
                {"path": str(f.relative_to(project_dir)), "lines": lines}
            )
            categories["python_test"]["lines"] += lines

    # Shell scripts
    if scripts_dir.is_dir():
        for f in sorted(scripts_dir.glob("*.sh")):
            lines = count_lines_raw(f)
            categories["shell"]["files"].append(
                {"path": str(f.relative_to(project_dir)), "lines": lines}
            )
            categories["shell"]["lines"] += lines

    # Roles YAML
    roles_dir = project_dir / "roles"
    if roles_dir.is_dir():
        for f in sorted(roles_dir.rglob("*.yml")):
            lines = count_lines_raw(f)
            categories["yaml_roles"]["files"].append(
                {"path": str(f.relative_to(project_dir)), "lines": lines}
            )
            categories["yaml_roles"]["lines"] += lines

    # Top-level YAML config
    for f in sorted(project_dir.glob("*.yml")):
        lines = count_lines_raw(f)
        categories["yaml_config"]["files"].append(
            {"path": str(f.relative_to(project_dir)), "lines": lines}
        )
        categories["yaml_config"]["lines"] += lines

    return categories


def compute_test_ratios(categories):
    """Compute test-to-implementation ratio per module."""
    impl_files = {}
    test_files = {}

    for entry in categories["python_impl"]["files"]:
        name = Path(entry["path"]).stem
        impl_files[name] = entry["lines"]

    for entry in categories["python_test"]["files"]:
        name = Path(entry["path"]).stem
        # Test files typically named test_<module>.py
        if name.startswith("test_"):
            module = name[5:]  # Remove "test_" prefix
        else:
            module = name
        test_files[module] = entry["lines"]

    ratios = {}
    for module, impl_lines in impl_files.items():
        test_lines = test_files.get(module, 0)
        ratio = round(test_lines / impl_lines, 2) if impl_lines > 0 else 0
        ratios[module] = {
            "impl_lines": impl_lines,
            "test_lines": test_lines,
            "ratio": ratio,
        }

    # Check for test files without matching implementation
    for module, test_lines in test_files.items():
        if module not in impl_files:
            ratios[module] = {
                "impl_lines": 0,
                "test_lines": test_lines,
                "ratio": float("inf"),
            }

    return ratios


def find_untested_scripts(project_dir):
    """Find scripts that have no corresponding test file."""
    scripts_dir = project_dir / "scripts"
    tests_dir = project_dir / "tests"
    untested = []

    if not scripts_dir.is_dir():
        return untested

    test_modules = set()
    if tests_dir.is_dir():
        for f in tests_dir.glob("test_*.py"):
            test_modules.add(f.stem[5:])  # Remove "test_" prefix

    # Check Python scripts
    for f in sorted(scripts_dir.glob("*.py")):
        if f.stem not in test_modules:
            untested.append(str(f.relative_to(project_dir)))

    # Check Shell scripts
    for f in sorted(scripts_dir.glob("*.sh")):
        stem = f.stem.replace("-", "_")
        if stem not in test_modules:
            untested.append(str(f.relative_to(project_dir)))

    return untested


def measure_roles(project_dir):
    """Measure role sizes and flag simplification candidates."""
    roles_dir = project_dir / "roles"
    roles = []

    if not roles_dir.is_dir():
        return roles

    for role_dir in sorted(roles_dir.iterdir()):
        if not role_dir.is_dir():
            continue
        total_lines = 0
        file_count = 0
        for f in role_dir.rglob("*.yml"):
            total_lines += count_lines_raw(f)
            file_count += 1
        for f in role_dir.rglob("*.j2"):
            total_lines += count_lines_raw(f)
            file_count += 1

        # Flag roles over 200 lines as simplification candidates
        candidate = total_lines > 200
        roles.append({
            "name": role_dir.name,
            "lines": total_lines,
            "files": file_count,
            "simplification_candidate": candidate,
        })

    # Sort by lines descending
    roles.sort(key=lambda r: r["lines"], reverse=True)
    return roles


def run_dead_code(project_dir):
    """Run dead code detection via code-analysis.sh."""
    script = project_dir / "scripts" / "code-analysis.sh"
    if not script.exists():
        return {"status": "skipped", "reason": "code-analysis.sh not found"}

    try:
        result = subprocess.run(
            ["bash", str(script), "dead-code"],
            capture_output=True,
            text=True,
            cwd=str(project_dir),
            timeout=60,
        )
        return {
            "status": "ok",
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"status": "timeout"}
    except FileNotFoundError:
        return {"status": "error", "reason": "bash not found"}


def build_report(project_dir):
    """Build the full audit report."""
    categories = collect_file_metrics(project_dir)
    ratios = compute_test_ratios(categories)
    untested = find_untested_scripts(project_dir)
    roles = measure_roles(project_dir)
    dead_code = run_dead_code(project_dir)

    total_impl = categories["python_impl"]["lines"] + categories["shell"]["lines"]
    total_test = categories["python_test"]["lines"]
    overall_ratio = round(total_test / total_impl, 2) if total_impl > 0 else 0

    return {
        "project_dir": str(project_dir),
        "summary": {
            "total_implementation_lines": total_impl,
            "total_test_lines": total_test,
            "total_role_lines": categories["yaml_roles"]["lines"],
            "overall_test_to_impl_ratio": overall_ratio,
        },
        "line_counts": {
            k: {"total_lines": v["lines"], "file_count": len(v["files"])}
            for k, v in categories.items()
        },
        "test_ratios": ratios,
        "untested_scripts": untested,
        "roles": roles,
        "dead_code": dead_code,
    }


def print_report(report):
    """Print a human-readable report to stdout."""
    s = report["summary"]
    print("=" * 60)
    print("  AnKLuMe Code Audit Report")
    print("=" * 60)
    print()

    # Summary
    print("SUMMARY")
    print(f"  Implementation (Python+Shell): {s['total_implementation_lines']} lines")
    print(f"  Tests (Python):                {s['total_test_lines']} lines")
    print(f"  Roles (YAML):                  {s['total_role_lines']} lines")
    print(f"  Test-to-impl ratio:            {s['overall_test_to_impl_ratio']}x")
    print()

    # Line counts by category
    print("LINE COUNTS BY CATEGORY")
    for cat, data in report["line_counts"].items():
        label = cat.replace("_", " ").title()
        print(f"  {label:25s} {data['total_lines']:>6} lines  ({data['file_count']} files)")
    print()

    # Test ratios per module
    print("TEST-TO-IMPLEMENTATION RATIO PER MODULE")
    ratios = report["test_ratios"]
    for module in sorted(ratios, key=lambda m: ratios[m]["ratio"], reverse=True):
        r = ratios[module]
        ratio_str = f"{r['ratio']:.1f}x" if r["ratio"] != float("inf") else "test-only"
        flag = " <-- no impl" if r["impl_lines"] == 0 else ""
        print(f"  {module:30s} impl={r['impl_lines']:>5}  test={r['test_lines']:>5}  ratio={ratio_str}{flag}")
    print()

    # Untested scripts
    print(f"SCRIPTS WITHOUT TEST COVERAGE ({len(report['untested_scripts'])})")
    if report["untested_scripts"]:
        for s in report["untested_scripts"]:
            print(f"  {s}")
    else:
        print("  All scripts have tests.")
    print()

    # Roles by size
    print("ROLES BY SIZE (largest first)")
    for role in report["roles"]:
        flag = " ** SIMPLIFICATION CANDIDATE" if role["simplification_candidate"] else ""
        print(f"  {role['name']:30s} {role['lines']:>5} lines  ({role['files']} files){flag}")
    print()

    # Dead code
    print("DEAD CODE DETECTION")
    dc = report["dead_code"]
    if dc["status"] == "ok":
        if dc["stdout"].strip():
            print(dc["stdout"])
        if dc["stderr"].strip():
            print(dc["stderr"])
    elif dc["status"] == "skipped":
        print(f"  Skipped: {dc['reason']}")
    elif dc["status"] == "timeout":
        print("  Timed out.")
    else:
        print(f"  Error: {dc.get('reason', 'unknown')}")
    print()
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="AnKLuMe codebase audit report")
    parser.add_argument(
        "--json", action="store_true", help="Output as JSON instead of text"
    )
    parser.add_argument(
        "--output", "-o", type=str, help="Write report to file (default: stdout)"
    )
    parser.add_argument(
        "--project-dir",
        type=str,
        default=str(PROJECT_DIR),
        help="Project root directory",
    )
    args = parser.parse_args()

    project_dir = Path(args.project_dir)
    if not project_dir.is_dir():
        print(f"ERROR: Not a directory: {project_dir}", file=sys.stderr)
        sys.exit(1)

    report = build_report(project_dir)

    if args.json:
        output = json.dumps(report, indent=2, default=str)
    else:
        # Capture print output if writing to file
        if args.output:
            import io

            buf = io.StringIO()
            old_stdout = sys.stdout
            sys.stdout = buf
            print_report(report)
            sys.stdout = old_stdout
            output = buf.getvalue()
        else:
            print_report(report)
            return

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            f.write(output)
        print(f"Report written to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
