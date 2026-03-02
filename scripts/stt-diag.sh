#!/usr/bin/env bash
# stt-diag.sh — Diagnose and manage STT (Speaches/Whisper) service
# Usage: stt-diag.sh {status|restart|logs|test} [OPTIONS]
set -euo pipefail

STT_CONTAINER="gpu-server"
STT_PROJECT="ai-tools"
STT_PORT=8000
STT_HOST="${STT_HOST:-10.100.3.1}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
DIM='\033[0;90m'
RESET='\033[0m'

ok()   { printf "${GREEN}[OK]${RESET} %s\n" "$*"; }
warn() { printf "${YELLOW}[WARN]${RESET} %s\n" "$*"; }
err()  { printf "${RED}[ERR]${RESET} %s\n" "$*"; }
dim()  { printf "${DIM}%s${RESET}\n" "$*"; }

# ── Check container is running ───────────────────────────────
check_container() {
    if ! incus list "$STT_CONTAINER" --project "$STT_PROJECT" --format csv -c s 2>/dev/null | grep -q "RUNNING"; then
        err "Container $STT_CONTAINER is not running (project: $STT_PROJECT)"
        return 1
    fi
    ok "Container $STT_CONTAINER is running"
}

# ── Check systemd service ────────────────────────────────────
check_service() {
    local state
    state=$(incus exec "$STT_CONTAINER" --project "$STT_PROJECT" -- \
        systemctl is-active speaches 2>/dev/null) || state="unknown"
    if [ "$state" = "active" ]; then
        ok "Service speaches is active"
    else
        err "Service speaches is $state"
        return 1
    fi
}

# ── Check HTTP health endpoint ───────────────────────────────
check_health() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" \
        "http://${STT_HOST}:${STT_PORT}/health" 2>/dev/null) || code="000"
    if [ "$code" = "200" ]; then
        ok "Health endpoint: HTTP $code"
    else
        err "Health endpoint: HTTP $code"
        return 1
    fi
}

# ── Check VRAM usage ─────────────────────────────────────────
check_vram() {
    local vram_info
    vram_info=$(incus exec "$STT_CONTAINER" --project "$STT_PROJECT" -- \
        nvidia-smi --query-gpu=memory.used,memory.total,temperature.gpu,utilization.gpu \
        --format=csv,noheader,nounits 2>/dev/null) || true
    if [ -z "$vram_info" ]; then
        warn "Could not query GPU (nvidia-smi unavailable)"
        return 0
    fi
    local used total temp util
    used=$(echo "$vram_info" | cut -d',' -f1 | tr -d ' ')
    total=$(echo "$vram_info" | cut -d',' -f2 | tr -d ' ')
    temp=$(echo "$vram_info" | cut -d',' -f3 | tr -d ' ')
    util=$(echo "$vram_info" | cut -d',' -f4 | tr -d ' ')
    local pct=0
    if [ "$total" -gt 0 ] 2>/dev/null; then
        pct=$((used * 100 / total))
    fi
    if [ "$pct" -ge 95 ]; then
        err "VRAM: ${used}/${total} MiB (${pct}%) — CRITICAL"
    elif [ "$pct" -ge 80 ]; then
        warn "VRAM: ${used}/${total} MiB (${pct}%)"
    else
        ok "VRAM: ${used}/${total} MiB (${pct}%)"
    fi
    dim "  GPU temp: ${temp}°C, utilization: ${util}%"
}

# ── Check loaded Ollama models ───────────────────────────────
check_ollama() {
    local models
    models=$(curl -s "http://${STT_HOST}:11434/api/ps" 2>/dev/null) || true
    if [ -z "$models" ]; then
        dim "  Ollama API not reachable"
        return 0
    fi
    local count
    count=$(echo "$models" | python3 -c "
import sys, json
data = json.load(sys.stdin)
models = data.get('models', [])
print(len(models))
for m in models:
    vram = m.get('size_vram', 0)
    total = m.get('size', 0)
    pct = int(vram * 100 / total) if total > 0 else 0
    print(f\"  {m['name']}: {vram // (1024**3):.0f} GiB VRAM ({pct}% GPU)\")
" 2>/dev/null) || count="0"
    local num_models
    num_models=$(echo "$count" | head -1)
    if [ "$num_models" -gt 0 ] 2>/dev/null; then
        warn "Ollama has $num_models model(s) loaded (consuming VRAM):"
        echo "$count" | tail -n +2
    else
        ok "No Ollama models loaded (VRAM free for STT)"
    fi
}

# ── Commands ─────────────────────────────────────────────────

cmd_status() {
    echo "=== STT Service Diagnostics ==="
    echo ""
    check_container || true
    check_service || true
    check_health || true
    echo ""
    echo "--- GPU / VRAM ---"
    check_vram
    check_ollama
}

cmd_restart() {
    echo "=== Restarting STT Service ==="
    echo ""

    # Unload all Ollama models to free VRAM
    echo "--- Unloading Ollama models ---"
    local models
    models=$(curl -s "http://${STT_HOST}:11434/api/ps" 2>/dev/null) || true
    if [ -n "$models" ]; then
        echo "$models" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for m in data.get('models', []):
    print(m['name'])
" 2>/dev/null | while read -r model; do
            dim "  Unloading $model..."
            curl -s "http://${STT_HOST}:11434/api/generate" \
                -d "{\"model\":\"$model\",\"keep_alive\":0}" >/dev/null 2>&1 || true
        done
    fi
    ok "Ollama models unloaded"

    # Restart speaches service
    echo ""
    echo "--- Restarting speaches ---"
    incus exec "$STT_CONTAINER" --project "$STT_PROJECT" -- \
        systemctl restart speaches 2>/dev/null || err "Failed to restart speaches"

    # Wait for health
    echo "Waiting for health endpoint..."
    local retries=0
    while [ $retries -lt 30 ]; do
        if curl -s -o /dev/null -w "" "http://${STT_HOST}:${STT_PORT}/health" 2>/dev/null; then
            ok "STT service is healthy"
            break
        fi
        sleep 1
        retries=$((retries + 1))
    done
    if [ $retries -ge 30 ]; then
        err "STT did not become healthy after 30s"
    fi

    echo ""
    cmd_status
}

cmd_logs() {
    local lines="${1:-50}"
    incus exec "$STT_CONTAINER" --project "$STT_PROJECT" -- \
        journalctl -u speaches -n "$lines" --no-pager
}

cmd_test() {
    echo "=== STT Health Check ==="
    check_health || true

    # Test model list endpoint
    local resp
    resp=$(curl -s "http://${STT_HOST}:${STT_PORT}/v1/models" 2>/dev/null) || true
    if [ -n "$resp" ]; then
        ok "Models endpoint responsive"
        echo "$resp" | python3 -c "
import sys, json
data = json.load(sys.stdin)
models = data.get('data', [])
for m in models:
    print(f\"  {m.get('id', 'unknown')}\")
" 2>/dev/null || dim "  (could not parse models response)"
    else
        err "Models endpoint not reachable"
    fi
}

# ── Main ─────────────────────────────────────────────────────

case "${1:-status}" in
    status)  cmd_status ;;
    restart) cmd_restart ;;
    logs)    cmd_logs "${2:-50}" ;;
    test)    cmd_test ;;
    *)
        echo "Usage: $0 {status|restart|logs|test}"
        exit 1
        ;;
esac
