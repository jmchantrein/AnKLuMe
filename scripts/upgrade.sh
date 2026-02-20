#!/usr/bin/env bash
# upgrade.sh — Safe anklume framework upgrade
# Usage: scripts/upgrade.sh
#
# Pulls upstream changes, detects modified framework files, creates backups,
# handles untracked file conflicts, and regenerates managed sections.
# User files are never touched.

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

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info() { printf "${CYAN}%s${NC}\n" "$1"; }
ok()   { printf "${GREEN}%s${NC}\n" "$1"; }
warn() { printf "${YELLOW}%s${NC}\n" "$1"; }
die()  { printf "${RED}ERROR: %s${NC}\n" "$1" >&2; exit 1; }

printf "\n${BOLD}=== AnKLuMe Upgrade ===${NC}\n\n"

# Check we're in a git repository
if ! git rev-parse --is-inside-work-tree &>/dev/null; then
    die "Not a git repository. Cannot upgrade."
fi

# Check for uncommitted changes — auto-stash if needed
STASHED=false
if ! git diff --quiet || ! git diff --cached --quiet; then
    warn "Uncommitted changes detected — stashing automatically."
    git stash push -m "anklume-upgrade-$(date +%Y%m%d-%H%M%S)"
    STASHED=true
fi

# Detect locally modified framework files
info "--- Checking for locally modified framework files ---"
MODIFIED=()
for file in "${FRAMEWORK_FILES[@]}"; do
    if [ -f "$file" ] && ! git diff --quiet -- "$file" 2>/dev/null; then
        MODIFIED+=("$file")
    fi
done

# Backup modified framework files
if [ ${#MODIFIED[@]} -gt 0 ]; then
    warn "Modified framework files (will be backed up):"
    for file in "${MODIFIED[@]}"; do
        backup="${file}.bak.$(date +%Y%m%d-%H%M%S)"
        printf "  %s → %s\n" "$file" "$backup"
        cp "$file" "$backup"
    done
fi

# Pull upstream
info "--- Pulling upstream changes ---"
CURRENT_BRANCH=$(git branch --show-current)
MOVED_UNTRACKED=()

if git remote | grep -q origin; then
    git fetch origin

    # Detect untracked files that would conflict with incoming changes
    # git merge fails with "The following untracked working tree files would
    # be overwritten by merge" — we handle this proactively.
    INCOMING_FILES=$(git diff --name-only HEAD "origin/$CURRENT_BRANCH" 2>/dev/null || true)
    if [ -n "$INCOMING_FILES" ]; then
        while IFS= read -r file; do
            # File exists locally, is untracked, and incoming from upstream
            if [ -e "$file" ] && ! git ls-files --error-unmatch "$file" &>/dev/null; then
                backup="${file}.local-backup.$(date +%Y%m%d-%H%M%S)"
                warn "Untracked file conflicts with upstream: $file → $backup"
                mv "$file" "$backup"
                MOVED_UNTRACKED+=("$file|$backup")
            fi
        done <<< "$INCOMING_FILES"
    fi

    git merge "origin/$CURRENT_BRANCH" --no-edit || {
        printf "\n${RED}ERROR: Merge conflict detected. Resolve manually.${NC}\n"
        echo "Backups of modified files have been created (.bak)."
        if [ ${#MOVED_UNTRACKED[@]} -gt 0 ]; then
            echo "Moved untracked files:"
            for entry in "${MOVED_UNTRACKED[@]}"; do
                printf "  %s\n" "${entry#*|}"
            done
        fi
        if $STASHED; then
            echo "Your stashed changes can be restored with: git stash pop"
        fi
        exit 1
    }
else
    warn "No 'origin' remote found. Skipping pull."
fi

# Report moved untracked files
if [ ${#MOVED_UNTRACKED[@]} -gt 0 ]; then
    printf "\n"
    warn "Untracked files were moved to avoid conflicts:"
    for entry in "${MOVED_UNTRACKED[@]}"; do
        orig="${entry%%|*}"
        backup="${entry#*|}"
        printf "  %s → %s\n" "$orig" "$backup"
    done
    echo "Review and merge manually if needed."
fi

# Regenerate managed sections
info "--- Regenerating managed sections ---"
INFRA_SRC="infra.yml"
if [ -d "infra" ] && [ -f "infra/base.yml" ]; then
    INFRA_SRC="infra"
fi

if [ -f "$INFRA_SRC" ] || [ -d "$INFRA_SRC" ]; then
    python3 scripts/generate.py "$INFRA_SRC"
    ok "Managed sections regenerated."
else
    warn "No infra.yml or infra/ found. Skipping regeneration."
fi

# Restore stashed changes
if $STASHED; then
    info "--- Restoring stashed changes ---"
    if git stash pop; then
        ok "Local changes restored."
    else
        warn "Stash pop had conflicts. Resolve with: git stash show -p | git apply"
    fi
fi

# Update version marker for notification
if [ -d "$HOME/.anklume" ]; then
    git rev-parse HEAD > "$HOME/.anklume/last-upgrade-commit" 2>/dev/null || true
fi

printf "\n"
ok "Upgrade complete."
echo "User files preserved: ${USER_FILES[*]}"
if [ ${#MODIFIED[@]} -gt 0 ]; then
    echo "Backups created for: ${MODIFIED[*]}"
fi
echo "Run 'make lint' to validate, then 'make apply' to converge."
