#!/usr/bin/env bash
# domain-menu.sh — Interactive domain/instance launcher via dmenu/rofi/fuzzel
#
# Reads infra.yml to list domains and instances with trust levels, presents
# a menu via the first available launcher (fuzzel > rofi > dmenu), and
# launches the selected instance in a terminal.
#
# Usage:
#   host/desktop/domain-menu.sh             # Pick instance, open terminal
#   host/desktop/domain-menu.sh --exec CMD  # Pick instance, run command
#   host/desktop/domain-menu.sh --list      # List instances to stdout
#   host/desktop/domain-menu.sh --help      # Show this help
#
# Phase 23: Host Bootstrap and Thin Host Layer
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
INFRA_YML="$PROJECT_ROOT/infra.yml"

info()  { echo -e "\033[0;34m[INFO]\033[0m $*"; }
err()   { echo -e "\033[0;31m[ERR ]\033[0m $*" >&2; }

usage() {
    echo "Usage: $(basename "$0") [OPTIONS]"
    echo ""
    echo "Interactive domain/instance launcher for anklume."
    echo ""
    echo "Options:"
    echo "  --exec CMD   Run CMD inside the selected instance instead of a terminal"
    echo "  --list       List all instances to stdout (no menu)"
    echo "  --help       Show this help"
    echo ""
    echo "Supported launchers (first available is used):"
    echo "  fuzzel, rofi, dmenu"
    echo ""
    echo "If no launcher is found, instances are listed to stdout with"
    echo "an interactive number prompt."
    exit 0
}

trust_label() {
    local trust="$1"
    case "$trust" in
        admin)        echo "[ADMN]" ;;
        trusted)      echo "[TRST]" ;;
        semi-trusted) echo "[SEMI]" ;;
        untrusted)    echo "[NONE]" ;;
        disposable)   echo "[DISP]" ;;
        *)            echo "[????]" ;;
    esac
}

# Parse infra.yml for instances (domain, machine name, trust level)
parse_instances() {
    if [[ ! -f "$INFRA_YML" ]]; then
        err "infra.yml not found at $INFRA_YML"
        exit 1
    fi

    python3 -c "
import yaml, sys
with open('$INFRA_YML') as f:
    data = yaml.safe_load(f)
domains = data.get('domains', {})
for dname, dconf in domains.items():
    trust = dconf.get('trust_level', 'untrusted')
    machines = dconf.get('machines', {})
    for mname in machines:
        print(f'{mname}\t{dname}\t{trust}')
" 2>/dev/null || {
        # Fallback: list running Incus instances
        if command -v incus &>/dev/null; then
            incus list --format csv -c n,s 2>/dev/null | \
                while IFS=',' read -r name status; do
                    [[ "$status" == "RUNNING" ]] && echo -e "${name}\tunknown\tunknown"
                done
        fi
    }
}

detect_launcher() {
    if command -v fuzzel &>/dev/null; then
        echo "fuzzel"
    elif command -v rofi &>/dev/null; then
        echo "rofi"
    elif command -v dmenu &>/dev/null; then
        echo "dmenu"
    else
        echo "none"
    fi
}

show_menu() {
    local launcher="$1"
    local prompt="anklume instance"

    case "$launcher" in
        fuzzel) fuzzel --dmenu --prompt "$prompt > " ;;
        rofi)   rofi -dmenu -p "$prompt" ;;
        dmenu)  dmenu -p "$prompt:" ;;
        *)      return 1 ;;
    esac
}

launch_instance() {
    local instance="$1"
    local exec_cmd="${2:-}"

    if [[ -n "$exec_cmd" ]]; then
        if [[ -x "$PROJECT_ROOT/scripts/domain-exec.sh" ]]; then
            exec "$PROJECT_ROOT/scripts/domain-exec.sh" "$instance" -- $exec_cmd
        else
            exec incus exec "$instance" -- $exec_cmd
        fi
    else
        if [[ -x "$PROJECT_ROOT/scripts/domain-exec.sh" ]]; then
            exec "$PROJECT_ROOT/scripts/domain-exec.sh" "$instance" --terminal
        else
            exec incus exec "$instance" -- bash
        fi
    fi
}

main() {
    local exec_cmd=""
    local list_only=false

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --exec)  exec_cmd="$2"; shift 2 ;;
            --list)  list_only=true; shift ;;
            --help|-h) usage ;;
            *)       err "Unknown option: $1"; usage ;;
        esac
    done

    local instances
    instances=$(parse_instances)

    if [[ -z "$instances" ]]; then
        err "No instances found in infra.yml or running in Incus"
        exit 1
    fi

    # List mode
    if [[ "$list_only" == true ]]; then
        printf "%-18s %-18s %s\n" "INSTANCE" "DOMAIN" "TRUST"
        printf "%-18s %-18s %s\n" "--------" "------" "-----"
        while IFS=$'\t' read -r name domain trust; do
            printf "%-18s %-18s %s\n" "$name" "$domain" "$(trust_label "$trust")"
        done <<< "$instances"
        exit 0
    fi

    # Build menu entries
    local menu_entries=""
    while IFS=$'\t' read -r name domain trust; do
        menu_entries+="$(trust_label "$trust") ${name} (${domain})"$'\n'
    done <<< "$instances"
    menu_entries="${menu_entries%$'\n'}"

    local launcher
    launcher=$(detect_launcher)

    local selection
    if [[ "$launcher" == "none" ]]; then
        info "No menu launcher found (fuzzel/rofi/dmenu). Listing instances:"
        echo ""
        echo "$menu_entries" | nl -ba
        echo ""
        read -rp "Enter number (or name): " choice
        if [[ "$choice" =~ ^[0-9]+$ ]]; then
            selection=$(echo "$menu_entries" | sed -n "${choice}p")
        else
            selection="$choice"
        fi
    else
        selection=$(echo "$menu_entries" | show_menu "$launcher") || exit 0
    fi

    [[ -z "$selection" ]] && exit 0

    # Extract instance name from "[TRUST] name (domain)"
    local instance_name
    instance_name=$(echo "$selection" | sed 's/^\[.*\] \([^ ]*\).*/\1/')
    [[ -z "$instance_name" || "$instance_name" == "$selection" ]] && instance_name="$selection"

    info "Launching: $instance_name"
    launch_instance "$instance_name" "$exec_cmd"
}

main "$@"
