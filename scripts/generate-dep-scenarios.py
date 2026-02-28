#!/usr/bin/env python3
"""Generate BDD scenarios from the CLI dependency graph.

Reads _cli_deps.yml and generates .feature files testing each
producer→consumer dependency chain.

Usage:
    python3 scripts/generate-dep-scenarios.py              # Preview
    python3 scripts/generate-dep-scenarios.py --write       # Write files
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

PROJECT_DIR = Path(__file__).resolve().parent.parent
DEPS_FILE = PROJECT_DIR / "scripts" / "cli" / "_cli_deps.yml"
OUTPUT_DIR = PROJECT_DIR / "scenarios" / "generated"


def load_deps() -> dict:
    """Load the CLI dependency graph."""
    with open(DEPS_FILE) as f:
        return yaml.safe_load(f)


def build_dependency_pairs(data: dict) -> list[tuple[str, str, str]]:
    """Build (consumer, producer, resource) triples from the dependency graph.

    For each resource, every consumer depends on every producer.
    """
    pairs = []
    for resource_name, resource in data.get("resources", {}).items():
        producers = resource.get("producers", [])
        consumers = resource.get("consumers", [])
        for consumer in consumers:
            for producer in producers:
                pairs.append((consumer, producer, resource_name))
    return sorted(set(pairs))


def generate_feature(pairs: list[tuple[str, str, str]]) -> str:
    """Generate a .feature file from dependency pairs."""
    lines = [
        "# Auto-generated from _cli_deps.yml — do not edit manually.",
        "# Regenerate with: python3 scripts/generate-dep-scenarios.py --write",
        "",
        "Feature: CLI resource dependency chains",
        "  Each command depends on resources produced by prerequisite commands.",
        "  Running a consumer before its producer should fail or produce errors.",
        "",
    ]

    # Group by consumer
    by_consumer: dict[str, list[tuple[str, str]]] = {}
    for consumer, producer, resource in pairs:
        by_consumer.setdefault(consumer, []).append((producer, resource))

    for consumer, deps in sorted(by_consumer.items()):
        producers_list = ", ".join(sorted(set(p for p, _ in deps)))
        resources_list = ", ".join(sorted(set(r for _, r in deps)))
        lines.append(f"  Scenario: {consumer} depends on {producers_list}")
        lines.append(f"    # Resources needed: {resources_list}")
        lines.append(f"    # Producers: {producers_list}")
        lines.append("    Given a clean sandbox environment")
        lines.append(f"    # {consumer} requires {len(deps)} prerequisite(s)")
        lines.append("")

    return "\n".join(lines)


def generate_summary(pairs: list[tuple[str, str, str]]) -> str:
    """Generate a human-readable summary of all dependency chains."""
    lines = ["CLI Dependency Chain Summary", "=" * 40, ""]

    by_consumer: dict[str, list[tuple[str, str]]] = {}
    for consumer, producer, resource in pairs:
        by_consumer.setdefault(consumer, []).append((producer, resource))

    for consumer, deps in sorted(by_consumer.items()):
        producers = sorted(set(p for p, _ in deps))
        resources = sorted(set(r for _, r in deps))
        lines.append(f"  {consumer}")
        lines.append(f"    depends on: {', '.join(producers)}")
        lines.append(f"    via: {', '.join(resources)}")
        lines.append("")

    lines.append(f"Total: {len(by_consumer)} consumers, {len(pairs)} dependency edges")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate dep scenarios")
    parser.add_argument(
        "--write", action="store_true", help="Write generated feature file"
    )
    args = parser.parse_args()

    if not DEPS_FILE.exists():
        print(f"Error: {DEPS_FILE} not found", file=sys.stderr)
        return 1

    data = load_deps()
    pairs = build_dependency_pairs(data)

    if not pairs:
        print("No dependency pairs found.")
        return 0

    summary = generate_summary(pairs)
    print(summary)

    if args.write:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        feature_content = generate_feature(pairs)
        output_file = OUTPUT_DIR / "cli_dependency_chains.feature"
        output_file.write_text(feature_content)
        print(f"\nWritten to {output_file.relative_to(PROJECT_DIR)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
