#!/usr/bin/env bash
# GPU & AI Services
# Local LLM inference with GPU passthrough.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../guide-lib.sh
source "$SCRIPT_DIR/../guide-lib.sh"

box_header 8 "$GUIDE_TOTAL_CHAPTERS" "GPU & AI Services"

# ── Prerequisites ─────────────────────────────────────────────
check_prerequisite "incus"
check_incus_socket

# Check GPU availability
GPU_INFO=""
if GPU_INFO="$(incus info --resources 2>/dev/null | grep -A5 'GPU:')"; then
    check_ok "GPU detected"
else
    skip_chapter "No GPU detected — chapter informational only"
    GPU_INFO=""
fi

# ── Explain ───────────────────────────────────────────────────
section_title "How it works"
echo "  anklume can pass your GPU to containers for local LLM"
echo "  inference — run Ollama, whisper, or any CUDA workload."
echo ""
echo "  Architecture:"
echo "    ${ARROW} GPU passthrough via Incus device (gpu: true in infra.yml)"
echo "    ${ARROW} ai-tools domain hosts GPU-enabled containers"
echo "    ${ARROW} Exclusive access mode: one domain at a time (VRAM flush)"
echo "    ${ARROW} LLM sanitizer strips infra data from cloud requests"
echo ""
echo "  Security:"
key_value "gpu_policy: exclusive" "one GPU consumer (default)"
key_value "gpu_policy: shared" "multiple (with warning)"
key_value "ai_access_policy: exclusive" "VRAM flush between domains"

# ── Demo ──────────────────────────────────────────────────────
section_title "Live demo"
if [[ -n "$GPU_INFO" ]]; then
    echo "  Detected GPU:"
    echo ""
    run_demo "incus info --resources 2>/dev/null | grep -A10 'GPU:' | head -12"
    echo ""
    echo "  GPU-enabled instances:"
    echo ""
    # List instances with GPU profiles
    incus list --all-projects --format compact -c nsPt 2>/dev/null \
        | grep -i gpu | sed 's/^/    /' || check_info "No GPU instances deployed"
else
    check_info "No GPU available — showing configuration examples"
    echo ""
    echo "  To enable GPU in infra.yml:"
    echo ""
    echo "    machines:"
    echo "      ai-gpu:"
    echo "        type: lxc"
    echo "        gpu: true"
    echo "        roles: [base_system, ollama]"
fi

# ── Try it ────────────────────────────────────────────────────
section_title "Your turn"
echo "  If you have a GPU and ai-tools domain:"
echo ""
check_info "incus exec <gpu-instance> --project ai-tools -- nvidia-smi"
check_info "incus exec <gpu-instance> --project ai-tools -- ollama list"
echo ""
echo "  Configure in infra.yml:"
check_info "gpu: true          # on a machine"
check_info "gpu_policy: shared  # in global: (if multiple consumers)"

# ── Recap ─────────────────────────────────────────────────────
chapter_recap "GPU is shareable for local AI"

# ── Deep dives ────────────────────────────────────────────────
section_title "Deep dives"
echo "  The tour is complete! For more:"
echo ""
key_value "Network isolation" "docs/network-isolation.md"
key_value "GPU & AI" "docs/gpu-advanced.md"
key_value "Educational labs" "anklume lab list"
key_value "Tor gateway" "docs/tor-gateway.md"
echo ""
echo -e "  ${C_GREEN}${C_BOLD}Tour complete! Happy compartmentalizing.${C_RESET}"
echo ""
