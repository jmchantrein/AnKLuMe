#!/usr/bin/env python3
"""Auto-generate stub step definitions for missing behave steps.

Parses all .feature files in scenarios/, extracts step texts, compares
against existing steps/*.py definitions, and outputs stubs for any
missing steps.

Usage:
    python3 scripts/generate-bdd-stubs.py              # Show missing steps
    python3 scripts/generate-bdd-stubs.py --write       # Generate stub file
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
SCENARIOS_DIR = PROJECT_DIR / "scenarios"
STEPS_DIR = SCENARIOS_DIR / "steps"
STUB_FILE = STEPS_DIR / "generated_stubs.py"


def extract_feature_steps(feature_dir: Path) -> list[tuple[str, str, str]]:
    """Extract all step texts from .feature files.

    Returns list of (keyword, text, source) tuples.
    """
    steps = []
    for feature_file in sorted(feature_dir.rglob("*.feature")):
        rel = feature_file.relative_to(SCENARIOS_DIR)
        for line_no, line in enumerate(feature_file.read_text().splitlines(), 1):
            stripped = line.strip()
            match = re.match(
                r"^(Given|When|Then|And|But)\s+(.+)$", stripped
            )
            if match:
                keyword = match.group(1)
                text = match.group(2)
                # Normalize And/But to the previous keyword context
                # (for stub generation, treat as Given)
                if keyword in ("And", "But"):
                    keyword = "Given"
                steps.append((keyword, text, f"{rel}:{line_no}"))
    return steps


def extract_defined_patterns(steps_dir: Path) -> set[str]:
    """Extract step patterns from Python step definition files.

    Returns set of normalized pattern strings.
    """
    patterns = set()
    for py_file in sorted(steps_dir.glob("*.py")):
        if py_file.name == "__init__.py":
            continue
        content = py_file.read_text()
        # Match @given('...'), @when('...'), @then('...')
        for match in re.finditer(
            r'@(?:given|when|then)\(["\'](.+?)["\']\)', content
        ):
            pattern = match.group(1)
            patterns.add(pattern)
    return patterns


def normalize_step_text(text: str) -> str:
    """Normalize a step text for comparison with patterns.

    Replaces quoted strings with pattern placeholders.
    """
    # Replace quoted strings with placeholder
    normalized = re.sub(r'"[^"]*"', '"{value}"', text)
    # Replace numbers with placeholder
    normalized = re.sub(r"\b\d+\b", "{n}", normalized)
    return normalized


def match_step_to_pattern(text: str, patterns: set[str]) -> bool:
    """Check if a step text matches any defined pattern."""
    for pattern in patterns:
        # Convert pattern to regex
        regex = pattern
        # Escape regex special chars except our placeholders
        regex = re.sub(r"\{[^}]+\}", "PLACEHOLDER", regex)
        regex = re.escape(regex)
        regex = regex.replace("PLACEHOLDER", r".+")
        regex = f"^{regex}$"
        if re.match(regex, text):
            return True
    return False


def find_missing_steps(
    feature_steps: list[tuple[str, str, str]],
    patterns: set[str],
) -> list[tuple[str, str, list[str]]]:
    """Find steps that don't match any defined pattern.

    Returns list of (keyword, text, sources) tuples, deduplicated.
    """
    missing: dict[str, tuple[str, str, list[str]]] = {}
    for keyword, text, source in feature_steps:
        if not match_step_to_pattern(text, patterns):
            key = f"{keyword}:{text}"
            if key in missing:
                missing[key][2].append(source)
            else:
                missing[key] = (keyword, text, [source])
    return list(missing.values())


def generate_stub(keyword: str, text: str) -> str:
    """Generate a Python stub for a missing step."""
    decorator = keyword.lower()
    if decorator in ("and", "but"):
        decorator = "given"

    # Create function name from text
    func_name = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:60]

    # Detect parameters
    params = []
    pattern = text
    for i, match in enumerate(re.finditer(r'"([^"]*)"', text)):
        param_name = f"param{i + 1}" if i > 0 else "value"
        params.append(param_name)
        pattern = pattern.replace(match.group(0), f'"{{{param_name}}}"', 1)

    param_str = ", ".join(["context"] + params)

    return f"""
@{decorator}('{pattern}')
def {func_name}({param_str}):
    \"\"\"TODO: Implement step.\"\"\"
    raise NotImplementedError("Step not yet implemented")
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate BDD step stubs")
    parser.add_argument(
        "--write", action="store_true", help="Write stubs to file"
    )
    args = parser.parse_args()

    feature_steps = extract_feature_steps(SCENARIOS_DIR)
    patterns = extract_defined_patterns(STEPS_DIR)

    missing = find_missing_steps(feature_steps, patterns)

    if not missing:
        print("All steps are defined. No stubs needed.")
        return 0

    print(f"Found {len(missing)} undefined step(s):\n")
    stubs = []
    for keyword, text, sources in missing:
        print(f"  {keyword} {text}")
        for src in sources[:3]:
            print(f"    -> {src}")
        stubs.append(generate_stub(keyword, text))

    if args.write:
        header = '"""Auto-generated step stubs. Move implementations to appropriate files."""\n\n'
        header += "from behave import given, then, when  # noqa: F401\n"
        content = header + "\n".join(stubs)
        STUB_FILE.write_text(content)
        print(f"\nStubs written to {STUB_FILE.relative_to(PROJECT_DIR)}")
    else:
        print(f"\nRun with --write to generate {STUB_FILE.relative_to(PROJECT_DIR)}")

    return 1


if __name__ == "__main__":
    sys.exit(main())
