"""Dry-run sanitizer: load patterns, apply regex to input text, show redactions.

Loads the LLM sanitization patterns (from deployed config or Ansible template
fallback), applies them to input text, and reports what would be redacted.

Usage:
    echo "My IP is 10.120.1.5" | python3 scripts/sanitizer_dryrun.py
    python3 scripts/sanitizer_dryrun.py --file prompt.txt
    python3 scripts/sanitizer_dryrun.py --tmux  # compact one-line summary
"""

import argparse
import json
import re
import sys
from pathlib import Path


def load_patterns(patterns_file=None):
    """Load sanitization patterns from YAML file.

    Resolution order:
    1. Explicit patterns_file argument
    2. Deployed config: /etc/llm-sanitizer/patterns.yml
    3. Ansible template fallback: roles/llm_sanitizer/templates/patterns.yml.j2
       (strips Jinja2 {{ ansible_managed }} line)
    """
    import yaml

    candidates = []
    if patterns_file:
        candidates.append(Path(patterns_file))
    candidates.append(Path("/etc/llm-sanitizer/patterns.yml"))
    # Template fallback (relative to project root)
    project_root = Path(__file__).resolve().parent.parent
    candidates.append(
        project_root / "roles" / "llm_sanitizer" / "templates" / "patterns.yml.j2"
    )

    for path in candidates:
        if not path.is_file():
            continue
        text = path.read_text()
        # Strip Jinja2 header line ({{ ansible_managed }})
        lines = text.splitlines()
        cleaned = "\n".join(
            line for line in lines
            if not line.strip().startswith("{{") or "ansible_managed" not in line
        )
        data = yaml.safe_load(cleaned)
        if not data or "categories" not in data:
            continue
        # Flatten categories into a list of patterns
        patterns = []
        for category, pattern_list in data["categories"].items():
            for p in pattern_list:
                patterns.append({
                    "category": category,
                    "name": p.get("name", ""),
                    "description": p.get("description", ""),
                    "pattern": p.get("pattern", ""),
                    "replacement": p.get("replacement", "[REDACTED]"),
                })
        return patterns

    return []


def apply_patterns(text, patterns):
    """Apply all patterns to text.

    Returns (sanitized_text, redactions_list).
    Each redaction: {category, name, original, replacement, start, end}.
    """
    redactions = []
    result = text

    for p in patterns:
        regex = p["pattern"]
        if not regex:
            continue
        try:
            compiled = re.compile(regex)
        except re.error:
            continue

        for match in compiled.finditer(result):
            redactions.append({
                "category": p["category"],
                "name": p["name"],
                "original": match.group(),
                "replacement": p["replacement"],
                "start": match.start(),
                "end": match.end(),
            })

    # Apply replacements in reverse order to preserve positions
    for p in patterns:
        regex = p["pattern"]
        if not regex:
            continue
        try:
            result = re.sub(regex, p["replacement"], result)
        except re.error:
            continue

    return result, redactions


def format_diff(text, sanitized, redactions):
    """Format a human-readable diff showing redactions.

    Returns a string with original fragments struck through and
    replacements highlighted.
    """
    if not redactions:
        return "No redactions applied."

    lines = []
    lines.append(f"Found {len(redactions)} redaction(s):\n")

    # Group by category
    by_cat = {}
    for r in redactions:
        by_cat.setdefault(r["category"], []).append(r)

    for cat, items in sorted(by_cat.items()):
        lines.append(f"  [{cat}] ({len(items)} match(es))")
        for item in items:
            lines.append(
                f"    {item['name']}: "
                f"'{item['original']}' -> '{item['replacement']}'"
            )

    lines.append(f"\nSanitized output:\n{sanitized}")
    return "\n".join(lines)


def pattern_stats(patterns):
    """Return category summary: {category: count}."""
    stats = {}
    for p in patterns:
        cat = p["category"]
        stats[cat] = stats.get(cat, 0) + 1
    return stats


def main():
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Dry-run LLM sanitizer")
    parser.add_argument("text", nargs="?", help="Text to sanitize (or stdin)")
    parser.add_argument("--file", "-f", type=str, help="Read text from file")
    parser.add_argument("--patterns", "-p", type=str, help="Custom patterns file")
    parser.add_argument("--json", dest="json_output", action="store_true",
                        help="JSON output with redaction details")
    parser.add_argument("--stats", action="store_true",
                        help="Show pattern statistics only")
    args = parser.parse_args()

    patterns = load_patterns(args.patterns)
    if not patterns:
        print("ERROR: No patterns found.", file=sys.stderr)
        sys.exit(1)

    if args.stats:
        stats = pattern_stats(patterns)
        print(f"Loaded {len(patterns)} patterns in {len(stats)} categories:")
        for cat, count in sorted(stats.items()):
            print(f"  {cat}: {count} patterns")
        return

    if args.file:
        text = Path(args.file).read_text()
    elif args.text:
        text = args.text
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        print("ERROR: Provide text as argument, --file, or stdin.", file=sys.stderr)
        sys.exit(1)

    sanitized, redactions = apply_patterns(text, patterns)

    if args.json_output:
        print(json.dumps({
            "original": text,
            "sanitized": sanitized,
            "redactions": redactions,
            "count": len(redactions),
        }, indent=2))
    else:
        print(format_diff(text, sanitized, redactions))


if __name__ == "__main__":
    main()
