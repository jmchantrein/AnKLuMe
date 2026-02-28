#!/usr/bin/env bash
# domain-exec.sh — Launch commands in containers with domain context
#
# Usage:
#   scripts/domain-exec.sh INSTANCE [OPTIONS] [--] [COMMAND...]
#
# Options:
#   --project PROJECT  Incus project (auto-detected if omitted)
#   --terminal         Open a new terminal window with domain colors
#   --gui              Forward Wayland/X11 display and GPU into container
#
# Phase 21: Desktop Integration

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck source=domain-lib.sh
source "$SCRIPT_DIR/domain-lib.sh"

INSTANCE=""
PROJECT=""
TERMINAL=false
GUI=false
CMD_ARGS=()

# ── Argument parsing ─────────────────────────────────────

usage() {
    echo "Usage: $0 INSTANCE [OPTIONS] [--] [COMMAND...]"
    echo ""
    echo "Options:"
    echo "  --project PROJECT  Incus project (auto-detected if omitted)"
    echo "  --terminal         Open a new terminal window with domain colors"
    echo "  --gui              Forward Wayland/X11 display and GPU into container"
    echo ""
    echo "If no COMMAND is given, opens an interactive bash shell."
    echo ""
    echo "Examples:"
    echo "  $0 pro-dev                          # Interactive shell"
    echo "  $0 pro-dev -- htop                  # Run htop in container"
    echo "  $0 pro-dev --terminal               # Colored terminal window"
    echo "  $0 pro-dev --gui -- firefox          # GUI app on host display"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --project)
            PROJECT="$2"
            shift 2
            ;;
        --terminal)
            TERMINAL=true
            shift
            ;;
        --gui)
            GUI=true
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        --)
            shift
            CMD_ARGS=("$@")
            break
            ;;
        -*)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 1
            ;;
        *)
            if [[ -z "$INSTANCE" ]]; then
                INSTANCE="$1"
            else
                CMD_ARGS+=("$1")
            fi
            shift
            ;;
    esac
done

if [[ -z "$INSTANCE" ]]; then
    usage >&2
    exit 1
fi

# ── Resolve domain and trust level ───────────────────────

IFS=$'\t' read -r DOMAIN TRUST_LEVEL RESOLVED_PROJECT \
    < <(resolve_context "$INSTANCE" "$PROJECT_DIR")

if [[ -z "$PROJECT" && -n "$RESOLVED_PROJECT" ]]; then
    PROJECT="$RESOLVED_PROJECT"
fi

BG_COLOR=$(trust_to_hex "$TRUST_LEVEL")

# Shared project args for setup_audio/setup_display (from domain-lib.sh)
# shellcheck disable=SC2034  # Used by setup_audio/setup_display in domain-lib.sh
DOMLIB_PROJECT_ARGS=()
if [[ -n "$PROJECT" ]]; then
    # shellcheck disable=SC2034
    DOMLIB_PROJECT_ARGS=("--project" "$PROJECT")
fi

# ── Device forwarding ────────────────────────────────────

setup_audio

if [[ "$GUI" == "true" ]]; then
    setup_display
fi

# ── Build incus exec command ─────────────────────────────

build_exec_cmd() {
    local exec_cmd=("incus" "exec")
    if [[ -n "$PROJECT" ]]; then
        exec_cmd+=("--project" "$PROJECT")
    fi
    exec_cmd+=("$INSTANCE" "--" "env"
        "ANKLUME_DOMAIN=$DOMAIN"
        "ANKLUME_TRUST_LEVEL=$TRUST_LEVEL"
        "ANKLUME_INSTANCE=$INSTANCE"
        "${AUDIO_ENV[@]}"
        "${DISPLAY_ENV[@]}"
    )
    if [[ ${#CMD_ARGS[@]} -gt 0 ]]; then
        exec_cmd+=("${CMD_ARGS[@]}")
    else
        exec_cmd+=("bash")
    fi
    echo "${exec_cmd[@]}"
}

EXEC_CMD=$(build_exec_cmd)

# ── Terminal mode ────────────────────────────────────────

if [[ "$TERMINAL" == "true" ]]; then
    TITLE="[${DOMAIN}] ${INSTANCE}"

    if command -v foot &>/dev/null; then
        exec foot \
            --title "$TITLE" \
            --override "colors.background=$BG_COLOR" \
            -- bash -c "$EXEC_CMD"
    elif command -v alacritty &>/dev/null; then
        exec alacritty \
            --title "$TITLE" \
            -e bash -c "$EXEC_CMD"
    elif command -v xterm &>/dev/null; then
        exec xterm \
            -title "$TITLE" \
            -bg "$BG_COLOR" \
            -e bash -c "$EXEC_CMD"
    else
        echo "No terminal emulator found (need foot, alacritty, or xterm)" >&2
        exit 1
    fi
fi

# ── Direct mode ──────────────────────────────────────────

exec $EXEC_CMD
