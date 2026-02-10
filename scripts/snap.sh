#!/usr/bin/env bash
# Snapshot management for AnKLuMe instances.
# Wraps incus snapshot commands with instance-to-project resolution.
# See docs/SPEC.md section 8 and ADR-013.
set -euo pipefail

die() { echo "ERROR: $*" >&2; exit 1; }

# ── Instance-to-project resolution ──────────────────────────

resolve_instance() {
    local name="$1"
    if [[ "$name" == "self" ]]; then
        name="${HOSTNAME:-$(hostname)}"
    fi
    echo "$name"
}

find_project() {
    local instance="$1"
    local project
    project=$(incus list --all-projects --format json | python3 -c "
import json, sys
data = json.load(sys.stdin)
for item in data:
    if item.get('name') == sys.argv[1]:
        print(item.get('project', 'default'))
        sys.exit(0)
sys.exit(1)
" "$instance" 2>/dev/null) || die "Instance '${instance}' not found in any Incus project"
    echo "$project"
}

default_snap_name() { date "+snap-%Y%m%d-%H%M%S"; }

# ── Commands ─────────────────────────────────────────────────

cmd_create() {
    [[ $# -ge 1 ]] || die "Usage: snap.sh create <instance|self> [snap-name]"
    local instance project snap_name
    instance="$(resolve_instance "$1")"
    project="$(find_project "$instance")"
    snap_name="${2:-$(default_snap_name)}"
    echo "Creating snapshot '${snap_name}' for ${instance} (project: ${project})..."
    incus snapshot create "$instance" "$snap_name" --project "$project"
    echo "Done: ${instance}/${snap_name}"
}

cmd_restore() {
    local force=false
    if [[ "${1:-}" == "--force" ]]; then
        force=true
        shift
    fi
    [[ $# -ge 2 ]] || die "Usage: snap.sh restore [--force] <instance|self> <snap-name>"
    local instance project
    instance="$(resolve_instance "$1")"
    project="$(find_project "$instance")"

    # Self-restore safety check
    local current_host="${HOSTNAME:-$(hostname)}"
    if [[ "$instance" == "$current_host" && "$force" == "false" ]]; then
        echo "WARNING: You are about to restore the instance you are currently"
        echo "running in. This will terminate your session immediately."
        echo "You will need to reconnect after the restore completes."
        echo ""
        read -rp "Type 'yes' to confirm: " confirm
        if [[ "$confirm" != "yes" ]]; then
            echo "Aborted." >&2
            exit 1
        fi
    fi

    echo "Restoring ${instance} to snapshot '${2}' (project: ${project})..."
    incus snapshot restore "$instance" "$2" --project "$project"
    echo "Done."
}

cmd_list() {
    if [[ $# -ge 1 ]]; then
        local instance project
        instance="$(resolve_instance "$1")"
        project="$(find_project "$instance")"
        echo "Snapshots for ${instance} (project: ${project}):"
        incus snapshot list "$instance" --project "$project" --format table
    else
        # List all instances from all projects
        incus list --all-projects --format json | python3 -c "
import json, sys
data = json.load(sys.stdin)
for item in data:
    print(item.get('project', 'default'), item['name'])
" | while IFS=' ' read -r project instance; do
            echo "=== ${instance} (project: ${project}) ==="
            incus snapshot list "$instance" --project "$project" --format table 2>/dev/null \
                || echo "  (no snapshots)"
            echo
        done
    fi
}

cmd_delete() {
    [[ $# -ge 2 ]] || die "Usage: snap.sh delete <instance|self> <snap-name>"
    local instance project
    instance="$(resolve_instance "$1")"
    project="$(find_project "$instance")"
    echo "Deleting snapshot '${2}' from ${instance} (project: ${project})..."
    incus snapshot delete "$instance" "$2" --project "$project"
    echo "Done."
}

# ── Entry point ──────────────────────────────────────────────

usage() {
    cat <<'USAGE'
Usage: snap.sh <command> [args]

Commands:
  create   <instance|self> [snap-name]          Create a snapshot
  restore  [--force] <instance|self> <snap-name> Restore a snapshot
  list     [instance|self]                       List snapshots
  delete   <instance|self> <snap-name>           Delete a snapshot
  help                                           Show this help

Use "self" as instance name to auto-detect from hostname.
Default snapshot name: snap-YYYYMMDD-HHMMSS

Examples:
  snap.sh create admin-ansible
  snap.sh create self my-checkpoint
  snap.sh restore admin-ansible snap-20250210-143000
  snap.sh restore self my-checkpoint
  snap.sh list
  snap.sh list self
USAGE
}

[[ $# -ge 1 ]] || { usage; exit 0; }

case "$1" in
    create)  shift; cmd_create "$@" ;;
    restore) shift; cmd_restore "$@" ;;
    list)    shift; cmd_list "$@" ;;
    delete)  shift; cmd_delete "$@" ;;
    -h|--help|help) usage ;;
    *) die "Unknown command: $1. Run 'snap.sh help' for usage." ;;
esac
