#!/usr/bin/env bash
# domain-lib.sh — Shared functions for domain-exec.sh and export-app.sh
#
# Source this file, do not execute directly.
# Provides: resolve_context(), trust_to_hex(), setup_audio(), setup_display()
#
# Phase 19b: Desktop Integration (DRY extraction)

# Guard: prevent direct execution
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "ERROR: domain-lib.sh must be sourced, not executed directly." >&2
    exit 1
fi

# ── Logging helpers ─────────────────────────────────────────

domlib_info()  { echo -e "\033[0;34m[INFO]\033[0m $*"; }
domlib_warn()  { echo -e "\033[1;33m[WARN]\033[0m $*" >&2; }
domlib_err()   { echo -e "\033[0;31m[ERR ]\033[0m $*" >&2; }

# ── Resolve domain and trust level ──────────────────────────
#
# Usage: IFS=$'\t' read -r DOMAIN TRUST_LEVEL PROJECT < <(resolve_context INSTANCE PROJECT_DIR)
#
# Outputs tab-separated: domain\ttrust_level\tproject

resolve_context() {
    local instance="$1"
    local project_dir="$2"
    python3 - "$instance" "$project_dir" <<'PYEOF'
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

# Try to resolve trust level from infra.yml
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

# ── Trust level to color mapping ────────────────────────────

trust_to_hex() {
    case "$1" in
        admin)        echo "#00005f" ;;
        trusted)      echo "#005f00" ;;
        semi-trusted) echo "#5f5f00" ;;
        untrusted)    echo "#5f0000" ;;
        disposable)   echo "#5f005f" ;;
        *)            echo "#1a1a1a" ;;
    esac
}

# ── PipeWire audio forwarding ────────────────────────────
#
# Expects: $INSTANCE, $DOMLIB_PROJECT_ARGS (array)
# Sets:    AUDIO_ENV (array)

AUDIO_ENV=()

setup_audio() {
    local host_uid
    host_uid=$(id -u "${SUDO_USER:-$USER}" 2>/dev/null || echo 1000)
    local runtime="/run/user/${host_uid}"
    local pw_sock="${runtime}/pipewire-0"

    [[ -S "$pw_sock" ]] || return 0

    local devices=(
        "anklume-pw:${runtime}/pipewire-0:/tmp/pipewire-0"
    )
    if [[ -S "${runtime}/pulse/native" ]]; then
        devices+=("anklume-pa:${runtime}/pulse/native:/tmp/pulse-native")
    fi

    for entry in "${devices[@]}"; do
        IFS=: read -r dev_name host_path container_path <<< "$entry"
        incus config device add "${DOMLIB_PROJECT_ARGS[@]}" "$INSTANCE" \
            "$dev_name" proxy \
            bind=container \
            "connect=unix:${host_path}" \
            "listen=unix:${container_path}" \
            uid=0 gid=0 mode=0777 2>/dev/null || true
    done

    # shellcheck disable=SC2034  # Used by sourcing script
    AUDIO_ENV=(
        "PIPEWIRE_REMOTE=/tmp/pipewire-0"
        "PULSE_SERVER=unix:/tmp/pulse-native"
    )
}

# ── Wayland/X11/GPU display forwarding ───────────────────
#
# Expects: $INSTANCE, $TRUST_LEVEL, $DOMAIN, $DOMLIB_PROJECT_ARGS (array)
# Sets:    DISPLAY_ENV (array)

DISPLAY_ENV=()

setup_display() {
    local host_uid
    host_uid=$(id -u "${SUDO_USER:-$USER}" 2>/dev/null || echo 1000)
    local runtime="/run/user/${host_uid}"
    local wl_sock="${runtime}/wayland-0"

    # Security warning for untrusted/disposable domains
    if [[ "$TRUST_LEVEL" == "untrusted" || "$TRUST_LEVEL" == "disposable" ]]; then
        domlib_warn "GUI forwarding to ${TRUST_LEVEL} domain '${DOMAIN}'"
        domlib_warn "Display access grants keylogging and screen capture capability."
    fi

    # Wayland socket
    if [[ -S "$wl_sock" ]]; then
        incus config device add "${DOMLIB_PROJECT_ARGS[@]}" "$INSTANCE" \
            anklume-wl proxy \
            bind=container \
            "connect=unix:${wl_sock}" \
            "listen=unix:/tmp/wayland-0" \
            uid=0 gid=0 mode=0777 2>/dev/null || true
    fi

    # X11 socket (Xwayland compatibility)
    if [[ -S "/tmp/.X11-unix/X0" ]]; then
        incus config device add "${DOMLIB_PROJECT_ARGS[@]}" "$INSTANCE" \
            anklume-x11 proxy \
            bind=container \
            "connect=unix:/tmp/.X11-unix/X0" \
            "listen=unix:/tmp/.X11-unix/X0" \
            uid=0 gid=0 mode=0777 2>/dev/null || true
    fi

    # GPU device (renders via host GPU driver)
    incus config device add "${DOMLIB_PROJECT_ARGS[@]}" "$INSTANCE" \
        anklume-gpu gpu 2>/dev/null || true

    # shellcheck disable=SC2034  # Used by sourcing script
    DISPLAY_ENV=(
        "WAYLAND_DISPLAY=wayland-0"
        "XDG_RUNTIME_DIR=/tmp"
        "DISPLAY=:0"
        "GDK_BACKEND=wayland,x11"
        "QT_QPA_PLATFORM=wayland;xcb"
    )
}
