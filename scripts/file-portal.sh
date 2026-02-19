#!/usr/bin/env bash
# file-portal.sh — Controlled file sharing between host and containers
#
# Usage:
#   scripts/file-portal.sh open  I=<instance> PATH=<path> [--project PROJECT]
#   scripts/file-portal.sh push  I=<instance> SRC=<host-path> DST=<container-path> [--project PROJECT]
#   scripts/file-portal.sh pull  I=<instance> SRC=<container-path> DST=<host-path> [--project PROJECT]
#   scripts/file-portal.sh list  [--project PROJECT]
#   scripts/file-portal.sh --help
#
# Reads file_portal configuration from the domain's infra.yml to enforce
# allowed_paths and read_only policies. All transfers are logged to
# ~/.anklume/portal-audit.log.
#
# Phase 25: XDG Desktop Portal for Cross-Domain File Access

set -euo pipefail

AUDIT_LOG="$HOME/.anklume/portal-audit.log"

# ── Helpers ──────────────────────────────────────────────

die() { echo "ERROR: $*" >&2; exit 1; }
info() { echo "INFO: $*"; }

audit_log() {
    local action="$1" instance="$2" paths="$3"
    local timestamp
    timestamp="$(date '+%Y-%m-%dT%H:%M:%S%z')"
    mkdir -p "$(dirname "$AUDIT_LOG")"
    echo "${timestamp} action=${action} instance=${instance} ${paths}" >> "$AUDIT_LOG"
}

# ── Argument parsing ─────────────────────────────────────

ACTION=""
INSTANCE=""
SRC=""
DST=""
FILE_PATH=""
PROJECT=""

usage() {
    cat <<'USAGE'
Usage: file-portal.sh <command> [options] [args]

Commands:
  open   I=<instance> PATH=<path>                      Open file from container via xdg-open
  push   I=<instance> SRC=<host-path> DST=<ctr-path>   Push file from host to container
  pull   I=<instance> SRC=<ctr-path> DST=<host-path>   Pull file from container to host
  list                                                  List configured file portals
  help                                                  Show this help

Options:
  --project PROJECT   Incus project for the instance

Examples:
  file-portal.sh open  ai-coder /shared/ai-tools/report.pdf
  file-portal.sh push  ai-coder ~/docs/input.txt /shared/ai-tools/input.txt
  file-portal.sh pull  ai-coder /shared/ai-tools/output.csv ~/results/output.csv
  file-portal.sh list
USAGE
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        open|push|pull|list)
            ACTION="$1"
            shift
            ;;
        --project)
            PROJECT="$2"
            shift 2
            ;;
        --help|-h|help)
            usage
            exit 0
            ;;
        -*)
            die "Unknown option: $1"
            ;;
        *)
            # Positional arguments: depend on ACTION
            if [[ -z "$INSTANCE" ]]; then
                INSTANCE="$1"
            elif [[ "$ACTION" == "open" && -z "$FILE_PATH" ]]; then
                FILE_PATH="$1"
            elif [[ -z "$SRC" ]]; then
                SRC="$1"
            elif [[ -z "$DST" ]]; then
                DST="$1"
            fi
            shift
            ;;
    esac
done

# ── Validate arguments ───────────────────────────────────

case "$ACTION" in
    open)
        [[ -n "$INSTANCE" ]] || die "Instance required. Usage: file-portal.sh open <instance> <path>"
        [[ -n "$FILE_PATH" ]] || die "Path required. Usage: file-portal.sh open <instance> <path>"
        ;;
    push)
        [[ -n "$INSTANCE" ]] || die "Instance required. Usage: file-portal.sh push <instance> <src> <dst>"
        [[ -n "$SRC" ]] || die "SRC required. Usage: file-portal.sh push <instance> <src> <dst>"
        [[ -n "$DST" ]] || die "DST required. Usage: file-portal.sh push <instance> <src> <dst>"
        ;;
    pull)
        [[ -n "$INSTANCE" ]] || die "Instance required. Usage: file-portal.sh pull <instance> <src> <dst>"
        [[ -n "$SRC" ]] || die "SRC required. Usage: file-portal.sh pull <instance> <src> <dst>"
        [[ -n "$DST" ]] || die "DST required. Usage: file-portal.sh pull <instance> <src> <dst>"
        ;;
    list)
        ;;  # No extra args needed
    "")
        usage
        exit 0
        ;;
    *)
        die "Unknown command: $ACTION. Run 'file-portal.sh help' for usage."
        ;;
esac

# ── Instance-to-project resolution ──────────────────────

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

if [[ -n "$INSTANCE" && -z "$PROJECT" ]]; then
    PROJECT="$(find_project "$INSTANCE")"
fi

# ── Incus helpers ────────────────────────────────────────

incus_cmd() {
    local cmd_args=("incus")
    if [[ -n "$PROJECT" ]]; then
        cmd_args+=("--project" "$PROJECT")
    fi
    cmd_args+=("$@")
    "${cmd_args[@]}"
}

# ── Policy: read file_portal config from infra.yml ──────

check_policy() {
    local instance="$1" container_path="$2" action="$3"
    local policy_result
    policy_result=$(python3 - "$instance" "$container_path" "$action" <<'PYEOF'
import sys, os

instance = sys.argv[1]
container_path = sys.argv[2]
action = sys.argv[3]

# Find infra.yml — walk up from script location or cwd
def find_infra():
    for base in [os.path.dirname(os.path.abspath(__file__)), os.getcwd()]:
        d = base
        for _ in range(10):
            for candidate in ["infra.yml", "infra/base.yml"]:
                p = os.path.join(d, candidate)
                if os.path.isfile(p):
                    return p
            d = os.path.dirname(d)
    return None

try:
    import yaml
except ImportError:
    # Fallback: allow everything if pyyaml not installed
    print("ALLOW")
    sys.exit(0)

infra_path = find_infra()
if not infra_path:
    print("ALLOW")
    sys.exit(0)

with open(infra_path) as f:
    infra = yaml.safe_load(f)

# Find the domain containing this instance
domains = infra.get("domains", {})
file_portal = None
for dname, dconf in domains.items():
    if not isinstance(dconf, dict):
        continue
    machines = dconf.get("machines", {})
    if instance in machines:
        file_portal = dconf.get("file_portal")
        break

if file_portal is None:
    # No portal config — allow by default
    print("ALLOW")
    sys.exit(0)

# Check read_only
read_only = file_portal.get("read_only", False)
if read_only and action == "push":
    print("DENY:read_only")
    sys.exit(0)

# Check allowed_paths
allowed_paths = file_portal.get("allowed_paths", [])
if not allowed_paths:
    print("ALLOW")
    sys.exit(0)

for ap in allowed_paths:
    if container_path.startswith(ap):
        print("ALLOW")
        sys.exit(0)

print("DENY:path_not_allowed")
PYEOF
    ) || die "Policy check failed"

    if [[ "$policy_result" == DENY:read_only ]]; then
        die "Push blocked: domain is configured as read_only for file portal"
    elif [[ "$policy_result" == DENY:path_not_allowed ]]; then
        die "Path '${container_path}' not in allowed_paths for this domain's file portal"
    fi
    # ALLOW — continue
}

# ── Commands ─────────────────────────────────────────────

cmd_open() {
    local instance="$1" path="$2"
    check_policy "$instance" "$path" "pull"

    local tmpdir
    tmpdir="$(mktemp -d "/tmp/anklume-portal-XXXXXX")"
    local filename
    filename="$(basename "$path")"
    local local_path="${tmpdir}/${filename}"

    info "Pulling ${instance}:${path} to temporary file..."
    incus_cmd file pull "${instance}${path}" "$local_path"
    audit_log "open" "$instance" "src=${path} local=${local_path}"

    info "Opening ${local_path} with xdg-open..."
    xdg-open "$local_path" &
}

cmd_push() {
    local instance="$1" src="$2" dst="$3"
    check_policy "$instance" "$dst" "push"

    [[ -f "$src" ]] || die "Source file not found: ${src}"

    info "Pushing ${src} -> ${instance}:${dst}..."
    incus_cmd file push "$src" "${instance}${dst}"
    audit_log "push" "$instance" "src=${src} dst=${dst}"

    local size
    size="$(stat -c%s "$src" 2>/dev/null || stat -f%z "$src" 2>/dev/null || echo "?")"
    info "Pushed ${size} bytes: ${src} -> ${instance}:${dst} (project: ${PROJECT})"
}

cmd_pull() {
    local instance="$1" src="$2" dst="$3"
    check_policy "$instance" "$src" "pull"

    info "Pulling ${instance}:${src} -> ${dst}..."
    mkdir -p "$(dirname "$dst")"
    incus_cmd file pull "${instance}${src}" "$dst"
    audit_log "pull" "$instance" "src=${src} dst=${dst}"

    local size
    size="$(stat -c%s "$dst" 2>/dev/null || stat -f%z "$dst" 2>/dev/null || echo "?")"
    info "Pulled ${size} bytes: ${instance}:${src} -> ${dst} (project: ${PROJECT})"
}

cmd_list() {
    python3 - <<'PYEOF'
import os, sys

def find_infra():
    for base in [os.getcwd()]:
        d = base
        for _ in range(10):
            for candidate in ["infra.yml", "infra/base.yml"]:
                p = os.path.join(d, candidate)
                if os.path.isfile(p):
                    return p
            d = os.path.dirname(d)
    return None

try:
    import yaml
except ImportError:
    print("pyyaml not installed — cannot read infra.yml")
    sys.exit(1)

infra_path = find_infra()
if not infra_path:
    print("No infra.yml found.")
    sys.exit(0)

with open(infra_path) as f:
    infra = yaml.safe_load(f)

domains = infra.get("domains", {})
found = False
for dname, dconf in sorted(domains.items()):
    if not isinstance(dconf, dict):
        continue
    fp = dconf.get("file_portal")
    if fp:
        found = True
        allowed = fp.get("allowed_paths", [])
        ro = fp.get("read_only", False)
        print(f"Domain: {dname}")
        print(f"  allowed_paths: {allowed}")
        print(f"  read_only:     {ro}")
        print()

if not found:
    print("No file_portal configuration found in any domain.")
PYEOF
}

# ── Dispatch ─────────────────────────────────────────────

case "$ACTION" in
    open) cmd_open "$INSTANCE" "$FILE_PATH" ;;
    push) cmd_push "$INSTANCE" "$SRC" "$DST" ;;
    pull) cmd_pull "$INSTANCE" "$SRC" "$DST" ;;
    list) cmd_list ;;
esac
