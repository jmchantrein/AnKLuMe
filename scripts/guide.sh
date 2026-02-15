#!/usr/bin/env bash
# guide.sh — Interactive step-by-step onboarding tutorial for AnKLuMe
# Usage: scripts/guide.sh [--step N] [--auto]
#
# Walks the user through setting up AnKLuMe from scratch.
# Each step: explain -> execute -> validate (green/red) -> pause.
#
# Options:
#   --step N   Resume from step N (default: 1)
#   --auto     Non-interactive mode for CI (no prompts, exit on failure)

set -euo pipefail

# ── ANSI Colors ──────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
RESET='\033[0m'

# ── Globals ──────────────────────────────────────────────
START_STEP=1
AUTO=false
TOTAL_STEPS=9
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── Argument parsing ─────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --step)
            START_STEP="$2"
            shift 2
            ;;
        --auto)
            AUTO=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [--step N] [--auto]"
            echo ""
            echo "Options:"
            echo "  --step N   Resume from step N (1-$TOTAL_STEPS)"
            echo "  --auto     Non-interactive CI mode (no prompts)"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--step N] [--auto]"
            exit 1
            ;;
    esac
done

if [[ "$START_STEP" -lt 1 || "$START_STEP" -gt "$TOTAL_STEPS" ]]; then
    echo "Step must be between 1 and $TOTAL_STEPS"
    exit 1
fi

# ── Helper functions ─────────────────────────────────────

header() {
    clear 2>/dev/null || true
    echo -e "${CYAN}${BOLD}"
    echo "  ┌─────────────────────────────────────────┐"
    echo "  │           AnKLuMe Setup Guide            │"
    echo "  │   Infrastructure Compartmentalization    │"
    echo "  └─────────────────────────────────────────┘"
    echo -e "${RESET}"
}

step_header() {
    local num="$1"
    local title="$2"
    echo ""
    echo -e "${BOLD}${BLUE}━━━ Step ${num}/${TOTAL_STEPS}: ${title} ━━━${RESET}"
    echo ""
}

ok() {
    echo -e "  ${GREEN}✓${RESET} $1"
}

fail() {
    echo -e "  ${RED}✗${RESET} $1"
}

warn() {
    echo -e "  ${YELLOW}!${RESET} $1"
}

info() {
    echo -e "  ${DIM}$1${RESET}"
}

pause() {
    if [[ "$AUTO" == "true" ]]; then
        return
    fi
    echo ""
    echo -e "${DIM}  Press Enter to continue (or Ctrl+C to exit)...${RESET}"
    read -r
}

confirm() {
    local prompt="$1"
    if [[ "$AUTO" == "true" ]]; then
        return 0
    fi
    echo ""
    echo -ne "  ${BOLD}${prompt}${RESET} [Y/n] "
    read -r answer
    [[ -z "$answer" || "$answer" =~ ^[Yy] ]]
}

select_option() {
    local prompt="$1"
    shift
    local options=("$@")
    local count=${#options[@]}

    echo -e "  ${BOLD}${prompt}${RESET}"
    echo ""
    for i in "${!options[@]}"; do
        echo -e "    ${CYAN}$((i + 1)))${RESET} ${options[$i]}"
    done
    echo ""

    if [[ "$AUTO" == "true" ]]; then
        echo "  Auto-mode: selecting option 1"
        SELECTED=1
        return
    fi

    while true; do
        echo -ne "  Choice [1-${count}]: "
        read -r choice
        if [[ "$choice" =~ ^[0-9]+$ ]] && [[ "$choice" -ge 1 ]] && [[ "$choice" -le "$count" ]]; then
            SELECTED="$choice"
            return
        fi
        echo -e "  ${RED}Invalid choice. Enter a number between 1 and ${count}.${RESET}"
    done
}

run_cmd() {
    local desc="$1"
    shift
    info "Running: $*"
    if "$@" 2>&1; then
        ok "$desc"
        return 0
    else
        fail "$desc"
        return 1
    fi
}

# ── Step functions ───────────────────────────────────────

step_1_prerequisites() {
    step_header 1 "Prerequisites Check"
    echo "  Checking required tools..."
    echo ""

    local missing=()

    if command -v incus &>/dev/null; then
        ok "incus $(incus version 2>/dev/null || echo '(found)')"
    else
        fail "incus not found"
        missing+=("incus")
    fi

    if command -v ansible-playbook &>/dev/null; then
        ok "ansible $(ansible --version 2>/dev/null | head -1 | awk '{print $NF}' || echo '(found)')"
    else
        fail "ansible not found"
        missing+=("ansible")
    fi

    if command -v python3 &>/dev/null; then
        ok "python3 $(python3 --version 2>/dev/null | awk '{print $2}')"
    else
        fail "python3 not found"
        missing+=("python3")
    fi

    if command -v git &>/dev/null; then
        ok "git $(git --version 2>/dev/null | awk '{print $3}')"
    else
        fail "git not found"
        missing+=("git")
    fi

    if command -v make &>/dev/null; then
        ok "make"
    else
        fail "make not found"
        missing+=("make")
    fi

    # Optional tools
    echo ""
    echo "  Optional tools:"
    for tool in ansible-lint yamllint shellcheck ruff; do
        if command -v "$tool" &>/dev/null; then
            ok "$tool"
        else
            warn "$tool not found (install for linting)"
        fi
    done

    if [[ ${#missing[@]} -gt 0 ]]; then
        echo ""
        fail "Missing required tools: ${missing[*]}"
        echo ""
        echo "  Install them before continuing."
        if [[ "$AUTO" == "true" ]]; then
            exit 1
        fi
        echo "  After installing, resume with: make guide STEP=1"
        exit 1
    fi

    echo ""
    if confirm "Run 'make init' to install Ansible dependencies?"; then
        echo ""
        (cd "$PROJECT_DIR" && make init) || warn "make init had warnings (non-fatal)"
    fi

    ok "All prerequisites satisfied"
    pause
}

step_2_use_case() {
    step_header 2 "Use Case Selection"
    echo "  AnKLuMe ships with example configurations for common use cases."
    echo "  Each example includes a ready-to-use infra.yml."
    echo ""

    select_option "Select your use case:" \
        "Student sysadmin — 2 domains (admin + lab)" \
        "Teacher lab — admin + N student domains" \
        "Pro workstation — admin/work with isolation" \
        "Custom — start from the default template"

    case "$SELECTED" in
        1) USE_CASE="student-sysadmin" ;;
        2) USE_CASE="teacher-lab" ;;
        3) USE_CASE="pro-workstation" ;;
        4) USE_CASE="custom" ;;
    esac

    ok "Selected: $USE_CASE"
    echo ""

    if [[ "$USE_CASE" == "custom" ]]; then
        INFRA_SRC="$PROJECT_DIR/infra.yml.example"
        info "Will use the default template (infra.yml.example)"
    else
        INFRA_SRC="$PROJECT_DIR/examples/${USE_CASE}/infra.yml"
        if [[ ! -f "$INFRA_SRC" ]]; then
            fail "Example not found: $INFRA_SRC"
            INFRA_SRC="$PROJECT_DIR/infra.yml.example"
            warn "Falling back to default template"
        else
            info "Will use: examples/${USE_CASE}/infra.yml"
        fi
    fi

    pause
}

step_3_infra_yml() {
    step_header 3 "Create and Customize infra.yml"

    local dest="$PROJECT_DIR/infra.yml"

    if [[ -f "$dest" ]]; then
        warn "infra.yml already exists"
        echo ""
        if confirm "Overwrite with the selected example?"; then
            cp "$INFRA_SRC" "$dest"
            ok "Replaced infra.yml"
        else
            ok "Keeping existing infra.yml"
        fi
    else
        cp "$INFRA_SRC" "$dest"
        ok "Created infra.yml from ${INFRA_SRC##*/}"
    fi

    echo ""
    echo "  Current infra.yml contents:"
    echo -e "${DIM}"
    sed 's/^/    /' "$dest"
    echo -e "${RESET}"

    echo ""
    warn "Pitfall: Content between '=== MANAGED ===' markers is overwritten"
    info "  by 'make sync'. Add your customizations BELOW the managed section."
    warn "Pitfall: Each machine IP must be globally unique across all domains."

    if [[ "$AUTO" != "true" ]]; then
        if confirm "Open infra.yml in your editor?"; then
            local editor="${EDITOR:-${VISUAL:-vi}}"
            "$editor" "$dest" || warn "Editor exited with error"
            ok "Editor closed"
        fi
    fi

    pause
}

step_4_generate() {
    step_header 4 "Generate Ansible Files"
    echo "  Running the PSOT generator to create inventory, group_vars,"
    echo "  and host_vars from infra.yml."
    echo ""

    echo "  Preview (dry-run):"
    echo ""
    if (cd "$PROJECT_DIR" && python3 scripts/generate.py infra.yml --dry-run 2>&1) | sed 's/^/    /'; then
        ok "Dry-run succeeded"
    else
        fail "Dry-run failed — check infra.yml for errors"
        if [[ "$AUTO" == "true" ]]; then
            exit 1
        fi
        echo "  Fix the errors, then resume with: make guide STEP=4"
        exit 1
    fi

    echo ""
    warn "Pitfall: Follow the workflow: edit -> sync -> lint -> apply."
    info "  Skipping 'make sync' means Ansible files won't match infra.yml."
    echo ""
    if confirm "Apply changes (make sync)?"; then
        echo ""
        if (cd "$PROJECT_DIR" && make sync 2>&1) | sed 's/^/    /'; then
            ok "Ansible files generated"
        else
            fail "make sync failed"
            if [[ "$AUTO" == "true" ]]; then
                exit 1
            fi
            pause
            return
        fi
    fi

    pause
}

step_5_validate() {
    step_header 5 "Validate Configuration"
    echo "  Running linters and syntax checks."
    echo ""

    local has_errors=false

    echo "  YAML lint:"
    if (cd "$PROJECT_DIR" && yamllint -c .yamllint.yml . 2>&1) | sed 's/^/    /'; then
        ok "yamllint passed"
    else
        warn "yamllint found issues (non-blocking)"
    fi

    echo ""
    echo "  Ansible lint:"
    if (cd "$PROJECT_DIR" && ansible-lint 2>&1) | tail -5 | sed 's/^/    /'; then
        ok "ansible-lint passed"
    else
        warn "ansible-lint found issues (non-blocking)"
    fi

    echo ""
    echo "  Syntax check:"
    if (cd "$PROJECT_DIR" && ansible-playbook site.yml --syntax-check 2>&1) | sed 's/^/    /'; then
        ok "Syntax check passed"
    else
        fail "Syntax check failed"
        has_errors=true
    fi

    if [[ "$has_errors" == "true" && "$AUTO" == "true" ]]; then
        exit 1
    fi

    pause
}

step_6_apply() {
    step_header 6 "Apply Infrastructure"
    echo "  This will create Incus networks, projects, profiles, and instances"
    echo "  as defined in infra.yml."
    echo ""
    warn "Requires a running Incus daemon with admin access."
    echo ""

    # Pitfall check: verify inventory exists before apply
    if [[ ! -d "$PROJECT_DIR/inventory" ]] || ! ls "$PROJECT_DIR/inventory"/*.yml >/dev/null 2>&1; then
        warn "Pitfall: No inventory files found. Run 'make sync' first!"
        info "  Without generated files, Ansible has no hosts to configure."
        if [[ "$AUTO" == "true" ]]; then
            exit 1
        fi
        pause
        return
    fi

    warn "Pitfall: After adding a domain, also run 'make nftables &&"
    info "  make nftables-deploy' to ensure network isolation."
    echo ""

    if [[ "$AUTO" == "true" ]]; then
        info "Auto-mode: skipping apply (requires live Incus)"
        pause
        return
    fi

    if ! incus info &>/dev/null 2>&1; then
        warn "Cannot connect to Incus daemon"
        info "Start Incus or run from the admin container."
        info "When ready, resume with: make guide STEP=6"
        pause
        return
    fi

    if confirm "Apply infrastructure now (make apply)?"; then
        echo ""
        if (cd "$PROJECT_DIR" && make apply 2>&1) | sed 's/^/    /'; then
            ok "Infrastructure applied"
        else
            fail "make apply failed — check output above"
        fi
    else
        info "Skipped. Run 'make apply' when ready."
    fi

    pause
}

step_7_verify() {
    step_header 7 "Verify Infrastructure"
    echo "  Checking that instances are running and isolated."
    echo ""

    if ! incus info &>/dev/null 2>&1; then
        warn "Cannot connect to Incus — skipping verification"
        info "Verify manually with: incus list --all-projects"
        pause
        return
    fi

    echo "  Running instances:"
    if incus list --all-projects --format compact 2>&1 | sed 's/^/    /'; then
        ok "Instance listing succeeded"
    else
        warn "Could not list instances"
    fi

    echo ""
    echo "  Networks:"
    if incus network list --format compact 2>/dev/null | grep "net-" | sed 's/^/    /'; then
        ok "AnKLuMe networks found"
    else
        warn "No AnKLuMe networks found (net-* pattern)"
    fi

    pause
}

step_8_snapshot() {
    step_header 8 "Create a Snapshot"
    echo "  Snapshots let you save and restore instance state."
    echo "  This is useful before making changes or running experiments."
    echo ""
    info "Commands:"
    info "  make snapshot              — snapshot all instances"
    info "  make snapshot NAME=fresh   — named snapshot"
    info "  make restore NAME=fresh    — restore from snapshot"
    info "  make snapshot-list         — list all snapshots"
    echo ""

    if [[ "$AUTO" == "true" ]]; then
        info "Auto-mode: skipping snapshot"
        pause
        return
    fi

    if ! incus info &>/dev/null 2>&1; then
        warn "Cannot connect to Incus — skipping snapshot"
        pause
        return
    fi

    if confirm "Create a snapshot of all instances now?"; then
        echo ""
        if (cd "$PROJECT_DIR" && make snapshot NAME=guide-initial 2>&1) | sed 's/^/    /'; then
            ok "Snapshot 'guide-initial' created"
        else
            warn "Snapshot creation had issues"
        fi
    fi

    pause
}

step_9_next_steps() {
    step_header 9 "Next Steps"
    echo "  Your AnKLuMe infrastructure is set up. Here is what to explore next:"
    echo ""
    echo -e "  ${CYAN}Network isolation${RESET}"
    info "  Block traffic between domains with nftables"
    info "  make nftables && make nftables-deploy"
    info "  See: docs/network-isolation.md"
    echo ""
    echo -e "  ${CYAN}GPU & AI services${RESET}"
    info "  Add Ollama, STT, or other AI tools"
    info "  See: docs/gpu-llm.md, docs/stt-service.md"
    echo ""
    echo -e "  ${CYAN}Firewall VM${RESET}"
    info "  Route inter-domain traffic through a firewall VM"
    info "  See: docs/firewall-vm.md"
    echo ""
    echo -e "  ${CYAN}AI-assisted testing${RESET}"
    info "  Let an LLM fix failing tests"
    info "  make ai-test AI_MODE=claude-code"
    info "  See: docs/ai-testing.md"
    echo ""
    echo -e "  ${CYAN}Useful commands${RESET}"
    info "  make help          — list all targets"
    info "  make check         — dry-run changes"
    info "  make apply-limit G=<domain>  — apply one domain"
    info "  make flush         — destroy everything (dev only)"
    echo ""
    echo -e "${GREEN}${BOLD}  Setup complete. Happy compartmentalizing!${RESET}"
    echo ""
}

# ── Main ─────────────────────────────────────────────────

cd "$PROJECT_DIR"
header

if [[ "$START_STEP" -gt 1 ]]; then
    info "Resuming from step $START_STEP"
    echo ""
fi

# Variables shared across steps
USE_CASE=""
INFRA_SRC=""
SELECTED=0

for step in $(seq "$START_STEP" "$TOTAL_STEPS"); do
    case "$step" in
        1) step_1_prerequisites ;;
        2) step_2_use_case ;;
        3) step_3_infra_yml ;;
        4) step_4_generate ;;
        5) step_5_validate ;;
        6) step_6_apply ;;
        7) step_7_verify ;;
        8) step_8_snapshot ;;
        9) step_9_next_steps ;;
    esac
done
