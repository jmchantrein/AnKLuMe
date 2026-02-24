#!/usr/bin/env bash
# llm-bench.sh — Benchmark LLM inference backends
#
# Usage:
#   scripts/llm-bench.sh                          # Benchmark active backend, default model
#   scripts/llm-bench.sh --model qwen3:30b-a3b    # Specific model
#   scripts/llm-bench.sh --model all              # All installed models (uses Ollama)
#   scripts/llm-bench.sh --compare                # Compare llama-server vs Ollama
#   scripts/llm-bench.sh --model m1,m2,m3         # Multiple models
#
# Measures tokens/second on a standard code generation prompt.

set -euo pipefail

# Configurable
CONTAINER="${LLM_CONTAINER:-gpu-server}"
PROJECT="${LLM_PROJECT:-ai-tools}"
LLAMA_PORT="${LLAMA_PORT:-8081}"
OLLAMA_PORT="${OLLAMA_PORT:-11434}"
OLLAMA_DATA="/usr/share/ollama/.ollama"

# Benchmark prompt (generates ~150-300 tokens)
BENCH_PROMPT="Write a Python function that implements a binary search tree with insert, search, and inorder traversal methods. Include type hints and docstrings."

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

# ── Helpers ──────────────────────────────────────────────────

_exec() {
    incus exec "$CONTAINER" --project "$PROJECT" -- "$@"
}

die() { printf "${RED}ERROR: %s${NC}\n" "$1" >&2; exit 1; }
info() { printf "${CYAN}%s${NC}\n" "$1"; }
warn() { printf "${YELLOW}%s${NC}\n" "$1"; }

bench_endpoint() {
    # Benchmark a single endpoint+model combination
    # Returns: "tokens duration_ms tok_per_sec"
    local url="$1"
    local model="$2"

    local payload
    payload=$(python3 - "$model" "$BENCH_PROMPT" <<'PYEOF'
import json, sys
print(json.dumps({
    "model": sys.argv[1],
    "messages": [
        {"role": "system", "content": "You are an expert Python programmer. Output only code."},
        {"role": "user", "content": sys.argv[2]},
    ],
    "temperature": 0.1,
    "stream": False,
}))
PYEOF
    )

    # Time the request from the container (closest to the server)
    local result
    result=$(_exec bash -c "
        start_ns=\$(date +%s%N)
        resp=\$(curl -sf -X POST '${url}/v1/chat/completions' \
            -H 'Content-Type: application/json' \
            -d '${payload}' 2>/dev/null)
        end_ns=\$(date +%s%N)
        duration_ms=\$(( (end_ns - start_ns) / 1000000 ))
        # Extract completion tokens from response
        tokens=\$(echo \"\$resp\" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    u = d.get(\"usage\", {})
    print(u.get(\"completion_tokens\", 0))
except: print(0)
')
        echo \"\$tokens \$duration_ms\"
    ") || echo "0 0"

    local tokens duration_ms
    tokens=$(echo "$result" | awk '{print $1}')
    duration_ms=$(echo "$result" | awk '{print $2}')

    # Guard against empty or non-numeric values from failed benchmarks
    if [[ "$tokens" =~ ^[0-9]+$ ]] && [[ "$duration_ms" =~ ^[0-9]+$ ]] \
       && [ "$tokens" -gt 0 ] && [ "$duration_ms" -gt 0 ]; then
        local tok_per_sec
        tok_per_sec=$(python3 -c "print(f'{${tokens} / (${duration_ms} / 1000):.1f}')")
        echo "$tokens $duration_ms $tok_per_sec"
    else
        echo "0 0 0"
    fi
}

detect_active_backend() {
    # Returns: "llama <url>" or "ollama <url>" or "none"
    if _exec curl -sf "http://127.0.0.1:${LLAMA_PORT}/v1/models" >/dev/null 2>&1; then
        echo "llama http://127.0.0.1:${LLAMA_PORT}"
        return
    fi
    if _exec curl -sf "http://127.0.0.1:${OLLAMA_PORT}/v1/models" >/dev/null 2>&1; then
        echo "ollama http://127.0.0.1:${OLLAMA_PORT}"
        return
    fi
    echo "none"
}

list_installed_models() {
    _exec find "${OLLAMA_DATA}/models/manifests/registry.ollama.ai/library" \
        -mindepth 2 -maxdepth 2 -type f 2>/dev/null | sort | while read -r manifest; do
        local name tag
        name=$(basename "$(dirname "$manifest")")
        tag=$(basename "$manifest")
        echo "${name}:${tag}"
    done
}

print_result_row() {
    local backend="$1" model="$2" tokens="$3" duration_ms="$4" tok_s="$5"

    if [ "$tok_s" = "0" ]; then
        printf "  %-12s %-40s %s\n" "$backend" "$model" "${RED}FAILED${NC}"
    else
        local duration_s
        duration_s=$(python3 -c "print(f'{${duration_ms}/1000:.1f}s')")
        printf "  %-12s %-40s %6s tokens  %8s  ${GREEN}%6s tok/s${NC}\n" \
            "$backend" "$model" "$tokens" "$duration_s" "$tok_s"
    fi
}

# ── Commands ──────────────────────────────────────────────────

cmd_bench() {
    local models=("$@")
    local backend_info
    backend_info=$(detect_active_backend)
    local backend_name backend_url
    backend_name=$(echo "$backend_info" | awk '{print $1}')
    backend_url=$(echo "$backend_info" | awk '{print $2}')

    if [ "$backend_name" = "none" ]; then
        die "No LLM backend detected. Start llama-server or Ollama first."
    fi

    # Get GPU info
    local gpu_info
    gpu_info=$(_exec nvidia-smi --query-gpu=name,memory.total,power.limit \
        --format=csv,noheader 2>/dev/null || echo "unknown")

    echo -e "${BOLD}LLM Benchmark${NC}"
    echo -e "  Backend: ${CYAN}${backend_name}${NC} (${backend_url})"
    echo -e "  GPU:     ${gpu_info}"
    echo -e "  Prompt:  ${DIM}${BENCH_PROMPT:0:60}...${NC}"
    echo ""

    echo -e "${BOLD}Results:${NC}"
    printf "  %-12s %-40s %6s  %8s  %12s\n" "BACKEND" "MODEL" "TOKENS" "TIME" "SPEED"
    echo "  $(printf '%.0s─' {1..95})"

    for model in "${models[@]}"; do
        printf "  ${DIM}Benchmarking %-40s${NC}\r" "$model"
        local result
        result=$(bench_endpoint "$backend_url" "$model" || echo "0 0 0")
        local tokens duration_ms tok_s
        tokens=$(echo "$result" | awk '{print $1}')
        duration_ms=$(echo "$result" | awk '{print $2}')
        tok_s=$(echo "$result" | awk '{print $3}')
        print_result_row "$backend_name" "$model" "${tokens:-0}" "${duration_ms:-0}" "${tok_s:-0}"
    done
    echo ""
}

cmd_compare() {
    local model="${1:-}"

    echo -e "${BOLD}LLM Backend Comparison${NC}"
    echo ""

    # Detect what's currently running
    local backend_info
    backend_info=$(detect_active_backend)
    local current_backend
    current_backend=$(echo "$backend_info" | awk '{print $1}')

    if [ -z "$model" ]; then
        if [ "$current_backend" = "llama" ]; then
            model=$(_exec grep -oP '(?<=--alias )\S+' /etc/systemd/system/llama-server.service 2>/dev/null || echo "qwen2.5-coder:32b-instruct-q4_K_M")
        else
            model="qwen2.5-coder:32b-instruct-q4_K_M"
        fi
    fi

    echo -e "  Model: ${CYAN}${model}${NC}"
    echo -e "  Prompt: ${DIM}${BENCH_PROMPT:0:60}...${NC}"
    echo ""

    printf "  %-12s %6s  %8s  %12s\n" "BACKEND" "TOKENS" "TIME" "SPEED"
    echo "  $(printf '%.0s─' {1..50})"

    # Benchmark on llama-server
    info "  Testing llama-server..."
    if [ "$current_backend" != "llama" ]; then
        scripts/llm-switch.sh llama "$model" >/dev/null 2>&1 || true
        sleep 5  # Let model load
    fi
    local result
    result=$(bench_endpoint "http://127.0.0.1:${LLAMA_PORT}" "$model" || echo "0 0 0")
    local llama_tokens llama_ms llama_tps
    llama_tokens=$(echo "$result" | awk '{print $1}')
    llama_ms=$(echo "$result" | awk '{print $2}')
    llama_tps=$(echo "$result" | awk '{print $3}')
    print_result_row "llama" "" "$llama_tokens" "$llama_ms" "${llama_tps:-0}"

    # Benchmark on Ollama
    info "  Testing Ollama..."
    scripts/llm-switch.sh ollama >/dev/null 2>&1 || true
    sleep 3
    # Warm up: first request loads the model
    _exec curl -sf -X POST "http://127.0.0.1:${OLLAMA_PORT}/v1/chat/completions" \
        -H 'Content-Type: application/json' \
        -d "{\"model\":\"${model}\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"stream\":false}" \
        >/dev/null 2>&1 || true
    sleep 2

    result=$(bench_endpoint "http://127.0.0.1:${OLLAMA_PORT}" "$model" || echo "0 0 0")
    local ollama_tokens ollama_ms ollama_tps
    ollama_tokens=$(echo "$result" | awk '{print $1}')
    ollama_ms=$(echo "$result" | awk '{print $2}')
    ollama_tps=$(echo "$result" | awk '{print $3}')
    print_result_row "ollama" "" "$ollama_tokens" "$ollama_ms" "${ollama_tps:-0}"

    echo ""

    # Comparison
    if [[ "${llama_tps:-0}" != "0" ]] && [[ "${ollama_tps:-0}" != "0" ]]; then
        local speedup
        speedup=$(python3 -c "print(f'{float(${llama_tps}) / float(${ollama_tps}):.2f}')" 2>/dev/null || echo "?")
        echo -e "  ${BOLD}llama-server is ${GREEN}${speedup}x${NC}${BOLD} vs Ollama${NC}"
    else
        warn "  One or both backends failed — cannot compare."
    fi

    # Restore original backend
    if [ "$current_backend" = "llama" ]; then
        info "  Restoring llama-server..."
        scripts/llm-switch.sh llama "$model" >/dev/null 2>&1
    fi
    echo ""
}

# ── Main ──────────────────────────────────────────────────────

usage() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  --model MODEL     Model to benchmark (name, comma-separated, or 'all')"
    echo "  --compare         Compare llama-server vs Ollama on same model"
    echo "  -h, --help        Show this help"
    echo ""
    echo "Examples:"
    echo "  $0                                    # Benchmark active backend, current model"
    echo "  $0 --model qwen3:30b-a3b              # Specific model"
    echo "  $0 --model 'qwen2.5-coder:32b-instruct-q4_K_M,qwen3:30b-a3b'  # Multiple"
    echo "  $0 --model all                        # All installed models"
    echo "  $0 --compare                          # Compare backends"
    echo "  $0 --compare --model qwen3:30b-a3b    # Compare on specific model"
}

MODEL=""
COMPARE=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --model)
            MODEL="$2"
            shift 2
            ;;
        --compare)
            COMPARE=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            die "Unknown option: $1"
            ;;
    esac
done

if $COMPARE; then
    cmd_compare "$MODEL"
    exit 0
fi

# Resolve model list
if [ -z "$MODEL" ]; then
    # Use current model of active backend
    backend_info=$(detect_active_backend)
    backend_name=$(echo "$backend_info" | awk '{print $1}')
    if [ "$backend_name" = "llama" ]; then
        MODEL=$(_exec grep -oP '(?<=--alias )\S+' /etc/systemd/system/llama-server.service 2>/dev/null || echo "qwen2.5-coder:32b-instruct-q4_K_M")
    else
        MODEL="qwen2.5-coder:32b-instruct-q4_K_M"
    fi
fi

if [ "$MODEL" = "all" ]; then
    # List all installed models
    mapfile -t model_list < <(list_installed_models)
    if [ ${#model_list[@]} -eq 0 ]; then
        die "No models found"
    fi
    info "Benchmarking all ${#model_list[@]} installed models..."
    echo ""

    # Multi-model requires Ollama (can load/unload dynamically)
    backend_info=$(detect_active_backend)
    current=$(echo "$backend_info" | awk '{print $1}')
    if [ "$current" = "llama" ]; then
        warn "Multi-model benchmark requires Ollama (dynamic model loading)."
        warn "Switching to Ollama temporarily..."
        scripts/llm-switch.sh ollama >/dev/null 2>&1
        sleep 3
    fi

    cmd_bench "${model_list[@]}"

    # Restore llama-server if it was active
    if [ "$current" = "llama" ]; then
        info "Restoring llama-server..."
        scripts/llm-switch.sh llama >/dev/null 2>&1
    fi
else
    # Parse comma-separated models
    IFS=',' read -ra model_list <<< "$MODEL"
    cmd_bench "${model_list[@]}"
fi
