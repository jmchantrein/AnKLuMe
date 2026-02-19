#!/usr/bin/env bash
# export-app.sh — Export container applications as native host apps
#
# Usage:
#   scripts/export-app.sh export I=<instance> APP=<app> [--project PROJECT]
#   scripts/export-app.sh list   [I=<instance>] [--project PROJECT]
#   scripts/export-app.sh remove I=<instance> APP=<app>
#   scripts/export-app.sh --help
#
# Exports container .desktop files to the host, creating wrapper .desktop
# files that launch the app via incus exec with domain-colored terminal.
# Icons are extracted and placed in ~/.local/share/icons/anklume/.
#
# Phase 26: Native App Export (distrobox-export Style)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

DESKTOP_DIR="${HOME}/.local/share/applications"
ICON_DIR="${HOME}/.local/share/icons/anklume"

ACTION=""
INSTANCE=""
APP=""
PROJECT=""

# ── Helper functions ─────────────────────────────────────

info()  { echo -e "\033[0;34m[INFO]\033[0m $*"; }
ok()    { echo -e "\033[0;32m[ OK ]\033[0m $*"; }
warn()  { echo -e "\033[1;33m[WARN]\033[0m $*"; }
err()   { echo -e "\033[0;31m[ERR ]\033[0m $*" >&2; }

die() {
    err "$@"
    exit 1
}

# ── Argument parsing ─────────────────────────────────────

usage() {
    echo "Usage: $0 <export|list|remove> [OPTIONS]"
    echo ""
    echo "Commands:"
    echo "  export   Export a container app to the host desktop"
    echo "  list     List exported apps, or available apps in a container"
    echo "  remove   Remove an exported app from the host desktop"
    echo ""
    echo "Options:"
    echo "  I=<instance>       Instance name (required for export/remove)"
    echo "  APP=<app>          Application name (required for export/remove)"
    echo "  --project PROJECT  Incus project (auto-detected if omitted)"
    echo ""
    echo "Examples:"
    echo "  $0 export I=pro-dev APP=firefox"
    echo "  $0 list"
    echo "  $0 list I=pro-dev"
    echo "  $0 remove I=pro-dev APP=firefox"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        export|list|remove)
            ACTION="$1"
            shift
            ;;
        I=*)
            INSTANCE="${1#I=}"
            shift
            ;;
        APP=*)
            APP="${1#APP=}"
            shift
            ;;
        --project)
            PROJECT="$2"
            shift 2
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        -*)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 1
            ;;
        *)
            # Positional: if no instance yet, treat as instance; else as app
            if [[ -z "$INSTANCE" ]]; then
                INSTANCE="$1"
            elif [[ -z "$APP" ]]; then
                APP="$1"
            fi
            shift
            ;;
    esac
done

if [[ -z "$ACTION" ]]; then
    usage >&2
    exit 1
fi

# ── Resolve domain and project from infra.yml ───────────

resolve_context() {
    python3 - "$1" "$PROJECT_DIR" <<'PYEOF'
import json, subprocess, sys, yaml
from pathlib import Path

instance_name = sys.argv[1]
project_dir = Path(sys.argv[2])

# Try to resolve project from Incus
project = ""
result = subprocess.run(
    ["incus", "list", "--all-projects", "--format", "json"],
    capture_output=True, text=True
)
if result.returncode == 0:
    for inst in json.loads(result.stdout):
        if inst.get("name") == instance_name:
            project = inst.get("project", "default")
            break

# Try to resolve domain from infra.yml
domain = project  # domain name == project name in anklume
trust_level = "trusted"

infra_path = project_dir / "infra.yml"
if infra_path.exists():
    with open(infra_path) as f:
        infra = yaml.safe_load(f) or {}
    for dname, dconfig in infra.get("domains", {}).items():
        machines = dconfig.get("machines", {})
        if instance_name in machines:
            domain = dname
            trust_level = dconfig.get("trust_level", "")
            if not trust_level:
                if "admin" in dname.lower():
                    trust_level = "admin"
                elif dconfig.get("ephemeral", False):
                    trust_level = "disposable"
                else:
                    trust_level = "trusted"
            break

print(f"{domain}\t{trust_level}\t{project}")
PYEOF
}

# ── Incus helpers ────────────────────────────────────────

incus_exec() {
    local cmd=("incus" "exec")
    if [[ -n "$PROJECT" ]]; then
        cmd+=("--project" "$PROJECT")
    fi
    cmd+=("$INSTANCE" "--" "$@")
    "${cmd[@]}"
}

incus_file_pull() {
    local cmd=("incus" "file" "pull")
    if [[ -n "$PROJECT" ]]; then
        cmd+=("--project" "$PROJECT")
    fi
    cmd+=("$@")
    "${cmd[@]}"
}

# ── Export command ───────────────────────────────────────

cmd_export() {
    if [[ -z "$INSTANCE" ]]; then
        die "I=<instance> is required for export. See --help."
    fi
    if [[ -z "$APP" ]]; then
        die "APP=<app> is required for export. See --help."
    fi

    # Resolve domain context
    local domain="unknown" trust_level="trusted" resolved_project=""
    if IFS=$'\t' read -r domain trust_level resolved_project < <(resolve_context "$INSTANCE"); then
        if [[ -z "$PROJECT" && -n "$resolved_project" ]]; then
            PROJECT="$resolved_project"
        fi
    fi

    info "Exporting '$APP' from instance '$INSTANCE' (domain: $domain)..."

    # Step 1: Find .desktop file in container
    local desktop_path
    desktop_path=$(incus_exec find /usr/share/applications -name "*${APP}*.desktop" -print -quit 2>/dev/null) || true

    if [[ -z "$desktop_path" ]]; then
        die "No .desktop file matching '*${APP}*' found in $INSTANCE:/usr/share/applications/"
    fi

    info "Found desktop file: $desktop_path"

    # Step 2: Pull .desktop content from container
    local tmp_desktop
    tmp_desktop=$(mktemp /tmp/anklume-export-XXXXXX.desktop)
    trap "rm -f '$tmp_desktop'" EXIT

    incus_file_pull "${INSTANCE}${desktop_path}" "$tmp_desktop" 2>/dev/null \
        || die "Failed to pull $desktop_path from $INSTANCE"

    # Step 3: Parse Exec= and Icon= lines
    local orig_exec orig_icon app_name
    orig_exec=$(grep -m1 '^Exec=' "$tmp_desktop" | sed 's/^Exec=//')
    orig_icon=$(grep -m1 '^Icon=' "$tmp_desktop" | sed 's/^Icon=//')
    app_name=$(grep -m1 '^Name=' "$tmp_desktop" | sed 's/^Name=//')

    if [[ -z "$orig_exec" ]]; then
        die "No Exec= line found in $desktop_path"
    fi

    info "Original Exec: $orig_exec"
    info "Original Icon: $orig_icon"

    # Step 4: Extract icon from container
    local host_icon=""
    if [[ -n "$orig_icon" ]]; then
        host_icon=$(extract_icon "$orig_icon" "$domain")
    fi

    # Step 5: Generate host .desktop file
    mkdir -p "$DESKTOP_DIR"
    local safe_app
    safe_app=$(echo "$APP" | tr '[:upper:]' '[:lower:]' | tr -cs '[:alnum:]-' '-' | sed 's/-$//')
    local desktop_file="${DESKTOP_DIR}/anklume-${domain}-${safe_app}.desktop"

    # Build the wrapper Exec line using domain-exec.sh
    local wrapper_exec="${SCRIPT_DIR}/domain-exec.sh ${INSTANCE}"
    if [[ -n "$PROJECT" ]]; then
        wrapper_exec+=" --project ${PROJECT}"
    fi
    wrapper_exec+=" -- ${orig_exec}"

    # Write the new .desktop file
    {
        echo "[Desktop Entry]"
        echo "Type=Application"
        echo "Name=[${domain}] ${app_name:-$APP}"
        echo "Comment=AnKLuMe: ${APP} in ${INSTANCE} (${domain})"
        echo "Exec=${wrapper_exec}"
        if [[ -n "$host_icon" && -f "$host_icon" ]]; then
            echo "Icon=${host_icon}"
        elif [[ -n "$orig_icon" ]]; then
            echo "Icon=${orig_icon}"
        fi
        echo "Terminal=false"
        echo "Categories=AnKLuMe;${domain};"
        echo "StartupNotify=true"
        echo "X-AnKLuMe-Instance=${INSTANCE}"
        echo "X-AnKLuMe-Domain=${domain}"
        echo "X-AnKLuMe-App=${APP}"
    } > "$desktop_file"

    chmod +x "$desktop_file"

    # Step 6: Update desktop database
    if command -v update-desktop-database &>/dev/null; then
        update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
    fi

    ok "Exported '${APP}' from ${INSTANCE} -> ${desktop_file}"
}

# ── Extract icon from container ──────────────────────────

extract_icon() {
    local icon_name="$1"
    local domain="$2"

    mkdir -p "$ICON_DIR"

    # If icon is a full path, pull it directly
    if [[ "$icon_name" == /* ]]; then
        local ext="${icon_name##*.}"
        local dest="${ICON_DIR}/anklume-${domain}-${APP}.${ext}"
        if incus_file_pull "${INSTANCE}${icon_name}" "$dest" 2>/dev/null; then
            info "Extracted icon: $dest"
            echo "$dest"
            return
        fi
    fi

    # Search common icon paths in the container
    local icon_dirs=(
        "/usr/share/icons/hicolor/128x128/apps"
        "/usr/share/icons/hicolor/64x64/apps"
        "/usr/share/icons/hicolor/48x48/apps"
        "/usr/share/icons/hicolor/scalable/apps"
        "/usr/share/pixmaps"
    )

    for dir in "${icon_dirs[@]}"; do
        local found
        found=$(incus_exec find "$dir" -name "${icon_name}.*" -print -quit 2>/dev/null) || true
        if [[ -n "$found" ]]; then
            local ext="${found##*.}"
            local dest="${ICON_DIR}/anklume-${domain}-${APP}.${ext}"
            if incus_file_pull "${INSTANCE}${found}" "$dest" 2>/dev/null; then
                info "Extracted icon: $dest"
                echo "$dest"
                return
            fi
        fi
    done

    warn "Could not extract icon '$icon_name' from container"
}

# ── List command ─────────────────────────────────────────

cmd_list() {
    if [[ -n "$INSTANCE" ]]; then
        # List available apps in a container
        info "Available .desktop apps in '$INSTANCE':"

        # Resolve project if needed
        if [[ -z "$PROJECT" ]]; then
            local domain trust_level resolved_project
            if IFS=$'\t' read -r domain trust_level resolved_project < <(resolve_context "$INSTANCE"); then
                if [[ -n "$resolved_project" ]]; then
                    PROJECT="$resolved_project"
                fi
            fi
        fi

        incus_exec find /usr/share/applications -name '*.desktop' -printf '%f\n' 2>/dev/null \
            | sort \
            | while read -r f; do
                echo "  $f"
            done
        return
    fi

    # List exported apps on the host
    info "Exported AnKLuMe apps:"
    local count=0
    for f in "${DESKTOP_DIR}"/anklume-*.desktop; do
        [[ -f "$f" ]] || continue
        local fname
        fname=$(basename "$f")
        local inst domain app_label
        inst=$(grep -m1 '^X-AnKLuMe-Instance=' "$f" 2>/dev/null | sed 's/^X-AnKLuMe-Instance=//' || true)
        domain=$(grep -m1 '^X-AnKLuMe-Domain=' "$f" 2>/dev/null | sed 's/^X-AnKLuMe-Domain=//' || true)
        app_label=$(grep -m1 '^X-AnKLuMe-App=' "$f" 2>/dev/null | sed 's/^X-AnKLuMe-App=//' || true)
        echo "  ${fname}  (instance: ${inst:-?}, domain: ${domain:-?}, app: ${app_label:-?})"
        count=$((count + 1))
    done

    if [[ $count -eq 0 ]]; then
        info "No exported apps found."
        info "Export an app with: $0 export I=<instance> APP=<app>"
    else
        ok "$count exported app(s)"
    fi
}

# ── Remove command ───────────────────────────────────────

cmd_remove() {
    if [[ -z "$INSTANCE" ]]; then
        die "I=<instance> is required for remove. See --help."
    fi
    if [[ -z "$APP" ]]; then
        die "APP=<app> is required for remove. See --help."
    fi

    local safe_app
    safe_app=$(echo "$APP" | tr '[:upper:]' '[:lower:]' | tr -cs '[:alnum:]-' '-' | sed 's/-$//')

    local removed=0

    # Remove matching .desktop files
    for f in "${DESKTOP_DIR}"/anklume-*-"${safe_app}".desktop; do
        [[ -f "$f" ]] || continue
        # Verify instance matches
        local inst
        inst=$(grep -m1 '^X-AnKLuMe-Instance=' "$f" 2>/dev/null | sed 's/^X-AnKLuMe-Instance=//' || true)
        if [[ "$inst" == "$INSTANCE" ]]; then
            rm -f "$f"
            info "Removed desktop file: $(basename "$f")"
            removed=$((removed + 1))
        fi
    done

    # Remove matching icon files
    for f in "${ICON_DIR}"/anklume-*-"${safe_app}".*; do
        [[ -f "$f" ]] || continue
        rm -f "$f"
        info "Removed icon: $(basename "$f")"
    done

    # Update desktop database
    if command -v update-desktop-database &>/dev/null; then
        update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
    fi

    if [[ $removed -eq 0 ]]; then
        warn "No exported app '${APP}' found for instance '${INSTANCE}'"
    else
        ok "Removed ${removed} export(s) for '${APP}' from '${INSTANCE}'"
    fi
}

# ── Main dispatch ────────────────────────────────────────

case "$ACTION" in
    export) cmd_export ;;
    list)   cmd_list   ;;
    remove) cmd_remove ;;
    *)
        err "Unknown action: $ACTION"
        usage >&2
        exit 1
        ;;
esac
