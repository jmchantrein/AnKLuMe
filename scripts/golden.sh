#!/usr/bin/env bash
# Golden image management for anklume instances.
# Create, derive (CoW copy), and publish golden images from instances.
# See docs/golden-images.md and ROADMAP.md Phase 20b.
set -euo pipefail

die() { echo "ERROR: $*" >&2; exit 1; }

# ── Pre-flight: verify Incus daemon is accessible ────────────

check_incus() {
    if ! incus project list --format csv >/dev/null 2>&1; then
        die "Cannot connect to the Incus daemon. Check that incus is installed and you have socket access."
    fi
}

# ── Instance-to-project resolution ──────────────────────────

find_project() {
    local instance="$1"
    local json project
    json=$(incus list --all-projects --format json)
    project=$(python3 -c "
import json, sys
data = json.loads(sys.argv[2])
for item in data:
    if item.get('name') == sys.argv[1]:
        print(item.get('project', 'default'))
        sys.exit(0)
sys.exit(1)
" "$instance" "$json" 2>/dev/null) || die "Instance '${instance}' not found in any Incus project"
    echo "$project"
}

# ── Commands ─────────────────────────────────────────────────

cmd_create() {
    [[ $# -ge 1 ]] || die "Usage: golden.sh create <instance> [--project PROJECT]"
    local instance="$1"
    shift
    local project=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --project) project="$2"; shift 2 ;;
            *) die "Unknown option: $1" ;;
        esac
    done

    check_incus

    if [[ -z "$project" ]]; then
        project="$(find_project "$instance")"
    fi

    # Verify instance exists and get its status
    local json status
    json=$(incus list --project "$project" --format json)
    status=$(python3 -c "
import json, sys
data = json.loads(sys.argv[2])
for item in data:
    if item.get('name') == sys.argv[1]:
        print(item.get('status', 'Unknown'))
        sys.exit(0)
print('NotFound')
" "$instance" "$json")

    if [[ "$status" == "NotFound" ]]; then
        die "Instance '${instance}' not found in project '${project}'"
    fi

    # Stop instance if running
    if [[ "$status" == "Running" ]]; then
        echo "Stopping ${instance} (project: ${project})..."
        incus stop "$instance" --project "$project"
    fi

    # Check if pristine snapshot already exists
    local snap_json has_pristine
    snap_json=$(incus snapshot list "$instance" --project "$project" --format json)
    has_pristine=$(python3 -c "
import json, sys
data = json.loads(sys.argv[1])
for snap in data:
    if snap.get('name') == 'pristine':
        print('yes')
        sys.exit(0)
print('no')
" "$snap_json")

    if [[ "$has_pristine" == "yes" ]]; then
        echo "Deleting existing 'pristine' snapshot..."
        incus snapshot delete "$instance" pristine --project "$project"
    fi

    echo "Creating golden snapshot 'pristine' for ${instance} (project: ${project})..."
    incus snapshot create "$instance" pristine --project "$project"
    echo "Done: ${instance}/pristine is now a golden image."
    echo "Derive new instances with: golden.sh derive ${instance} <new-name>"
}

cmd_derive() {
    [[ $# -ge 2 ]] || die "Usage: golden.sh derive <template> <new-instance> [--project PROJECT]"
    local template="$1"
    local new_instance="$2"
    shift 2
    local project=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --project) project="$2"; shift 2 ;;
            *) die "Unknown option: $1" ;;
        esac
    done

    check_incus

    if [[ -z "$project" ]]; then
        project="$(find_project "$template")"
    fi

    echo "Deriving '${new_instance}' from '${template}/pristine' (project: ${project})..."
    echo "Note: uses CoW on ZFS/Btrfs backends, full copy on dir backend."
    incus copy "${template}/pristine" "$new_instance" --project "$project"
    echo "Done: ${new_instance} created from ${template}/pristine."
    echo "Start it with: incus start ${new_instance} --project ${project}"
}

cmd_publish() {
    [[ $# -ge 2 ]] || die "Usage: golden.sh publish <template> <alias> [--project PROJECT]"
    local template="$1"
    local alias="$2"
    shift 2
    local project=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --project) project="$2"; shift 2 ;;
            *) die "Unknown option: $1" ;;
        esac
    done

    check_incus

    if [[ -z "$project" ]]; then
        project="$(find_project "$template")"
    fi

    echo "Publishing '${template}/pristine' as image '${alias}' (project: ${project})..."
    incus publish "${template}/pristine" --project "$project" --alias "$alias"
    echo "Done: image '${alias}' published."
    echo "Use in infra.yml as: os_image: \"${alias}\""
}

cmd_list() {
    local project=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --project) project="$2"; shift 2 ;;
            *) die "Unknown option: $1" ;;
        esac
    done

    check_incus

    echo "Golden images (instances with 'pristine' snapshot):"
    echo ""

    if [[ -n "$project" ]]; then
        _list_project "$project"
    else
        # List across all projects
        local proj_json
        proj_json=$(incus project list --format json)
        python3 -c "
import json, sys
data = json.loads(sys.argv[1])
for p in data:
    print(p.get('name', 'default'))
" "$proj_json" | while IFS= read -r proj; do
            _list_project "$proj"
        done
    fi
}

_list_project() {
    local proj="$1"
    local json
    json=$(incus list --project "$proj" --format json 2>/dev/null) || return 0
    python3 -c "
import json, sys
data = json.loads(sys.argv[2])
project = sys.argv[1]
for instance in data:
    name = instance.get('name', '')
    snapshots = instance.get('snapshots') or []
    for snap in snapshots:
        if snap.get('name') == 'pristine':
            created = snap.get('created_at', 'unknown')[:19]
            print(f'  {name:<30s} project={project:<15s} created={created}')
            break
" "$proj" "$json"
}

# ── Entry point ──────────────────────────────────────────────

usage() {
    cat <<'USAGE'
Usage: golden.sh <command> [args]

Commands:
  create   <instance> [--project P]              Stop + snapshot as 'pristine'
  derive   <template> <new-name> [--project P]   Copy from pristine (CoW)
  publish  <template> <alias> [--project P]      Publish as reusable Incus image
  list     [--project P]                          List golden images
  help                                            Show this help

Options:
  --project PROJECT   Incus project (auto-detected if omitted)

Golden images are instances with a 'pristine' snapshot. The 'derive'
command uses 'incus copy' which leverages CoW (Copy-on-Write) on
ZFS and Btrfs storage backends for efficient disk usage.

Examples:
  golden.sh create pro-dev                  # Stop + snapshot
  golden.sh derive pro-dev pro-dev-copy     # CoW copy
  golden.sh publish pro-dev my-golden-image # Publish as image
  golden.sh list                            # List all golden images
  golden.sh list --project admin            # List in specific project
USAGE
}

[[ $# -ge 1 ]] || { usage; exit 0; }

case "$1" in
    create)  shift; cmd_create "$@" ;;
    derive)  shift; cmd_derive "$@" ;;
    publish) shift; cmd_publish "$@" ;;
    list)    shift; cmd_list "$@" ;;
    -h|--help|help) usage ;;
    *) die "Unknown command: $1. Run 'golden.sh help' for usage." ;;
esac
