#!/usr/bin/env bash
# upgrade.sh — Safe AnKLuMe framework upgrade
# Usage: scripts/upgrade.sh
#
# Pulls upstream changes, detects modified framework files, creates backups,
# and regenerates managed sections. User files are never touched.

set -euo pipefail

FRAMEWORK_FILES=(
    "Makefile"
    "site.yml"
    "snapshot.yml"
    "ansible.cfg"
    ".ansible-lint"
    ".yamllint.yml"
    "pyproject.toml"
)
USER_FILES=(
    "infra.yml"
    "infra/"
    "anklume.conf.yml"
    "roles_custom/"
)

echo "=== AnKLuMe Upgrade ==="

# Check we're in a git repository
if ! git rev-parse --is-inside-work-tree &>/dev/null; then
    echo "ERROR: Not a git repository. Cannot upgrade."
    exit 1
fi

# Check for uncommitted changes
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "WARNING: Uncommitted changes detected."
    read -rp "Continue anyway? [y/N] " confirm
    if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
        echo "Aborted. Commit or stash changes first."
        exit 0
    fi
fi

# Detect locally modified framework files
echo "--- Checking for locally modified framework files ---"
MODIFIED=()
for file in "${FRAMEWORK_FILES[@]}"; do
    if [ -f "$file" ] && ! git diff --quiet -- "$file" 2>/dev/null; then
        MODIFIED+=("$file")
    fi
done

# Backup modified framework files
if [ ${#MODIFIED[@]} -gt 0 ]; then
    echo "Modified framework files (will be backed up):"
    for file in "${MODIFIED[@]}"; do
        backup="${file}.bak.$(date +%Y%m%d-%H%M%S)"
        echo "  $file → $backup"
        cp "$file" "$backup"
    done
fi

# Pull upstream
echo "--- Pulling upstream changes ---"
CURRENT_BRANCH=$(git branch --show-current)
if git remote | grep -q origin; then
    git fetch origin
    git merge "origin/$CURRENT_BRANCH" --no-edit || {
        echo "ERROR: Merge conflict detected. Resolve manually."
        echo "Backups of modified files have been created (.bak)."
        exit 1
    }
else
    echo "WARNING: No 'origin' remote found. Skipping pull."
fi

# Regenerate managed sections
echo "--- Regenerating managed sections ---"
INFRA_SRC="infra.yml"
if [ -d "infra" ] && [ -f "infra/base.yml" ]; then
    INFRA_SRC="infra"
fi

if [ -f "$INFRA_SRC" ] || [ -d "$INFRA_SRC" ]; then
    python3 scripts/generate.py "$INFRA_SRC"
    echo "Managed sections regenerated."
else
    echo "WARNING: No infra.yml or infra/ found. Skipping regeneration."
fi

echo ""
echo "Upgrade complete."
echo "User files preserved: ${USER_FILES[*]}"
if [ ${#MODIFIED[@]} -gt 0 ]; then
    echo "Backups created for: ${MODIFIED[*]}"
fi
echo "Run 'make lint' to validate, then 'make apply' to converge."
