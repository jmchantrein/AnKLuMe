#!/usr/bin/env bash
# snapshot-apply.sh — Pre-apply snapshot and rollback management
#
# Creates automatic snapshots before make apply, with retention policy
# and one-command rollback.
#
# Usage:
#   scripts/snapshot-apply.sh create [--limit <group>]
#   scripts/snapshot-apply.sh rollback [<timestamp>]
#   scripts/snapshot-apply.sh list
#   scripts/snapshot-apply.sh cleanup [--keep <N>]

set -euo pipefail

# ── Configuration ────────────────────────────────────────────────

SNAPSHOT_PREFIX="pre-apply"
DEFAULT_KEEP=3
STATE_DIR="${HOME}/.anklume/pre-apply-snapshots"
mkdir -p "${STATE_DIR}"

# ── Helpers ──────────────────────────────────────────────────────

timestamp() {
    date +%Y%m%d-%H%M%S
}

log_info() {
    echo "  $1"
}

log_ok() {
    echo "  OK $1"
}

log_warn() {
    echo "  WARNING: $1" >&2
}

log_error() {
    echo "  ERROR: $1" >&2
}

# ── Inventory detection ─────────────────────────────────────────

get_running_instances() {
    # Get all instances from Ansible inventory.
    # Optional arg: group name to filter by (--limit scope).
    local limit="${1:-}"

    if [[ -n "${limit}" ]]; then
        # Get hosts for a specific group only
        ansible-inventory -i inventory/ --list 2>/dev/null \
            | python3 -c "
import sys, json
data = json.load(sys.stdin)
group = '${limit}'
hosts = set()
if group in data:
    for h in data[group].get('hosts', []):
        hosts.add(h)
for h in sorted(hosts):
    print(h)
" 2>/dev/null || true
    else
        # Get all hosts
        ansible-inventory -i inventory/ --list 2>/dev/null \
            | python3 -c "
import sys, json
data = json.load(sys.stdin)
hosts = data.get('_meta', {}).get('hostvars', {})
for h in sorted(hosts):
    print(h)
" 2>/dev/null || true
    fi
}

get_instance_project() {
    # Get the Incus project for an instance from its group_vars.
    local instance="$1"
    python3 -c "
import yaml, glob, sys
for f in glob.glob('group_vars/*/vars.yml'):
    with open(f) as fh:
        data = yaml.safe_load(fh) or {}
        project = data.get('incus_project')
        if project:
            # Check if this instance belongs to this group
            group = f.split('/')[1]
            # Read inventory to check membership
            for inv in glob.glob('inventory/*.yml'):
                with open(inv) as ih:
                    inv_data = yaml.safe_load(ih) or {}
                    for g, gdata in (inv_data.get('all', {}).get('children', {}) or {}).items():
                        if g == group:
                            hosts = (gdata or {}).get('hosts', {}) or {}
                            if '${instance}' in hosts:
                                print(project)
                                sys.exit(0)
print('default')
" 2>/dev/null
}

# ── Create pre-apply snapshots ───────────────────────────────────

do_create() {
    local limit="${1:-}"
    local ts
    ts=$(timestamp)
    local snap_name="${SNAPSHOT_PREFIX}-${ts}"

    log_info "Creating pre-apply snapshots: ${snap_name}"

    # Get instances
    local instances
    instances=$(get_running_instances "${limit}")

    if [[ -z "${instances}" ]]; then
        log_warn "No instances found in inventory"
        return 0
    fi

    local count=0
    local failed=0

    while IFS= read -r instance; do
        [[ -z "${instance}" ]] && continue
        local project
        project=$(get_instance_project "${instance}")

        # Check if instance exists and is running
        if ! incus info "${instance}" --project "${project}" &>/dev/null; then
            log_warn "${instance} (project=${project}): not found, skipping"
            continue
        fi

        # Create snapshot
        if incus snapshot create "${instance}" "${snap_name}" --project "${project}" 2>/dev/null; then
            log_ok "${instance} (project=${project})"
            count=$((count + 1))
        else
            log_warn "${instance}: snapshot failed"
            failed=$((failed + 1))
        fi
    done <<< "${instances}"

    # Record this snapshot for rollback
    echo "${ts}" > "${STATE_DIR}/latest"
    echo "${snap_name}" >> "${STATE_DIR}/history"

    # Also record the limit scope if any
    if [[ -n "${limit}" ]]; then
        echo "${limit}" > "${STATE_DIR}/latest-scope"
    else
        echo "all" > "${STATE_DIR}/latest-scope"
    fi

    log_info "${count} snapshot(s) created, ${failed} failed"

    if [[ ${failed} -gt 0 ]]; then
        log_warn "Some snapshots failed. Apply will proceed but rollback may be incomplete."
    fi
}

# ── Rollback to pre-apply snapshot ───────────────────────────────

do_rollback() {
    local target_ts="${1:-}"

    # Determine which snapshot to restore
    local snap_name
    if [[ -n "${target_ts}" ]]; then
        snap_name="${SNAPSHOT_PREFIX}-${target_ts}"
    elif [[ -f "${STATE_DIR}/latest" ]]; then
        local latest_ts
        latest_ts=$(cat "${STATE_DIR}/latest")
        snap_name="${SNAPSHOT_PREFIX}-${latest_ts}"
    else
        log_error "No pre-apply snapshots found. Nothing to rollback."
        echo "  Run 'make rollback-list' to see available snapshots." >&2
        exit 1
    fi

    log_info "Rolling back to: ${snap_name}"

    # Get all instances
    local instances
    instances=$(get_running_instances)

    if [[ -z "${instances}" ]]; then
        log_error "No instances found in inventory"
        exit 1
    fi

    local count=0
    local skipped=0

    while IFS= read -r instance; do
        [[ -z "${instance}" ]] && continue
        local project
        project=$(get_instance_project "${instance}")

        if ! incus info "${instance}" --project "${project}" &>/dev/null; then
            continue
        fi

        # Check if this snapshot exists on this instance
        local has_snap
        has_snap=$(incus snapshot list "${instance}" --project "${project}" --format json 2>/dev/null \
            | python3 -c "
import sys, json
snaps = json.load(sys.stdin)
names = [s['name'] for s in snaps]
print('yes' if '${snap_name}' in names else 'no')
" 2>/dev/null || echo "no")

        if [[ "${has_snap}" != "yes" ]]; then
            skipped=$((skipped + 1))
            continue
        fi

        log_info "Restoring ${instance}..."
        if incus snapshot restore "${instance}" "${snap_name}" --project "${project}" 2>/dev/null; then
            log_ok "${instance}"
            count=$((count + 1))
        else
            log_error "${instance}: restore failed"
        fi
    done <<< "${instances}"

    log_info "${count} instance(s) restored, ${skipped} skipped (no matching snapshot)"

    if [[ ${count} -eq 0 ]]; then
        log_error "No instances were restored. Snapshot '${snap_name}' may not exist."
        echo "  Run 'make rollback-list' to see available snapshots." >&2
        exit 1
    fi
}

# ── List pre-apply snapshots ─────────────────────────────────────

do_list() {
    log_info "Pre-apply snapshots:"

    if [[ ! -f "${STATE_DIR}/history" ]]; then
        echo "  (none)"
        return 0
    fi

    # Show history with latest marker
    local latest=""
    if [[ -f "${STATE_DIR}/latest" ]]; then
        latest="${SNAPSHOT_PREFIX}-$(cat "${STATE_DIR}/latest")"
    fi

    while IFS= read -r snap_name; do
        if [[ "${snap_name}" == "${latest}" ]]; then
            echo "  ${snap_name}  <-- latest"
        else
            echo "  ${snap_name}"
        fi
    done < "${STATE_DIR}/history"
}

# ── Cleanup old pre-apply snapshots ──────────────────────────────

do_cleanup() {
    local keep="${1:-${DEFAULT_KEEP}}"

    if [[ ! -f "${STATE_DIR}/history" ]]; then
        log_info "No pre-apply snapshots to clean up"
        return 0
    fi

    # Read all snapshot names
    local total
    total=$(wc -l < "${STATE_DIR}/history")

    if [[ ${total} -le ${keep} ]]; then
        log_info "Only ${total} snapshot(s), keeping all (retention: ${keep})"
        return 0
    fi

    local to_delete=$((total - keep))
    log_info "Cleaning up: removing ${to_delete} old snapshot(s), keeping ${keep}"

    # Get the oldest snapshots to delete
    local old_snaps
    old_snaps=$(head -n "${to_delete}" "${STATE_DIR}/history")

    # Get instances
    local instances
    instances=$(get_running_instances)

    while IFS= read -r snap_name; do
        [[ -z "${snap_name}" ]] && continue

        while IFS= read -r instance; do
            [[ -z "${instance}" ]] && continue
            local project
            project=$(get_instance_project "${instance}")

            if ! incus info "${instance}" --project "${project}" &>/dev/null; then
                continue
            fi

            incus snapshot delete "${instance}" "${snap_name}" --project "${project}" 2>/dev/null || true
        done <<< "${instances}"

        log_ok "Deleted ${snap_name}"
    done <<< "${old_snaps}"

    # Update history file (keep only the last N entries)
    tail -n "${keep}" "${STATE_DIR}/history" > "${STATE_DIR}/history.tmp"
    mv "${STATE_DIR}/history.tmp" "${STATE_DIR}/history"

    log_info "Cleanup complete"
}

# ── Main dispatch ────────────────────────────────────────────────

usage() {
    echo "Usage: $0 {create|rollback|list|cleanup} [options]"
    echo ""
    echo "Commands:"
    echo "  create [--limit <group>]    Create pre-apply snapshots"
    echo "  rollback [<timestamp>]      Restore pre-apply snapshot"
    echo "  list                        List pre-apply snapshots"
    echo "  cleanup [--keep <N>]        Remove old snapshots (default: keep ${DEFAULT_KEEP})"
}

case "${1:-}" in
    create)
        shift
        limit=""
        while [[ $# -gt 0 ]]; do
            case "$1" in
                --limit) limit="$2"; shift 2 ;;
                *) log_error "Unknown option: $1"; exit 1 ;;
            esac
        done
        do_create "${limit}"
        ;;
    rollback)
        shift
        do_rollback "${1:-}"
        ;;
    list)
        do_list
        ;;
    cleanup)
        shift
        keep="${DEFAULT_KEEP}"
        while [[ $# -gt 0 ]]; do
            case "$1" in
                --keep) keep="$2"; shift 2 ;;
                *) log_error "Unknown option: $1"; exit 1 ;;
            esac
        done
        do_cleanup "${keep}"
        ;;
    *)
        usage
        exit 1
        ;;
esac
