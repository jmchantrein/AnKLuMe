#!/usr/bin/env python3
"""Mine git history for fix patterns and experience entries.

Scans git log for commits matching fix/lint/resolve/hotfix/workaround
patterns and extracts structured experience entries. Outputs YAML
entries that can be appended to the experiences/ directory.

Usage:
    python3 scripts/mine-experiences.py              # Mine all fix commits
    python3 scripts/mine-experiences.py --since abc1234  # Mine since commit
    python3 scripts/mine-experiences.py --dry-run    # Show without writing
    python3 scripts/mine-experiences.py --incremental # Resume from last run
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. Install: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

PROJECT_DIR = Path(__file__).resolve().parent.parent
EXPERIENCES_DIR = PROJECT_DIR / "experiences"
FIXES_DIR = EXPERIENCES_DIR / "fixes"
LAST_MINED_FILE = EXPERIENCES_DIR / ".last-mined-commit"

FIX_PATTERNS = re.compile(r"\b(fix|lint|resolve|hotfix|workaround|bug)\b", re.IGNORECASE)

CATEGORY_MAP = {
    "ansible-lint": re.compile(r"\b(lint|ansible-lint|noqa|fqcn)\b", re.IGNORECASE),
    "molecule": re.compile(r"\b(molecule|test|verify|converge|cleanup)\b", re.IGNORECASE),
    "incus-cli": re.compile(r"\b(incus|lxc|vm|bridge|network|project|profile|device)\b", re.IGNORECASE),
    "generator": re.compile(r"\b(generator|generate|psot|infra\.yml|validate|orphan)\b", re.IGNORECASE),
}


def run_git(args: list[str]) -> str:
    """Run a git command and return stdout."""
    result = subprocess.run(
        ["git", "-C", str(PROJECT_DIR), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def get_fix_commits(since_commit: str | None = None) -> list[tuple[str, str]]:
    """Get commits matching fix patterns. Returns [(hash, message), ...]."""
    log_args = ["log", "--all", "--format=%H %s"]
    if since_commit:
        log_args.append(f"{since_commit}..HEAD")

    output = run_git(log_args)
    if not output:
        return []

    commits = []
    for line in output.splitlines():
        parts = line.split(" ", 1)
        if len(parts) != 2:
            continue
        commit_hash, message = parts
        if FIX_PATTERNS.search(message):
            commits.append((commit_hash, message))

    return commits


def get_commit_files(commit_hash: str) -> list[str]:
    """Get list of files changed in a commit."""
    output = run_git(["diff-tree", "--no-commit-id", "-r", "--name-only", commit_hash])
    return output.splitlines() if output else []


def categorize_commit(message: str, files: list[str]) -> str:
    """Determine the category for a commit based on message and files."""
    combined = message + " " + " ".join(files)

    scores: dict[str, int] = {}
    for cat, pattern in CATEGORY_MAP.items():
        scores[cat] = len(pattern.findall(combined))

    if not any(scores.values()):
        return "generator"

    return max(scores, key=lambda k: scores[k])


def extract_experience(commit_hash: str, message: str) -> dict | None:
    """Extract an experience entry from a commit."""
    files = get_commit_files(commit_hash)
    if not files:
        return None

    category = categorize_commit(message, files)
    short_hash = commit_hash[:7]

    # Build file patterns from affected files
    file_patterns = []
    for f in files[:5]:
        if "roles/" in f:
            parts = f.split("/")
            if len(parts) >= 3:
                file_patterns.append(f"roles/*/{'/'.join(parts[2:])}")
            else:
                file_patterns.append(f)
        else:
            file_patterns.append(f)

    # Deduplicate patterns
    file_patterns = list(dict.fromkeys(file_patterns))

    return {
        "category": category,
        "problem": message,
        "solution": f"See commit {short_hash} for implementation details",
        "source_commit": short_hash,
        "files_affected": file_patterns,
        "prevention": "Added to experience library for future reference",
    }


def load_existing_ids() -> set[str]:
    """Load existing experience IDs to avoid duplicates."""
    ids: set[str] = set()
    for yml_file in FIXES_DIR.glob("*.yml"):
        try:
            with open(yml_file) as f:
                data = yaml.safe_load(f)
            if isinstance(data, list):
                for entry in data:
                    if isinstance(entry, dict):
                        if "id" in entry:
                            ids.add(entry["id"])
                        if "source_commit" in entry:
                            ids.add(entry["source_commit"])
        except (yaml.YAMLError, OSError):
            continue
    return ids


def load_last_mined_commit() -> str | None:
    """Load the last mined commit hash for incremental runs."""
    if LAST_MINED_FILE.exists():
        content = LAST_MINED_FILE.read_text().strip()
        return content if content else None
    return None


def save_last_mined_commit(commit_hash: str) -> None:
    """Save the last mined commit hash."""
    LAST_MINED_FILE.write_text(commit_hash + "\n")


def format_entries(entries: list[dict], category: str) -> str:
    """Format entries as YAML for appending to a category file."""
    lines = [f"# Mined entries for {category}"]
    for entry in entries:
        lines.append("")
        entry_id = entry.get("id", "MINED")
        lines.append(f"- id: {entry_id}")
        lines.append(f"  category: {entry['category']}")
        problem = entry["problem"].replace('"', '\\"')
        lines.append(f'  problem: "{problem}"')
        solution = entry["solution"].replace('"', '\\"')
        lines.append(f'  solution: "{solution}"')
        lines.append(f'  source_commit: "{entry["source_commit"]}"')
        files_str = ", ".join(f'"{f}"' for f in entry["files_affected"])
        lines.append(f"  files_affected: [{files_str}]")
        prevention = entry["prevention"].replace('"', '\\"')
        lines.append(f'  prevention: "{prevention}"')
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Mine git history for experience entries")
    parser.add_argument("--since", help="Mine commits since this commit hash")
    parser.add_argument("--dry-run", action="store_true", help="Show entries without writing")
    parser.add_argument("--incremental", action="store_true", help="Resume from last mined commit")
    args = parser.parse_args()

    since = args.since
    if args.incremental and not since:
        since = load_last_mined_commit()
        if since:
            print(f"Incremental mode: mining since {since[:7]}")

    existing_ids = load_existing_ids()
    commits = get_fix_commits(since)

    if not commits:
        print("No fix commits found.")
        return

    print(f"Found {len(commits)} fix commits to process")

    # Group new entries by category
    new_entries: dict[str, list[dict]] = {}
    skipped = 0

    for commit_hash, message in commits:
        short_hash = commit_hash[:7]

        if short_hash in existing_ids:
            skipped += 1
            continue

        entry = extract_experience(commit_hash, message)
        if not entry:
            continue

        cat = entry["category"]
        counter = len(new_entries.get(cat, [])) + 1
        prefix_map = {
            "ansible-lint": "MINED-LINT",
            "molecule": "MINED-MOL",
            "incus-cli": "MINED-INCUS",
            "generator": "MINED-GEN",
        }
        prefix = prefix_map.get(cat, "MINED")
        entry["id"] = f"{prefix}-{counter:03d}"

        new_entries.setdefault(cat, []).append(entry)

    total_new = sum(len(v) for v in new_entries.values())
    print(f"New entries: {total_new}, Skipped (already exists): {skipped}")

    if not new_entries:
        print("No new entries to add.")
        return

    for cat, entries in sorted(new_entries.items()):
        print(f"\n--- {cat} ({len(entries)} entries) ---")
        formatted = format_entries(entries, cat)

        if args.dry_run:
            print(formatted)
        else:
            target = FIXES_DIR / f"{cat}.yml"
            if target.exists():
                with open(target, "a") as f:
                    f.write("\n" + formatted)
                print(f"  Appended to {target}")
            else:
                with open(target, "w") as f:
                    f.write("---\n" + formatted)
                print(f"  Created {target}")

    # Save last mined commit for incremental mode
    if not args.dry_run and commits:
        latest = commits[0][0]  # First commit is most recent
        save_last_mined_commit(latest)
        print(f"\nSaved last mined commit: {latest[:7]}")


if __name__ == "__main__":
    main()
