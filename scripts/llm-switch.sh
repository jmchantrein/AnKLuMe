#!/usr/bin/env bash
# llm-switch.sh — Switch between llama-server and Ollama backends
#
# Usage:
#   scripts/llm-switch.sh llama [MODEL]   # Switch to llama-server (default: current model)
#   scripts/llm-switch.sh ollama          # Switch to Ollama
#   scripts/llm-switch.sh status          # Show active backend, model, VRAM
#
# Runs from anklume-instance or the host. Executes service commands
# in the ollama container via incus exec.

set -euo pipefail

# Configurable
CONTAINER="${LLM_CONTAINER:-ollama}"
PROJECT="${LLM_PROJECT:-ai-tools}"
LLAMA_PORT="${LLAMA_PORT:-8081}"
OLLAMA_PORT="${OLLAMA_PORT:-11434}"
DEFAULT_MODEL="qwen2.5-coder:32b-instruct-q4_K_M"
OLLAMA_DATA="/usr/share/ollama/.ollama"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# ── Helpers ──────────────────────────────────────────────────

_exec() {
    incus exec "$CONTAINER" --project "$PROJECT" -- "$@"
}

_exec_quiet() {
    incus exec "$CONTAINER" --project "$PROJECT" -- "$@" 2>/dev/null || true
}

die() { echo -e "${RED}ERROR: $1${NC}" >&2; exit 1; }
info() { echo -e "${CYAN}$1${NC}"; }
ok() { echo -e "${GREEN}$1${NC}"; }
warn() { echo -e "${YELLOW}$1${NC}"; }

resolve_model_blob() {
    # Resolve Ollama model name to GGUF blob path inside the container
    local model="$1"
    local name="${model%%:*}"
    local tag="${model#*:}"
    [ "$tag" = "$model" ] && tag="latest"

    local manifest_path="${OLLAMA_DATA}/models/manifests/registry.ollama.ai/library/${name}/${tag}"

    _exec python3 - "$manifest_path" <<'PYEOF'
import json, sys
try:
    with open(sys.argv[1]) as f:
        data = json.load(f)
    for layer in data.get("layers", []):
        if "model" in layer.get("mediaType", ""):
            digest = layer["digest"].replace(":", "-")
            print(f"/usr/share/ollama/.ollama/models/blobs/{digest}")
            sys.exit(0)
    print("ERROR: no model layer found in manifest", file=sys.stderr)
    sys.exit(1)
except FileNotFoundError:
    print(f"ERROR: manifest not found: {sys.argv[1]}", file=sys.stderr)
    sys.exit(1)
PYEOF
}

get_current_llama_model() {
    # Extract model alias from llama-server service file
    _exec_quiet grep -oP '(?<=--alias )\S+' /etc/systemd/system/llama-server.service || echo "unknown"
}

write_llama_service() {
    local blob_path="$1"
    local model_alias="$2"

    _exec bash -c "cat > /etc/systemd/system/llama-server.service" <<EOF
[Unit]
Description=llama.cpp inference server (GPU) — ${model_alias}
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/llama-server \\
    -m ${blob_path} \\
    --alias ${model_alias} \\
    --host 0.0.0.0 \\
    --port ${LLAMA_PORT} \\
    -ngl 999 \\
    -c 8192 \\
    --flash-attn on \\
    --parallel 2 \\
    --cache-type-k q8_0 \\
    --cache-type-v q8_0
Environment="PATH=/usr/local/cuda-13.1/bin:/usr/local/bin:/usr/bin:/bin"
Environment="LD_LIBRARY_PATH=/usr/local/cuda-13.1/lib64"
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
    _exec systemctl daemon-reload
}

wait_for_service() {
    local url="$1"
    local max_wait="${2:-60}"
    local elapsed=0

    while [ "$elapsed" -lt "$max_wait" ]; do
        if _exec curl -sf "$url" >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
        elapsed=$((elapsed + 2))
        printf "."
    done
    echo ""
    return 1
}

# ── Commands ──────────────────────────────────────────────────

cmd_status() {
    echo -e "${BOLD}LLM Backend Status${NC}"
    echo ""

    # Check services
    local ollama_active llama_active stt_active
    ollama_active=$(_exec_quiet systemctl is-active ollama)
    llama_active=$(_exec_quiet systemctl is-active llama-server)
    stt_active=$(_exec_quiet systemctl is-active speaches)

    local ollama_enabled llama_enabled
    ollama_enabled=$(_exec_quiet systemctl is-enabled ollama)
    llama_enabled=$(_exec_quiet systemctl is-enabled llama-server)

    echo "Services:"
    if [ "$llama_active" = "active" ]; then
        local model
        model=$(get_current_llama_model)
        echo -e "  llama-server:  ${GREEN}active${NC} (enabled: ${llama_enabled}) — model: ${CYAN}${model}${NC}"
    else
        echo -e "  llama-server:  ${RED}inactive${NC} (enabled: ${llama_enabled})"
    fi

    if [ "$ollama_active" = "active" ]; then
        echo -e "  ollama:        ${GREEN}active${NC} (enabled: ${ollama_enabled})"
    else
        echo -e "  ollama:        ${RED}inactive${NC} (enabled: ${ollama_enabled})"
    fi

    if [ "$stt_active" = "active" ]; then
        echo -e "  speaches:      ${GREEN}active${NC} (STT)"
    else
        echo -e "  speaches:      ${RED}inactive${NC} (STT)"
    fi

    # VRAM
    echo ""
    echo "GPU VRAM:"
    _exec nvidia-smi --query-gpu=memory.used,memory.total,power.draw,power.limit \
        --format=csv,noheader,nounits 2>/dev/null | while IFS=', ' read -r used total power plimit; do
        echo -e "  Used: ${CYAN}${used} MiB${NC} / ${total} MiB  |  Power: ${CYAN}${power}W${NC} / ${plimit}W"
    done

    # Installed models
    echo ""
    echo "Installed models (Ollama registry):"
    _exec_quiet find "${OLLAMA_DATA}/models/manifests/registry.ollama.ai/library" \
        -mindepth 2 -maxdepth 2 -type f | sort | while read -r manifest; do
        local name tag
        name=$(basename "$(dirname "$manifest")")
        tag=$(basename "$manifest")
        echo "  ${name}:${tag}"
    done
}

cmd_llama() {
    local model="${1:-$DEFAULT_MODEL}"

    info "Switching to llama-server with model: ${model}"

    # Resolve model blob
    info "Resolving model blob..."
    local blob_path
    blob_path=$(resolve_model_blob "$model") || die "Model not found: $model"
    ok "  Blob: $blob_path"

    # Stop Ollama first to free VRAM
    info "Stopping Ollama..."
    _exec systemctl stop ollama 2>/dev/null || true
    sleep 1

    # Stop current llama-server if running
    _exec systemctl stop llama-server 2>/dev/null || true
    sleep 1

    # Write updated service file
    info "Updating llama-server service..."
    write_llama_service "$blob_path" "$model"

    # Enable llama-server, disable Ollama
    _exec systemctl enable llama-server 2>/dev/null
    _exec systemctl disable ollama 2>/dev/null

    # Start llama-server
    info "Starting llama-server..."
    _exec systemctl start llama-server

    # Wait for it to be ready
    printf "  Waiting for server"
    if wait_for_service "http://127.0.0.1:${LLAMA_PORT}/v1/models" 90; then
        echo ""
        ok "llama-server ready on port ${LLAMA_PORT}"
    else
        warn "Timeout waiting for llama-server (it may still be loading the model)"
        warn "Check: incus exec $CONTAINER --project $PROJECT -- journalctl -u llama-server -f"
    fi

    # Verify STT
    local stt_status
    stt_status=$(_exec_quiet systemctl is-active speaches)
    if [ "$stt_status" = "active" ]; then
        ok "STT (speaches) still running"
    else
        warn "STT (speaches) not running — restarting..."
        _exec systemctl start speaches
    fi

    echo ""
    ok "Active backend: llama-server (port ${LLAMA_PORT})"
    ok "Model: ${model}"
}

cmd_ollama() {
    info "Switching to Ollama"

    # Stop llama-server first to free VRAM
    info "Stopping llama-server..."
    _exec systemctl stop llama-server 2>/dev/null || true
    sleep 1

    # Disable llama-server, enable Ollama
    _exec systemctl disable llama-server 2>/dev/null
    _exec systemctl enable ollama 2>/dev/null

    # Start Ollama
    info "Starting Ollama..."
    _exec systemctl start ollama

    # Wait for it
    printf "  Waiting for server"
    if wait_for_service "http://127.0.0.1:${OLLAMA_PORT}/v1/models" 30; then
        echo ""
        ok "Ollama ready on port ${OLLAMA_PORT}"
    else
        warn "Timeout waiting for Ollama"
    fi

    # Verify STT
    local stt_status
    stt_status=$(_exec_quiet systemctl is-active speaches)
    if [ "$stt_status" = "active" ]; then
        ok "STT (speaches) still running"
    else
        warn "STT (speaches) not running — restarting..."
        _exec systemctl start speaches
    fi

    echo ""
    ok "Active backend: Ollama (port ${OLLAMA_PORT})"
}

# ── Main ──────────────────────────────────────────────────────

usage() {
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Commands:"
    echo "  llama [MODEL]   Switch to llama-server (default: ${DEFAULT_MODEL})"
    echo "  ollama          Switch to Ollama"
    echo "  status          Show active backend and VRAM usage"
    echo ""
    echo "Examples:"
    echo "  $0 llama                              # Use default model"
    echo "  $0 llama qwen3:30b-a3b                # Switch model"
    echo "  $0 llama glm-4.7-flash:latest         # Another model"
    echo "  $0 ollama                             # Switch to Ollama"
    echo "  $0 status                             # Check status"
}

case "${1:-}" in
    llama)
        cmd_llama "${2:-}"
        ;;
    ollama)
        cmd_ollama
        ;;
    status)
        cmd_status
        ;;
    -h|--help|"")
        usage
        ;;
    *)
        die "Unknown command: $1"
        ;;
esac
