#!/usr/bin/env bash
# instance-remove.sh — Targeted instance removal with protection awareness
# Usage:
#   scripts/instance-remove.sh --instance <name> [--force]
#   scripts/instance-remove.sh --domain <name> --scope <ephemeral|all> [--force]
#
# Respects security.protection.delete unless FORCE=true env var or --force flag.
# See ADR-042 for flush protection design.

set -euo pipefail

INSTANCE=""
DOMAIN=""
SCOPE=""
CLI_FORCE=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --instance|-i) INSTANCE="$2"; shift 2 ;;
        --domain|-d)   DOMAIN="$2";   shift 2 ;;
        --scope|-s)    SCOPE="$2";    shift 2 ;;
        --force)       CLI_FORCE=true; shift ;;
        *) echo "Usage: $0 --instance <name> | --domain <name> --scope <ephemeral|all> [--force]"
           exit 1 ;;
    esac
done

BYPASS="${FORCE:-false}"
[ "$CLI_FORCE" = "true" ] && BYPASS="true"

# Color helpers
_red()    { printf '\033[31m%s\033[0m' "$*"; }
_yellow() { printf '\033[33m%s\033[0m' "$*"; }
_green()  { printf '\033[32m%s\033[0m' "$*"; }

# Find project for an instance by scanning all projects
_find_project() {
    local name="$1"
    while IFS= read -r proj; do
        proj=$(echo "$proj" | sed 's/ (current)$//')
        if incus list --project "$proj" --format csv -c n 2>/dev/null | grep -qx "$name"; then
            echo "$proj"
            return 0
        fi
    done < <(incus project list --format csv -c n 2>/dev/null)
    return 1
}

# Check if instance is protected
_is_protected() {
    local name="$1" project="$2"
    local val
    val=$(incus config get "$name" security.protection.delete \
        --project "$project" 2>/dev/null || echo "")
    [ "$val" = "true" ]
}

# Delete a single instance with protection check
_delete_instance() {
    local name="$1" project="$2"
    if _is_protected "$name" "$project" && [ "$BYPASS" != "true" ]; then
        echo "  $(_yellow "PROTECTED"): $name (project: $project)"
        echo "  Use FORCE=true to bypass delete protection."
        return 1
    fi
    echo "  Deleting: $name (project: $project)"
    incus delete "$name" --project "$project" --force
    echo "  $(_green "Deleted"): $name"
}

deleted=0
skipped=0

if [ -n "$INSTANCE" ]; then
    # Single instance mode
    project=$(_find_project "$INSTANCE") || {
        echo "$(_red "ERROR"): Instance '$INSTANCE' not found in any project."
        exit 1
    }
    if _delete_instance "$INSTANCE" "$project"; then
        deleted=1
    else
        skipped=1
    fi

elif [ -n "$DOMAIN" ] && [ -n "$SCOPE" ]; then
    # Domain mode
    if [ "$SCOPE" != "ephemeral" ] && [ "$SCOPE" != "all" ]; then
        echo "$(_red "ERROR"): SCOPE must be 'ephemeral' or 'all', got '$SCOPE'"
        exit 1
    fi
    # Find the project for this domain (convention: project name = domain name)
    project="$DOMAIN"
    if ! incus project list --format csv -c n 2>/dev/null | sed 's/ (current)$//' | grep -qx "$project"; then
        echo "$(_red "ERROR"): Project '$project' not found."
        exit 1
    fi
    while IFS= read -r inst; do
        [ -z "$inst" ] && continue
        if [ "$SCOPE" = "ephemeral" ]; then
            # Only delete unprotected instances
            if _is_protected "$inst" "$project"; then
                echo "  Skipping (protected): $inst"
                skipped=$((skipped + 1))
                continue
            fi
        fi
        if _delete_instance "$inst" "$project"; then
            deleted=$((deleted + 1))
        else
            skipped=$((skipped + 1))
        fi
    done < <(incus list --project "$project" --format csv -c n 2>/dev/null)
else
    echo "Usage: $0 --instance <name> | --domain <name> --scope <ephemeral|all> [--force]"
    exit 1
fi

echo ""
echo "Result: $(_green "$deleted deleted"), $(_yellow "$skipped skipped")."
