#!/usr/bin/env bash
# domain-exec.sh — Launch commands in containers with domain context
#
# Usage:
#   scripts/domain-exec.sh INSTANCE [--] [COMMAND...]
#   scripts/domain-exec.sh INSTANCE --project PROJECT [--] [COMMAND...]
#   scripts/domain-exec.sh INSTANCE --terminal [--] [COMMAND...]
#
# Wrapper around `incus exec` that:
# 1. Resolves the instance's domain and trust level
# 2. Sets ANKLUME_* environment variables inside the container
# 3. Optionally opens a terminal with domain-colored background
#
# Environment variables set inside the container:
#   ANKLUME_DOMAIN      — domain name
#   ANKLUME_TRUST_LEVEL — trust level (admin, trusted, etc.)
#   ANKLUME_INSTANCE    — instance name
#
# Phase 21: Desktop Integration

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

INSTANCE=""
PROJECT=""
TERMINAL=false
CMD_ARGS=()

# ── Argument parsing ─────────────────────────────────────

usage() {
    echo "Usage: $0 INSTANCE [OPTIONS] [--] [COMMAND...]"
    echo ""
    echo "Options:"
    echo "  --project PROJECT  Incus project (auto-detected if omitted)"
    echo "  --terminal         Open a new terminal window with domain colors"
    echo ""
    echo "If no COMMAND is given, opens an interactive bash shell."
    echo ""
    echo "Examples:"
    echo "  $0 pro-dev                          # Interactive shell"
    echo "  $0 pro-dev -- htop                  # Run htop in container"
    echo "  $0 pro-dev --terminal               # Colored terminal window"
    echo "  $0 pro-dev --terminal -- firefox     # Firefox in colored terminal"
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

resolve_context() {
    python3 - "$INSTANCE" "$PROJECT_DIR" <<'PYEOF'
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

IFS=$'\t' read -r DOMAIN TRUST_LEVEL RESOLVED_PROJECT < <(resolve_context)

if [[ -z "$PROJECT" && -n "$RESOLVED_PROJECT" ]]; then
    PROJECT="$RESOLVED_PROJECT"
fi

# ── Color mapping ────────────────────────────────────────

trust_to_hex() {
    case "$1" in
        admin)       echo "#00005f" ;;
        trusted)     echo "#005f00" ;;
        semi-trusted) echo "#5f5f00" ;;
        untrusted)   echo "#5f0000" ;;
        disposable)  echo "#5f005f" ;;
        *)           echo "#1a1a1a" ;;
    esac
}

BG_COLOR=$(trust_to_hex "$TRUST_LEVEL")

# ── Build incus exec command ─────────────────────────────

build_exec_cmd() {
    local exec_cmd=("incus" "exec")
    if [[ -n "$PROJECT" ]]; then
        exec_cmd+=("--project" "$PROJECT")
    fi
    exec_cmd+=("$INSTANCE")
    exec_cmd+=("--")
    exec_cmd+=("env"
        "ANKLUME_DOMAIN=$DOMAIN"
        "ANKLUME_TRUST_LEVEL=$TRUST_LEVEL"
        "ANKLUME_INSTANCE=$INSTANCE"
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

    # Try foot (Wayland-native), then alacritty, then xterm
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
