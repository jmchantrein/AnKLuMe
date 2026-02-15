#!/usr/bin/env bash
# clipboard.sh — Controlled clipboard bridge between host and containers
#
# Usage:
#   scripts/clipboard.sh copy-to  INSTANCE [--project PROJECT]
#   scripts/clipboard.sh copy-from INSTANCE [--project PROJECT]
#   scripts/clipboard.sh --help
#
# Bridges the host Wayland/X11 clipboard with a container's clipboard
# file (/tmp/anklume-clipboard). Each transfer is an explicit user
# action — no automatic clipboard sync between domains.
#
# Supports: wl-copy/wl-paste (Wayland), xclip (X11), xsel (X11 fallback)
#
# Phase 21: Desktop Integration

set -euo pipefail

CLIPBOARD_PATH="/tmp/anklume-clipboard"

# ── Argument parsing ─────────────────────────────────────

ACTION=""
INSTANCE=""
PROJECT=""

usage() {
    echo "Usage: $0 <copy-to|copy-from> INSTANCE [--project PROJECT]"
    echo ""
    echo "Commands:"
    echo "  copy-to    Copy host clipboard content INTO the container"
    echo "  copy-from  Copy container clipboard content TO the host"
    echo ""
    echo "Options:"
    echo "  --project PROJECT  Incus project for the instance"
    echo ""
    echo "Examples:"
    echo "  $0 copy-to pro-dev --project pro    # Host → container"
    echo "  $0 copy-from pro-dev --project pro   # Container → host"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        copy-to|copy-from)
            ACTION="$1"
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
            if [[ -z "$INSTANCE" ]]; then
                INSTANCE="$1"
            fi
            shift
            ;;
    esac
done

if [[ -z "$ACTION" || -z "$INSTANCE" ]]; then
    usage >&2
    exit 1
fi

# ── Clipboard backend detection ─────────────────────────

detect_clipboard_backend() {
    if [[ -n "${WAYLAND_DISPLAY:-}" ]]; then
        if command -v wl-copy &>/dev/null && command -v wl-paste &>/dev/null; then
            echo "wayland"
            return
        fi
    fi
    if [[ -n "${DISPLAY:-}" ]]; then
        if command -v xclip &>/dev/null; then
            echo "xclip"
            return
        fi
        if command -v xsel &>/dev/null; then
            echo "xsel"
            return
        fi
    fi
    echo "none"
}

host_clipboard_get() {
    local backend
    backend=$(detect_clipboard_backend)
    case "$backend" in
        wayland) wl-paste 2>/dev/null ;;
        xclip)  xclip -selection clipboard -o 2>/dev/null ;;
        xsel)   xsel --clipboard --output 2>/dev/null ;;
        none)
            echo "ERROR: No clipboard tool found (need wl-copy/wl-paste, xclip, or xsel)" >&2
            exit 1
            ;;
    esac
}

host_clipboard_set() {
    local backend
    backend=$(detect_clipboard_backend)
    case "$backend" in
        wayland) wl-copy ;;
        xclip)  xclip -selection clipboard ;;
        xsel)   xsel --clipboard --input ;;
        none)
            echo "ERROR: No clipboard tool found (need wl-copy/wl-paste, xclip, or xsel)" >&2
            exit 1
            ;;
    esac
}

# ── Incus helpers ────────────────────────────────────────

incus_cmd() {
    local cmd_args=("incus")
    if [[ -n "$PROJECT" ]]; then
        cmd_args+=("--project" "$PROJECT")
    fi
    cmd_args+=("$@")
    "${cmd_args[@]}"
}

# Resolve project if not specified
if [[ -z "$PROJECT" ]]; then
    PROJECT=$(python3 - "$INSTANCE" <<'PYEOF'
import json, subprocess, sys
name = sys.argv[1]
result = subprocess.run(
    ["incus", "list", "--all-projects", "--format", "json"],
    capture_output=True, text=True
)
if result.returncode != 0:
    sys.exit(1)
for inst in json.loads(result.stdout):
    if inst.get("name") == name:
        print(inst.get("project", "default"))
        sys.exit(0)
print("default", file=sys.stderr)
sys.exit(1)
PYEOF
    ) || {
        echo "ERROR: Cannot find instance '$INSTANCE'. Specify --project." >&2
        exit 1
    }
fi

# ── Commands ─────────────────────────────────────────────

case "$ACTION" in
    copy-to)
        content=$(host_clipboard_get)
        if [[ -z "$content" ]]; then
            echo "Host clipboard is empty."
            exit 0
        fi
        printf '%s' "$content" | incus_cmd file push - "${INSTANCE}${CLIPBOARD_PATH}"
        size=${#content}
        echo "Copied $size bytes: host → ${INSTANCE} (project: ${PROJECT})"
        ;;

    copy-from)
        content=$(incus_cmd file pull "${INSTANCE}${CLIPBOARD_PATH}" - 2>/dev/null) || {
            echo "Container clipboard is empty or file not found."
            exit 0
        }
        if [[ -z "$content" ]]; then
            echo "Container clipboard is empty."
            exit 0
        fi
        printf '%s' "$content" | host_clipboard_set
        size=${#content}
        echo "Copied $size bytes: ${INSTANCE} (project: ${PROJECT}) → host"
        ;;
esac
