#!/usr/bin/env bash
# flush.sh — Destroy all AnKLuMe infrastructure
# Usage: scripts/flush.sh [--force]
#
# Destroys: all Incus instances, profiles, projects, and net-* bridges
#           managed by AnKLuMe. Also removes generated Ansible files.
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

echo "=== AnKLuMe Flush ==="
echo "This will destroy ALL AnKLuMe infrastructure."

# Pre-flight: verify Incus daemon is accessible
if ! incus project list --format csv >/dev/null 2>&1; then
    echo "ERROR: Cannot connect to the Incus daemon."
    echo "       Check that incus is installed and you have socket access."
    echo "       (Run from the admin container or a user in the 'incus' group)"
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

# 1. Destroy instances in all projects
echo "--- Destroying instances ---"
for project in $(incus project list --format csv | cut -d, -f1); do
    for instance in $(incus list --project "$project" --format csv -c n 2>/dev/null); do
        echo "  Deleting: $instance (project: $project)"
        if incus delete "$instance" --project "$project" --force; then
            deleted=$((deleted + 1))
        else
            echo "  WARNING: Failed to delete $instance (project: $project)"
        fi
    done
done

# 2. Delete non-default profiles in all projects
echo "--- Deleting profiles ---"
for project in $(incus project list --format csv | cut -d, -f1); do
    for profile in $(incus profile list --project "$project" --format csv -c n 2>/dev/null); do
        if [ "$profile" != "default" ]; then
            echo "  Deleting profile: $profile (project: $project)"
            if incus profile delete "$profile" --project "$project"; then
                deleted=$((deleted + 1))
            else
                echo "  WARNING: Failed to delete profile $profile (project: $project)"
            fi
        fi
    done
done

# 3. Delete non-default projects
echo "--- Deleting projects ---"
for project in $(incus project list --format csv | cut -d, -f1); do
    if [ "$project" != "default" ]; then
        echo "  Deleting project: $project"
        if incus project delete "$project"; then
            deleted=$((deleted + 1))
        else
            echo "  WARNING: Failed to delete project $project"
        fi
    fi
done

# 4. Delete AnKLuMe bridges (net-*)
echo "--- Deleting bridges ---"
for bridge in $(incus network list --format csv -c n | grep "^net-"); do
    echo "  Deleting bridge: $bridge"
    if incus network delete "$bridge"; then
        deleted=$((deleted + 1))
    else
        echo "  WARNING: Failed to delete bridge $bridge"
    fi
done

# 5. Remove generated Ansible files
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
    echo "Nothing to flush (no AnKLuMe resources found)."
else
    echo "Flush complete: $deleted resources destroyed."
fi
echo "Run 'make sync && make apply' to rebuild."
