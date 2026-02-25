#!/usr/bin/env bash
# desktop-plugin.sh — Desktop environment plugin framework
# Discovers, validates, and invokes DE plugins for domain-based config.
#
# Usage:
#   desktop-plugin.sh list              # List available plugins
#   desktop-plugin.sh detect            # Detect active DE
#   desktop-plugin.sh apply [--engine X] # Apply config (auto-detect or specified)
#   desktop-plugin.sh reset [--engine X] # Reset to defaults
#   desktop-plugin.sh validate          # Validate all plugins
#
# Reads infra.yml desktop: section and delegates to the appropriate plugin.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PLUGIN_DIR="$PROJECT_ROOT/plugins/desktop"
INFRA_FILE="$PROJECT_ROOT/infra.yml"

info()  { echo -e "\033[0;34m[INFO]\033[0m $*"; }
ok()    { echo -e "\033[0;32m[ OK ]\033[0m $*"; }
warn()  { echo -e "\033[1;33m[WARN]\033[0m $*"; }
err()   { echo -e "\033[0;31m[ERR ]\033[0m $*" >&2; }

# ── Plugin discovery ──────────────────────────────────────────

list_plugins() {
    info "Available desktop plugins:"
    local found=0
    for plugin_dir in "$PLUGIN_DIR"/*/; do
        [ -d "$plugin_dir" ] || continue
        local name
        name=$(basename "$plugin_dir")
        # Skip non-plugin directories
        [ -f "$plugin_dir/detect.sh" ] || continue
        found=$((found + 1))

        local has_detect="yes"
        local has_apply="no"
        [ -f "$plugin_dir/apply.sh" ] && has_apply="yes"

        local active="no"
        if bash "$plugin_dir/detect.sh" &>/dev/null; then
            active="yes"
        fi

        printf "  %-15s detect: %-3s  apply: %-3s  active: %s\n" \
            "$name" "$has_detect" "$has_apply" "$active"
    done

    if [ "$found" -eq 0 ]; then
        warn "No plugins found in $PLUGIN_DIR"
    fi
}

# ── Plugin validation ─────────────────────────────────────────

validate_plugins() {
    info "Validating desktop plugins..."
    local errors=0

    for plugin_dir in "$PLUGIN_DIR"/*/; do
        [ -d "$plugin_dir" ] || continue
        local name
        name=$(basename "$plugin_dir")
        [ -f "$plugin_dir/detect.sh" ] || continue

        printf "  %-15s " "$name"

        # Check required scripts
        if [ ! -x "$plugin_dir/detect.sh" ]; then
            echo -e "\033[0;31mFAIL\033[0m — detect.sh not executable"
            errors=$((errors + 1))
            continue
        fi

        if [ ! -f "$plugin_dir/apply.sh" ]; then
            echo -e "\033[0;31mFAIL\033[0m — apply.sh missing"
            errors=$((errors + 1))
            continue
        fi

        if [ ! -x "$plugin_dir/apply.sh" ]; then
            echo -e "\033[0;31mFAIL\033[0m — apply.sh not executable"
            errors=$((errors + 1))
            continue
        fi

        # Shellcheck if available
        if command -v shellcheck &>/dev/null; then
            if ! shellcheck -S warning "$plugin_dir/detect.sh" &>/dev/null; then
                echo -e "\033[1;33mWARN\033[0m — detect.sh has shellcheck warnings"
                continue
            fi
        fi

        echo -e "\033[0;32mOK\033[0m"
    done

    if [ "$errors" -gt 0 ]; then
        err "$errors plugin(s) have errors"
        return 1
    fi
    ok "All plugins valid"
}

# ── DE detection ──────────────────────────────────────────────

detect_de() {
    for plugin_dir in "$PLUGIN_DIR"/*/; do
        [ -d "$plugin_dir" ] || continue
        local name
        name=$(basename "$plugin_dir")
        [ -f "$plugin_dir/detect.sh" ] || continue

        local output
        if output=$(bash "$plugin_dir/detect.sh" 2>/dev/null); then
            echo "$name"
            [ -n "$output" ] && info "Detected: $output"
            return 0
        fi
    done

    warn "No active desktop environment detected"
    return 1
}

# ── Config generation ─────────────────────────────────────────

generate_config() {
    # Generate JSON config from infra.yml for plugin consumption
    python3 - "$INFRA_FILE" <<'PYEOF'
import json
import sys
from pathlib import Path

# Add scripts/ to path for generate module
sys.path.insert(0, str(Path(sys.argv[1]).resolve().parent / "scripts"))
from generate import load_infra  # noqa: E402
from colors import TRUST_BORDER_COLORS, infer_trust_level  # noqa: E402

infra = load_infra(sys.argv[1])
domains_config = infra.get("domains", {})
global_config = infra.get("global", {})
desktop_global = global_config.get("desktop", {})

domains = []
for dname in sorted(domains_config.keys()):
    dconfig = domains_config[dname]
    if not dconfig.get("enabled", True):
        continue
    trust = infer_trust_level(dname, dconfig)
    desktop_domain = dconfig.get("desktop", {})
    machines = list((dconfig.get("machines") or {}).keys())

    domains.append({
        "name": dname,
        "trust_level": trust,
        "color": desktop_domain.get("panel_color",
                   TRUST_BORDER_COLORS.get(trust, "#888888")),
        "wallpaper": desktop_domain.get("wallpaper", ""),
        "pinned_apps": desktop_domain.get("pinned_apps", []),
        "machines": machines,
    })

config = {
    "project_name": infra.get("project_name", "anklume"),
    "virtual_desktops": desktop_global.get("virtual_desktops", "auto"),
    "window_borders": desktop_global.get("window_borders", "trust_level"),
    "domains": domains,
}

print(json.dumps(config, indent=2))
PYEOF
}

# ── Apply / Reset ─────────────────────────────────────────────

apply_config() {
    local engine="${1:-}"
    local dry_run="${2:-false}"

    # Auto-detect if no engine specified
    if [ -z "$engine" ]; then
        engine=$(detect_de 2>/dev/null) || {
            err "No desktop environment detected. Use --engine to specify one."
            return 1
        }
    fi

    local plugin_dir="$PLUGIN_DIR/$engine"
    if [ ! -f "$plugin_dir/apply.sh" ]; then
        err "Plugin '$engine' not found or has no apply.sh"
        return 1
    fi

    if [ ! -f "$INFRA_FILE" ]; then
        err "infra.yml not found at $INFRA_FILE"
        return 1
    fi

    info "Generating config from infra.yml..."
    local config
    config=$(generate_config)

    if [ "$dry_run" = true ]; then
        info "Dry run — generated config:"
        echo "$config"
        echo "---"
        echo "$config" | bash "$plugin_dir/apply.sh" --dry-run
    else
        info "Applying $engine config..."
        echo "$config" | bash "$plugin_dir/apply.sh"
        ok "Desktop configuration applied via $engine plugin"
    fi
}

reset_config() {
    local engine="${1:-}"

    if [ -z "$engine" ]; then
        engine=$(detect_de 2>/dev/null) || {
            err "No desktop environment detected. Use --engine to specify one."
            return 1
        }
    fi

    local plugin_dir="$PLUGIN_DIR/$engine"
    if [ ! -f "$plugin_dir/apply.sh" ]; then
        err "Plugin '$engine' not found"
        return 1
    fi

    info "Resetting $engine config..."
    bash "$plugin_dir/apply.sh" --reset
    ok "Desktop configuration reset"
}

# ── Main ──────────────────────────────────────────────────────

usage() {
    echo "Usage: $(basename "$0") <command> [options]"
    echo ""
    echo "Commands:"
    echo "  list              List available desktop plugins"
    echo "  detect            Detect active desktop environment"
    echo "  apply [--engine X] [--dry-run]  Apply domain config"
    echo "  reset [--engine X] Reset to defaults"
    echo "  validate          Validate all plugins"
    echo ""
    echo "Options:"
    echo "  --engine NAME     Force a specific DE plugin"
    echo "  --dry-run         Preview changes without applying"
    exit 0
}

COMMAND="${1:-help}"
shift || true

ENGINE=""
DRY_RUN=false

while [ $# -gt 0 ]; do
    case "$1" in
        --engine)  ENGINE="$2"; shift 2 ;;
        --dry-run) DRY_RUN=true; shift ;;
        --help)    usage ;;
        *) err "Unknown option: $1"; exit 1 ;;
    esac
done

case "$COMMAND" in
    list)     list_plugins ;;
    detect)   detect_de ;;
    apply)    apply_config "$ENGINE" "$DRY_RUN" ;;
    reset)    reset_config "$ENGINE" ;;
    validate) validate_plugins ;;
    help)     usage ;;
    *)        err "Unknown command: $COMMAND"; usage ;;
esac
