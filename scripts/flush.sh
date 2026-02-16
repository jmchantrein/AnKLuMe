#!/usr/bin/env bash
# flush.sh — Destroy all anklume infrastructure
# Usage: scripts/flush.sh [--force]
#
# Destroys: all Incus instances, profiles, projects, and net-* bridges
#           managed by anklume. Also removes generated Ansible files.
# Preserves: infra.yml, roles/, scripts/, docs/, CLAUDE.md
#
# Safety: requires --force on production (absolute_level == 0 and yolo != true)

set -euo pipefail

FORCE=false
for arg in "$@"; do
    case "$arg" in
        --force) FORCE=true ;;
        *) echo "Usage: $0 [--force]"; exit 1 ;;
    esac
done

# Safety check: production requires --force
ABS_LEVEL=""
YOLO=""
if [ -f /etc/anklume/absolute_level ]; then
    ABS_LEVEL=$(cat /etc/anklume/absolute_level)
fi
if [ -f /etc/anklume/yolo ]; then
    YOLO=$(cat /etc/anklume/yolo)
fi

if [ "$ABS_LEVEL" = "0" ] && [ "$YOLO" != "true" ] && [ "$FORCE" != "true" ]; then
    echo "ERROR: Running on production host (absolute_level=0, yolo=false)."
    echo "       Use 'make flush FORCE=true' to confirm destruction."
    exit 1
fi

echo "=== anklume Flush ==="
echo "This will destroy ALL anklume infrastructure."

# Pre-flight: verify Incus daemon is accessible
if ! incus project list --format csv >/dev/null 2>&1; then
    echo "ERROR: Cannot connect to the Incus daemon."
    echo "       Check that incus is installed and you have socket access."
    echo "       (Run from the anklume container or a user in the 'incus' group)"
    exit 1
fi

if [ "$FORCE" != "true" ]; then
    read -rp "Type 'yes' to confirm: " confirm
    if [ "$confirm" != "yes" ]; then
        echo "Aborted."
        exit 0
    fi
fi

deleted=0

# Helper: list projects as one-per-line (strip " (current)" suffix from CSV)
_list_projects() {
    incus project list --format csv -c n 2>/dev/null | sed 's/ (current)$//'
}

# 1. Destroy instances in all projects
echo "--- Destroying instances ---"
while IFS= read -r project; do
    while IFS= read -r instance; do
        [ -z "$instance" ] && continue
        echo "  Deleting: $instance (project: $project)"
        if incus delete "$instance" --project "$project" --force; then
            deleted=$((deleted + 1))
        else
            echo "  WARNING: Failed to delete $instance (project: $project)"
        fi
    done < <(incus list --project "$project" --format csv -c n 2>/dev/null)
done < <(_list_projects)

# 2. Delete cached images in non-default projects (blocks project deletion)
echo "--- Deleting cached images ---"
while IFS= read -r project; do
    [ "$project" = "default" ] && continue
    while IFS= read -r fingerprint; do
        [ -z "$fingerprint" ] && continue
        echo "  Deleting image: ${fingerprint:0:12} (project: $project)"
        if incus image delete "$fingerprint" --project "$project" 2>/dev/null; then
            deleted=$((deleted + 1))
        fi
    done < <(incus image list --project "$project" --format csv -c f 2>/dev/null)
done < <(_list_projects)

# 3. Delete non-default profiles in all projects
echo "--- Deleting profiles ---"
while IFS= read -r project; do
    while IFS= read -r profile; do
        [ -z "$profile" ] && continue
        [ "$profile" = "default" ] && continue
        echo "  Deleting profile: $profile (project: $project)"
        if incus profile delete "$profile" --project "$project"; then
            deleted=$((deleted + 1))
        fi
    done < <(incus profile list --project "$project" --format csv -c n 2>/dev/null)
done < <(_list_projects)

# 4. Reset default profile in non-default projects (remove device references to net-* bridges)
echo "--- Resetting default profiles ---"
while IFS= read -r project; do
    [ "$project" = "default" ] && continue
    # Remove all devices from default profile so it no longer references bridges
    for device in $(incus profile device list default --project "$project" --format csv 2>/dev/null | cut -d, -f1); do
        [ -z "$device" ] && continue
        echo "  Removing device '$device' from default profile (project: $project)"
        incus profile device remove default "$device" --project "$project" 2>/dev/null || true
    done
done < <(_list_projects)

# 5. Delete non-default projects (now empty: no instances, images, or device refs)
echo "--- Deleting projects ---"
while IFS= read -r project; do
    [ "$project" = "default" ] && continue
    echo "  Deleting project: $project"
    if incus project delete "$project"; then
        deleted=$((deleted + 1))
    else
        echo "  WARNING: Failed to delete project $project"
    fi
done < <(_list_projects)

# 6. Delete anklume bridges (net-*) — now unreferenced by any project
echo "--- Deleting bridges ---"
while IFS= read -r bridge; do
    [ -z "$bridge" ] && continue
    echo "  Deleting bridge: $bridge"
    if incus network delete "$bridge"; then
        deleted=$((deleted + 1))
    else
        echo "  WARNING: Failed to delete bridge $bridge"
    fi
done < <(incus network list --format csv -c n 2>/dev/null | grep "^net-")

# 7. Remove generated Ansible files
echo "--- Removing generated files ---"
for dir in inventory group_vars host_vars; do
    if [ -d "$dir" ]; then
        echo "  Removing: $dir/"
        rm -rf "$dir"
        deleted=$((deleted + 1))
    fi
done

echo ""
if [ "$deleted" -eq 0 ]; then
    echo "Nothing to flush (no anklume resources found)."
else
    echo "Flush complete: $deleted resources destroyed."
fi
echo "Run 'make sync && make apply' to rebuild."
