#!/usr/bin/env bash
# clipboard.sh — Controlled clipboard bridge between host and containers
#
# Usage:
#   scripts/clipboard.sh copy-to  INSTANCE [--project PROJECT]
#   scripts/clipboard.sh copy-from INSTANCE [--project PROJECT]
#   scripts/clipboard.sh history | recall | purge
#
# Security: auto-purge after paste (single-use), configurable timeout
# on copy-to, trust-level warnings for untrusted/disposable domains.
# Phase 21: Desktop Integration

set -euo pipefail

CLIPBOARD_PATH="/tmp/anklume-clipboard"
ANKLUME_CLIPBOARD_TIMEOUT="${ANKLUME_CLIPBOARD_TIMEOUT:-30}"
HISTORY_DIR="${HOME}/.anklume/clipboard"

# ── Argument parsing ─────────────────────────────────────

ACTION="" ; INSTANCE="" ; PROJECT=""

usage() {
    cat <<EOF
Usage:
  $0 copy-to  INSTANCE [--project PROJECT]  # Host -> container
  $0 copy-from INSTANCE [--project PROJECT]  # Container -> host
  $0 history                                  # List transfers
  $0 recall                                   # Recall last entry
  $0 purge                                    # Purge history

Options:
  --project PROJECT  Incus project (auto-detected if omitted)

Environment:
  ANKLUME_CLIPBOARD_TIMEOUT  Auto-purge delay in seconds (default: 30, 0=disable)
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        copy-to|copy-from|history|recall|purge) ACTION="$1"; shift ;;
        --project) PROJECT="$2"; shift 2 ;;
        --help|-h) usage; exit 0 ;;
        -*) echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
        *)  [[ -z "$INSTANCE" ]] && INSTANCE="$1"; shift ;;
    esac
done

[[ -z "$ACTION" ]] && { usage >&2; exit 1; }
if [[ "$ACTION" == "copy-to" || "$ACTION" == "copy-from" ]] && [[ -z "$INSTANCE" ]]; then
    usage >&2; exit 1
fi

# ── Clipboard backend detection ─────────────────────────

detect_clipboard_backend() {
    if [[ -n "${WAYLAND_DISPLAY:-}" ]] && command -v wl-copy &>/dev/null \
       && command -v wl-paste &>/dev/null; then echo "wayland"; return; fi
    if [[ -n "${DISPLAY:-}" ]]; then
        command -v xclip &>/dev/null && { echo "xclip"; return; }
        command -v xsel &>/dev/null && { echo "xsel"; return; }
    fi
    echo "none"
}

clipboard_error() {
    echo "ERROR: No clipboard tool found (need wl-copy/wl-paste, xclip, or xsel)" >&2
    exit 1
}

host_clipboard_get() {
    case "$(detect_clipboard_backend)" in
        wayland) wl-paste 2>/dev/null ;;
        xclip)  xclip -selection clipboard -o 2>/dev/null ;;
        xsel)   xsel --clipboard --output 2>/dev/null ;;
        none)   clipboard_error ;;
    esac
}

host_clipboard_set() {
    case "$(detect_clipboard_backend)" in
        wayland) wl-copy ;;
        xclip)  xclip -selection clipboard ;;
        xsel)   xsel --clipboard --input ;;
        none)   clipboard_error ;;
    esac
}

# ── Incus helpers ────────────────────────────────────────

incus_cmd() {
    local cmd_args=("incus")
    [[ -n "$PROJECT" ]] && cmd_args+=("--project" "$PROJECT")
    cmd_args+=("$@")
    "${cmd_args[@]}"
}

# ── Clipboard history ───────────────────────────────────

save_to_history() {
    local direction="$1" content="$2" instance="$3"
    local ts entry_dir
    ts=$(date +%Y%m%d-%H%M%S)
    entry_dir="${HISTORY_DIR}/${ts}-${direction}-${instance}"
    mkdir -p "$entry_dir"
    printf '%s' "$content" > "${entry_dir}/content"
    cat > "${entry_dir}/meta.yml" <<EOF
direction: ${direction}
instance: ${instance}
project: ${PROJECT}
timestamp: $(date -Iseconds)
size: ${#content}
EOF
}

# ── Trust level warning ─────────────────────────────────

check_trust_warning() {
    local trust
    trust=$(python3 - "$1" <<'PYEOF'
import sys, yaml
from pathlib import Path
name = sys.argv[1]
for p in [Path("infra.yml"), Path("infra/base.yml")]:
    if p.exists():
        with open(p) as f:
            infra = yaml.safe_load(f) or {}
        for dconf in infra.get("domains", {}).values():
            if name in (dconf.get("machines") or {}):
                print(dconf.get("trust_level", "")); sys.exit(0)
sys.exit(1)
PYEOF
    ) 2>/dev/null || true
    if [[ "$trust" == "untrusted" || "$trust" == "disposable" ]]; then
        echo "WARNING: Pasting from ${trust} domain — verify content before using in trusted contexts" >&2
    fi
}

# ── Resolve project if needed ───────────────────────────

if [[ "$ACTION" == "copy-to" || "$ACTION" == "copy-from" ]] && [[ -z "$PROJECT" ]]; then
    PROJECT=$(python3 - "$INSTANCE" <<'PYEOF'
import json, subprocess, sys
name = sys.argv[1]
r = subprocess.run(["incus", "list", "--all-projects", "--format", "json"],
                    capture_output=True, text=True)
if r.returncode != 0: sys.exit(1)
for i in json.loads(r.stdout):
    if i.get("name") == name:
        print(i.get("project", "default")); sys.exit(0)
sys.exit(1)
PYEOF
    ) || { echo "ERROR: Cannot find instance '$INSTANCE'. Specify --project." >&2; exit 1; }
fi

# ── Commands ─────────────────────────────────────────────

case "$ACTION" in
    copy-to)
        content=$(host_clipboard_get)
        if [[ -z "$content" ]]; then echo "Host clipboard is empty."; exit 0; fi
        printf '%s' "$content" | incus_cmd file push - "${INSTANCE}${CLIPBOARD_PATH}"
        echo "Copied ${#content} bytes: host -> ${INSTANCE} (project: ${PROJECT})"
        save_to_history "to" "$content" "$INSTANCE"
        if [[ "$ANKLUME_CLIPBOARD_TIMEOUT" -gt 0 ]]; then
            (sleep "$ANKLUME_CLIPBOARD_TIMEOUT" && \
                incus_cmd file delete "${INSTANCE}${CLIPBOARD_PATH}" 2>/dev/null) &
            disown
            echo "Auto-purge in ${ANKLUME_CLIPBOARD_TIMEOUT}s"
        fi
        ;;
    copy-from)
        check_trust_warning "$INSTANCE"
        content=$(incus_cmd file pull "${INSTANCE}${CLIPBOARD_PATH}" - 2>/dev/null) || {
            echo "Container clipboard is empty or file not found."; exit 0
        }
        if [[ -z "$content" ]]; then echo "Container clipboard is empty."; exit 0; fi
        printf '%s' "$content" | host_clipboard_set
        echo "Copied ${#content} bytes: ${INSTANCE} (project: ${PROJECT}) -> host"
        save_to_history "from" "$content" "$INSTANCE"
        incus_cmd file delete "${INSTANCE}${CLIPBOARD_PATH}" 2>/dev/null || true
        echo "Clipboard purged from container (single-use)"
        ;;
    history)
        shopt -s nullglob
        entries=("$HISTORY_DIR"/*/)
        shopt -u nullglob
        if [[ ${#entries[@]} -eq 0 ]]; then echo "No clipboard history."; exit 0; fi
        echo "Clipboard history (newest first):"
        readarray -t sorted < <(printf '%s\n' "${entries[@]}" | sort -r)
        for entry in "${sorted[@]}"; do
            [[ ! -f "$entry/meta.yml" ]] && continue
            direction=$(grep "^direction:" "$entry/meta.yml" | cut -d' ' -f2)
            instance=$(grep "^instance:" "$entry/meta.yml" | cut -d' ' -f2)
            size=$(grep "^size:" "$entry/meta.yml" | cut -d' ' -f2)
            ts=$(grep "^timestamp:" "$entry/meta.yml" | cut -d' ' -f2-)
            echo "  $(basename "$entry")  ${direction}  ${instance}  ${size}B  ${ts}"
        done
        ;;
    recall)
        latest=$(find "$HISTORY_DIR" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort -r | head -1)
        if [[ -z "$latest" || ! -f "${latest}/content" ]]; then
            echo "No clipboard history to recall."
            exit 1
        fi
        host_clipboard_set < "${latest}/content"
        echo "Recalled: $(basename "$latest")"
        ;;
    purge)
        if [[ -d "$HISTORY_DIR" ]]; then
            rm -rf "${HISTORY_DIR:?}"/*
            echo "Clipboard history purged."
        else
            echo "No clipboard history."
        fi
        ;;
esac
