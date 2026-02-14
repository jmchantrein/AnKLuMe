#!/usr/bin/env bash
# Deploy nftables inter-bridge isolation rules on the host.
#
# This script runs ON THE HOST (not inside the admin container).
# It pulls the generated rules from the admin container,
# validates the syntax, copies to /etc/nftables.d/, and reloads nftables.
#
# Usage: deploy-nftables.sh [--dry-run] [--source CONTAINER_NAME]
# Default source: admin-ansible
# Default project: admin (searches all projects if not found)
set -euo pipefail

die() { echo "ERROR: $*" >&2; exit 1; }

# ── Defaults ─────────────────────────────────────────────────

DRY_RUN=false
SOURCE_CONTAINER="admin-ansible"
SOURCE_PATH="/opt/anklume/nftables-isolation.nft"
DEST_DIR="/etc/nftables.d"
DEST_FILE="${DEST_DIR}/anklume-isolation.nft"

# ── Argument parsing ─────────────────────────────────────────

usage() {
    cat <<'USAGE'
Usage: deploy-nftables.sh [--dry-run] [--source CONTAINER_NAME]

Pulls nftables isolation rules from the admin container, validates
syntax, copies to /etc/nftables.d/, and reloads nftables.

Options:
  --dry-run             Validate only, do not install or reload
  --source CONTAINER    Source container name (default: admin-ansible)
  -h, --help            Show this help

This script must be run ON THE HOST as root (or with sudo).
USAGE
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --source)
            [[ $# -ge 2 ]] || die "--source requires a container name"
            SOURCE_CONTAINER="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            die "Unknown option: $1. Run with --help for usage."
            ;;
    esac
done

# ── Pre-flight: verify Incus daemon is accessible ──────────

if ! incus project list --format csv >/dev/null 2>&1; then
    die "Cannot connect to the Incus daemon. Check that incus is installed and you have socket access."
fi

# ── Find container project ──────────────────────────────────

find_project() {
    local container="$1"
    local project

    # Try the default project (admin) first
    if incus info "$container" --project admin &>/dev/null; then
        echo "admin"
        return 0
    fi

    # Search all projects
    project=$(incus list --all-projects --format json | python3 -c "
import json, sys
data = json.load(sys.stdin)
for item in data:
    if item.get('name') == sys.argv[1]:
        print(item.get('project', 'default'))
        sys.exit(0)
sys.exit(1)
" "$container" 2>/dev/null) || die "Container '${container}' not found in any Incus project"

    echo "$project"
}

# ── Main ─────────────────────────────────────────────────────

echo "=== AnKLuMe nftables deployment ==="

# Find container project
echo "Looking for container '${SOURCE_CONTAINER}'..."
PROJECT=$(find_project "$SOURCE_CONTAINER")
echo "Found in project: ${PROJECT}"

# Pull the rules file from the container
TMPFILE=$(mktemp /tmp/anklume-nft-XXXXXX.nft)
# shellcheck disable=SC2064
trap "rm -f '$TMPFILE'" EXIT

echo "Pulling rules from ${SOURCE_CONTAINER}:${SOURCE_PATH}..."
incus file pull "${SOURCE_CONTAINER}/${SOURCE_PATH}" "$TMPFILE" --project "$PROJECT" \
    || die "Failed to pull ${SOURCE_PATH} from ${SOURCE_CONTAINER}. Did you run 'make nftables' first?"

echo "Rules file retrieved ($(wc -l < "$TMPFILE") lines)"

# Validate content — ensure rules only modify the expected AnKLuMe table
# If this check blocks a legitimate use case, review the validation logic in
# scripts/deploy-nftables.sh lines below, or adjust the nftables template in
# roles/incus_nftables/templates/anklume-isolation.nft.j2
echo "Validating nftables content..."
if grep -qE '^\s*table\s' "$TMPFILE"; then
    NON_ANKLUME_TABLES=$(grep -E '^\s*table\s' "$TMPFILE" | grep -cv 'inet anklume' || true)
    if [[ "$NON_ANKLUME_TABLES" -gt 0 ]]; then
        echo "Offending lines:" >&2
        grep -nE '^\s*table\s' "$TMPFILE" | grep -v 'inet anklume' >&2
        die "Rules contain unexpected table definitions (expected only 'table inet anklume'). See scripts/deploy-nftables.sh content validation."
    fi
fi
# Reject dangerous patterns that should never appear in isolation rules
if grep -qiE '(flush ruleset|delete table inet filter|drop.*input.*policy)' "$TMPFILE"; then
    echo "Offending lines:" >&2
    grep -niE '(flush ruleset|delete table inet filter|drop.*input.*policy)' "$TMPFILE" >&2
    die "Rules contain dangerous patterns (flush ruleset, delete inet filter, or input drop policy). See scripts/deploy-nftables.sh content validation."
fi

# Validate syntax
echo "Validating nftables syntax..."
nft -c -f "$TMPFILE" || die "Syntax validation failed"
echo "Syntax OK"

if [[ "$DRY_RUN" == "true" ]]; then
    echo ""
    echo "--- Dry run: rules validated but NOT installed ---"
    echo "Rules content:"
    cat "$TMPFILE"
    exit 0
fi

# Install rules
echo "Installing to ${DEST_FILE}..."
mkdir -p "$DEST_DIR"
cp "$TMPFILE" "$DEST_FILE"
chmod 644 "$DEST_FILE"

# Reload nftables
echo "Applying rules..."
nft -f "$DEST_FILE" || die "Failed to apply nftables rules"

echo ""
echo "=== nftables isolation rules deployed successfully ==="
echo "Rules installed to: ${DEST_FILE}"
echo "Verify with: nft list table inet anklume"
