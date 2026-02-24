#!/usr/bin/env bash
# export-desktops.sh — Install anklume .desktop files to user menu
#
# Generates .desktop files via desktop_config.py and installs them to
# ~/.local/share/applications/ for XDG desktop integration.
#
# Idempotent: safe to re-run at any time.
#
# Usage:
#   host/desktop/export-desktops.sh           # Install .desktop files
#   host/desktop/export-desktops.sh --remove  # Uninstall .desktop files
#   host/desktop/export-desktops.sh --help    # Show this help
#
# Phase 23: Host Bootstrap and Thin Host Layer
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DESKTOP_DIR="$PROJECT_ROOT/desktop"
INSTALL_DIR="${HOME}/.local/share/applications"

info()  { echo -e "\033[0;34m[INFO]\033[0m $*"; }
ok()    { echo -e "\033[0;32m[ OK ]\033[0m $*"; }
warn()  { echo -e "\033[1;33m[WARN]\033[0m $*"; }
err()   { echo -e "\033[0;31m[ERR ]\033[0m $*" >&2; }

usage() {
    echo "Usage: $(basename "$0") [--remove] [--help]"
    echo ""
    echo "Install or remove anklume .desktop files."
    echo ""
    echo "Options:"
    echo "  --remove   Uninstall all anklume-*.desktop files from user menu"
    echo "  --help     Show this help"
    exit 0
}

remove_desktops() {
    info "Removing anklume .desktop files from ${INSTALL_DIR}..."
    local count=0
    for f in "${INSTALL_DIR}"/anklume-*.desktop; do
        [[ -f "$f" ]] || continue
        rm -f "$f"
        info "  Removed $(basename "$f")"
        count=$((count + 1))
    done

    if [[ $count -eq 0 ]]; then
        ok "No anklume .desktop files found to remove"
    else
        ok "Removed $count .desktop file(s)"
    fi

    if command -v update-desktop-database &>/dev/null; then
        update-desktop-database "$INSTALL_DIR" 2>/dev/null || true
    fi
}

install_desktops() {
    # Generate .desktop files via desktop_config.py
    if [[ -f "$PROJECT_ROOT/scripts/desktop_config.py" ]]; then
        info "Generating .desktop files via desktop_config.py..."
        python3 "$PROJECT_ROOT/scripts/desktop_config.py" --desktop
    else
        warn "scripts/desktop_config.py not found, using existing desktop/ files"
    fi

    if ! ls "${DESKTOP_DIR}"/anklume-*.desktop &>/dev/null; then
        err "No anklume-*.desktop files found in ${DESKTOP_DIR}/"
        err "Ensure desktop_config.py --desktop generates files into desktop/"
        exit 1
    fi

    mkdir -p "$INSTALL_DIR"

    local count=0
    for f in "${DESKTOP_DIR}"/anklume-*.desktop; do
        [[ -f "$f" ]] || continue
        cp -f "$f" "$INSTALL_DIR/"
        info "  Installed $(basename "$f")"
        count=$((count + 1))
    done

    if [[ $count -eq 0 ]]; then
        warn "No .desktop files were installed"
    else
        ok "Installed $count .desktop file(s) to ${INSTALL_DIR}/"
    fi

    if command -v update-desktop-database &>/dev/null; then
        update-desktop-database "$INSTALL_DIR" 2>/dev/null || true
        ok "Desktop database updated"
    fi
}

main() {
    case "${1:-}" in
        --remove)  remove_desktops ;;
        --help|-h) usage ;;
        "")        install_desktops ;;
        *)         err "Unknown option: $1"; usage ;;
    esac
}

main "$@"
