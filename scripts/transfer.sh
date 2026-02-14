#!/usr/bin/env bash
# File transfer and backup for AnKLuMe instances.
# Wraps incus file/export/import commands with instance-to-project resolution.
# See docs/file-transfer.md and ROADMAP.md Phase 20d.
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

# ── Parse instance:path format ────────────────────────────────

parse_instance_path() {
    local spec="$1"
    if [[ "$spec" != *:* ]]; then
        die "Invalid format: '${spec}'. Expected instance:/path"
    fi
    local instance="${spec%%:*}"
    local path="${spec#*:}"
    if [[ -z "$instance" || -z "$path" ]]; then
        die "Invalid format: '${spec}'. Both instance and path are required (instance:/path)"
    fi
    echo "${instance}" "${path}"
}

# ── Commands ─────────────────────────────────────────────────

cmd_copy() {
    [[ $# -ge 2 ]] || die "Usage: transfer.sh copy <instance:/path> <instance:/path>"
    check_incus

    local src_spec="$1"
    local dst_spec="$2"

    local src_instance src_path dst_instance dst_path
    read -r src_instance src_path <<< "$(parse_instance_path "$src_spec")"
    read -r dst_instance dst_path <<< "$(parse_instance_path "$dst_spec")"

    local src_project dst_project
    src_project="$(find_project "$src_instance")"
    dst_project="$(find_project "$dst_instance")"

    echo "Copying ${src_instance}:${src_path} -> ${dst_instance}:${dst_path}"
    echo "  Source project: ${src_project}, Destination project: ${dst_project}"

    incus file pull "${src_instance}${src_path}" - --project "$src_project" \
        | incus file push - "${dst_instance}${dst_path}" --project "$dst_project"

    echo "Done."
}

cmd_backup() {
    local gpg_recipient=""
    local output_dir="backups"
    local force=false

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --gpg-recipient) gpg_recipient="$2"; shift 2 ;;
            --output)        output_dir="$2"; shift 2 ;;
            --force)         force=true; shift ;;
            -*)              die "Unknown option: $1" ;;
            *)               break ;;
        esac
    done

    [[ $# -ge 1 ]] || die "Usage: transfer.sh backup [--gpg-recipient ID] [--output DIR] <instance>"
    check_incus

    local instance="$1"
    local project
    project="$(find_project "$instance")"

    mkdir -p "$output_dir"
    local timestamp
    timestamp="$(date +%Y%m%d-%H%M%S)"
    local backup_file="${output_dir}/${instance}-${timestamp}.tar.gz"

    if [[ -f "$backup_file" && "$force" == "false" ]]; then
        die "Backup file already exists: ${backup_file}. Use --force to overwrite."
    fi

    echo "Exporting ${instance} (project: ${project}) to ${backup_file}..."
    incus export "$instance" "$backup_file" --project "$project"

    if [[ -n "$gpg_recipient" ]]; then
        echo "Encrypting with GPG recipient: ${gpg_recipient}..."
        gpg --encrypt --recipient "$gpg_recipient" --output "${backup_file}.gpg" "$backup_file"
        rm -f "$backup_file"
        backup_file="${backup_file}.gpg"
        echo "Encrypted backup: ${backup_file}"
    fi

    echo "Done: ${backup_file}"
}

cmd_restore() {
    local new_name=""
    local project=""
    local force=false

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --name)    new_name="$2"; shift 2 ;;
            --project) project="$2"; shift 2 ;;
            --force)   force=true; shift ;;
            -*)        die "Unknown option: $1" ;;
            *)         break ;;
        esac
    done

    [[ $# -ge 1 ]] || die "Usage: transfer.sh restore [--name NEW_NAME] [--project PROJECT] <backup-file>"
    check_incus

    local backup_file="$1"
    [[ -f "$backup_file" ]] || die "Backup file not found: ${backup_file}"

    # Decrypt if GPG encrypted
    local import_file="$backup_file"
    if [[ "$backup_file" == *.gpg ]]; then
        echo "Decrypting GPG-encrypted backup..."
        import_file="${backup_file%.gpg}"
        gpg --decrypt --output "$import_file" "$backup_file"
    fi

    local import_args=()
    if [[ -n "$project" ]]; then
        import_args+=(--project "$project")
    fi

    echo "Importing ${import_file}..."
    if [[ -n "$new_name" ]]; then
        incus import "$import_file" "${import_args[@]}" --alias "$new_name"
        echo "Done: imported as ${new_name}"
    else
        incus import "$import_file" "${import_args[@]}"
        echo "Done: imported from ${import_file}"
    fi

    # Clean up decrypted file if we created one
    if [[ "$backup_file" == *.gpg && -f "$import_file" ]]; then
        rm -f "$import_file"
    fi
}

# ── Entry point ──────────────────────────────────────────────

usage() {
    cat <<'USAGE'
Usage: transfer.sh <command> [options] [args]

Commands:
  copy     <src_instance:/path> <dst_instance:/path>   Copy file between instances
  backup   [options] <instance>                         Export instance to backup
  restore  [options] <backup-file>                      Import instance from backup
  help                                                  Show this help

Copy:
  transfer.sh copy pro-dev:/etc/config admin-ctrl:/tmp/config

Backup options:
  --gpg-recipient ID   Encrypt backup with GPG
  --output DIR         Output directory (default: backups/)
  --force              Overwrite existing backup file

Restore options:
  --name NEW_NAME      Import with a different instance name
  --project PROJECT    Target Incus project
  --force              Force import

Examples:
  transfer.sh copy pro-dev:/etc/hosts perso-desktop:/tmp/hosts
  transfer.sh backup homelab-ai
  transfer.sh backup --gpg-recipient user@example.com --output /mnt/backup admin-ansible
  transfer.sh restore backups/homelab-ai-20260214-120000.tar.gz
  transfer.sh restore --name homelab-ai-v2 --project homelab backups/homelab-ai.tar.gz
  transfer.sh restore backups/admin-ansible.tar.gz.gpg
USAGE
}

[[ $# -ge 1 ]] || { usage; exit 0; }

case "$1" in
    copy)    shift; cmd_copy "$@" ;;
    backup)  shift; cmd_backup "$@" ;;
    restore) shift; cmd_restore "$@" ;;
    -h|--help|help) usage ;;
    *) die "Unknown command: $1. Run 'transfer.sh help' for usage." ;;
esac
