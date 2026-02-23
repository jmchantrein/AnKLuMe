#!/usr/bin/env python3
"""Run behavioral test chains from tests/behavioral_chains.yml.

Each chain is a sequential admin-sys workflow. Steps run in order;
a failing step stops the chain (subsequent steps depend on it).

Usage:
    python3 scripts/run-behavioral-tests.py              # all chains
    python3 scripts/run-behavioral-tests.py --chain bootstrap-to-first-deploy
    python3 scripts/run-behavioral-tests.py --dry-run    # show plan only
    python3 scripts/run-behavioral-tests.py --json       # JSON output
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import yaml

PROJECT_DIR = Path(__file__).resolve().parent.parent
CHAINS_FILE = PROJECT_DIR / "tests" / "behavioral_chains.yml"


def load_chains(path: Path) -> list:
    """Load and return chains from YAML file."""
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("chains", [])


def check_expectations(result, expect: dict, cwd: str) -> list:
    """Check result against expectations. Return list of failures."""
    failures = []

    if "exit_code" in expect and result.returncode != expect["exit_code"]:
        failures.append(
            f"exit_code: expected {expect['exit_code']}, "
            f"got {result.returncode}"
        )

    if "exit_code_not" in expect and result.returncode == expect["exit_code_not"]:
        failures.append(
            f"exit_code_not: should not be {expect['exit_code_not']}"
        )

    combined = result.stdout + result.stderr

    if "stdout_contains" in expect:
        needle = expect["stdout_contains"].lower()
        if needle not in combined.lower():
            failures.append(
                f"stdout_contains: '{expect['stdout_contains']}' "
                f"not found in output"
            )

    if "stdout_not_contains" in expect:
        needle = expect["stdout_not_contains"].lower()
        if needle in combined.lower():
            failures.append(
                f"stdout_not_contains: '{expect['stdout_not_contains']}' "
                f"found in output"
            )

    if "stderr_contains" in expect:
        needle = expect["stderr_contains"].lower()
        if needle not in combined.lower():
            failures.append(
                f"stderr_contains: '{expect['stderr_contains']}' "
                f"not found in output"
            )

    if "stdout_matches" in expect:
        import re
        pattern = expect["stdout_matches"]
        if not re.search(pattern, combined):
            failures.append(
                f"stdout_matches: pattern '{pattern}' not found"
            )

    if "file_exists" in expect:
        p = Path(cwd) / expect["file_exists"]
        if not p.exists():
            failures.append(f"file_exists: {expect['file_exists']} not found")

    if "dir_exists" in expect:
        p = Path(cwd) / expect["dir_exists"]
        if not p.exists():
            failures.append(f"dir_exists: {expect['dir_exists']} not found")

    if "files_exist" in expect:
        for fname in expect["files_exist"]:
            p = Path(cwd) / fname
            if not p.exists():
                failures.append(f"files_exist: {fname} not found")

    return failures


def run_step(step: dict, cwd: str, dry_run: bool = False) -> dict:
    """Run a single step and return result dict."""
    action = step["action"]
    expect = step.get("expect", {})
    timeout = step.get("timeout", 60)
    desc = step.get("description", action[:60])

    if dry_run:
        return {
            "description": desc,
            "action": action,
            "status": "dry-run",
            "failures": [],
        }

    start = time.time()
    try:
        result = subprocess.run(
            ["bash", "-c", action],
            capture_output=True, text=True,
            timeout=timeout, cwd=cwd,
        )
    except subprocess.TimeoutExpired:
        return {
            "description": desc,
            "action": action,
            "status": "TIMEOUT",
            "duration": timeout,
            "failures": [f"Timed out after {timeout}s"],
        }

    duration = round(time.time() - start, 1)
    failures = check_expectations(result, expect, cwd)

    return {
        "description": desc,
        "action": action,
        "status": "PASS" if not failures else "FAIL",
        "duration": duration,
        "exit_code": result.returncode,
        "failures": failures,
        "stdout_tail": result.stdout[-500:] if failures else "",
        "stderr_tail": result.stderr[-500:] if failures else "",
    }


def run_chain(chain: dict, dry_run: bool = False,
              cwd: str | None = None) -> dict:
    """Run all steps in a chain sequentially.

    Chains with sandbox: true run in a temporary copy of the repo
    to avoid modifying production files (infra.yml, inventory/, etc.).
    """
    name = chain["chain"]
    steps = chain.get("steps", [])
    use_sandbox = chain.get("sandbox", False)

    sandbox_dir = None
    if use_sandbox and not dry_run:
        import shutil
        import tempfile
        sandbox_dir = tempfile.mkdtemp(prefix=f"anklume-behavioral-{name}-")
        # Copy essential project files (not .git)
        for item in PROJECT_DIR.iterdir():
            if item.name in (".git", ".venv", "__pycache__", ".tox",
                             "control", "control.tar.xz", "uv.lock"):
                continue
            dest = Path(sandbox_dir) / item.name
            if item.is_dir():
                shutil.copytree(item, dest, symlinks=True,
                                ignore=shutil.ignore_patterns(
                                    "__pycache__", "*.pyc", ".git"))
            else:
                shutil.copy2(item, dest)
        # Symlink .venv from original project (avoids copying GBs)
        venv_src = PROJECT_DIR / ".venv"
        if venv_src.exists():
            os.symlink(venv_src, Path(sandbox_dir) / ".venv")
        # Remove user-specific files so tests start clean
        for f in ["infra.yml"]:
            p = Path(sandbox_dir) / f
            if p.exists():
                p.unlink()
        for d in ["inventory", "group_vars", "host_vars"]:
            p = Path(sandbox_dir) / d
            if p.exists():
                shutil.rmtree(p)
        work_dir = sandbox_dir
    else:
        work_dir = cwd or str(PROJECT_DIR)

    results = []
    chain_status = "PASS"

    for i, step in enumerate(steps, 1):
        step_result = run_step(step, work_dir, dry_run)
        step_result["step"] = i
        results.append(step_result)

        if step_result["status"] == "FAIL":
            chain_status = "FAIL"
            # Mark remaining steps as skipped
            for j, remaining in enumerate(steps[i:], i + 1):
                results.append({
                    "step": j,
                    "description": remaining.get(
                        "description", remaining["action"][:60]
                    ),
                    "status": "SKIPPED",
                    "failures": ["Previous step failed"],
                })
            break
        elif step_result["status"] == "TIMEOUT":
            chain_status = "FAIL"
            for j, remaining in enumerate(steps[i:], i + 1):
                results.append({
                    "step": j,
                    "description": remaining.get(
                        "description", remaining["action"][:60]
                    ),
                    "status": "SKIPPED",
                    "failures": ["Previous step timed out"],
                })
            break

    # Cleanup sandbox
    if sandbox_dir and not os.environ.get("ANKLUME_KEEP_SANDBOX"):
        import shutil
        shutil.rmtree(sandbox_dir, ignore_errors=True)

    return {
        "chain": name,
        "description": chain.get("description", ""),
        "status": chain_status,
        "sandbox": sandbox_dir if sandbox_dir else None,
        "steps": results,
        "total": len(steps),
        "passed": sum(1 for r in results if r["status"] == "PASS"),
        "failed": sum(1 for r in results if r["status"] == "FAIL"),
        "skipped": sum(1 for r in results if r["status"] == "SKIPPED"),
    }


def print_result(result: dict) -> None:
    """Print chain result in human-readable format."""
    status_icon = {"PASS": "+", "FAIL": "X", "SKIPPED": "-",
                   "dry-run": "~", "TIMEOUT": "!"}

    name = result["chain"]
    status = result["status"]
    print(f"\n{'=' * 60}")
    print(f"[{status}] {name}")
    print(f"  {result['description'].strip()}")
    print(f"  {result['passed']}/{result['total']} passed", end="")
    if result["failed"]:
        print(f", {result['failed']} failed", end="")
    if result["skipped"]:
        print(f", {result['skipped']} skipped", end="")
    print()

    for step in result["steps"]:
        icon = status_icon.get(step["status"], "?")
        desc = step["description"]
        duration = step.get("duration", "")
        dur_str = f" ({duration}s)" if duration else ""
        print(f"  [{icon}] Step {step['step']}: {desc}{dur_str}")
        for f in step.get("failures", []):
            print(f"      ! {f}")
        if step.get("stderr_tail"):
            for line in step["stderr_tail"].strip().split("\n")[-3:]:
                print(f"      > {line}")


def main():
    parser = argparse.ArgumentParser(
        description="Run behavioral test chains"
    )
    parser.add_argument("--chain", help="Run a specific chain by name")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show plan without executing")
    parser.add_argument("--json", action="store_true",
                        help="Output results as JSON")
    parser.add_argument("--chains-file", default=str(CHAINS_FILE),
                        help="Path to chains YAML file")
    args = parser.parse_args()

    chains = load_chains(Path(args.chains_file))

    if args.chain:
        chains = [c for c in chains if c["chain"] == args.chain]
        if not chains:
            print(f"Chain '{args.chain}' not found.", file=sys.stderr)
            sys.exit(1)

    all_results = []
    for chain in chains:
        result = run_chain(chain, dry_run=args.dry_run)
        all_results.append(result)
        if not args.json:
            print_result(result)

    if args.json:
        print(json.dumps(all_results, indent=2))
    else:
        print(f"\n{'=' * 60}")
        total_chains = len(all_results)
        passed_chains = sum(1 for r in all_results if r["status"] == "PASS")
        print(f"TOTAL: {passed_chains}/{total_chains} chains passed")

    sys.exit(0 if all(r["status"] == "PASS" for r in all_results) else 1)


if __name__ == "__main__":
    main()
