#!/usr/bin/env bash
# guide.sh — Interactive step-by-step onboarding tutorial for anklume
# Usage: scripts/guide.sh [--step N] [--auto]
#
# Walks the user through setting up anklume from scratch.
# Works from the HOST (auto-detects and delegates to anklume-instance)
# or from inside the admin container.
#
# Each step: explain -> execute -> validate (green/red) -> pause.
#
# Options:
#   --step N   Resume from step N (0-10)
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
START_STEP=0
AUTO=false
TOTAL_STEPS=10
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CONTAINER_NAME="anklume-instance"

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
            echo "  --step N   Resume from step N (0-$TOTAL_STEPS)"
            echo "  --auto     Non-interactive CI mode (no prompts)"
            echo ""
            echo "Step 0 detects your environment (host or container)."
            echo "Run from the host or from inside anklume-instance."
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--step N] [--auto]"
            exit 1
            ;;
    esac
done

if [[ "$START_STEP" -lt 0 || "$START_STEP" -gt "$TOTAL_STEPS" ]]; then
    echo "Step must be between 0 and $TOTAL_STEPS"
    exit 1
fi

# ── Helper functions ─────────────────────────────────────

header() {
    clear 2>/dev/null || true
    echo -e "${CYAN}${BOLD}"
    echo "  ┌─────────────────────────────────────────┐"
    echo "  │         anklume Setup Guide              │"
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

# Detect if running on the host (not inside a container/VM)
# Note: systemd-detect-virt returns exit code 1 when NOT virtualized,
# so we must suppress the exit code separately from capturing stdout.
is_on_host() {
    local virt
    virt="$(systemd-detect-virt 2>/dev/null)" || true
    [[ "$virt" == "none" ]]
}

# Check if anklume-instance container exists and is running
# Note: avoid 'incus info | grep -q' — grep -q causes SIGPIPE with pipefail.
container_running() {
    incus list "$CONTAINER_NAME" --format csv -c s 2>/dev/null | grep -q RUNNING
}

# ── Step functions ───────────────────────────────────────

step_0_environment() {
    step_header 0 "Environment Detection"

    echo "  anklume uses an admin container (${CONTAINER_NAME}) as its"
    echo "  control center. All infrastructure management happens from inside it."
    echo ""

    if is_on_host; then
        ok "You are on the host machine"
        echo ""

        # Check if Incus is available
        if ! command -v incus &>/dev/null; then
            fail "Incus not found on host"
            echo ""
            echo "  Run bootstrap.sh first to install Incus and create"
            echo "  the admin container:"
            echo ""
            echo -e "    ${CYAN}bash bootstrap.sh${RESET}"
            echo ""
            if [[ "$AUTO" == "true" ]]; then
                exit 1
            fi
            exit 1
        fi

        # Check if anklume-instance exists
        if ! container_running; then
            fail "${CONTAINER_NAME} is not running"
            echo ""
            echo "  The admin container does not exist or is stopped."
            echo "  Run bootstrap.sh to create it:"
            echo ""
            echo -e "    ${CYAN}bash bootstrap.sh${RESET}"
            echo ""
            echo "  Or start it if it already exists:"
            echo ""
            echo -e "    ${CYAN}incus start ${CONTAINER_NAME}${RESET}"
            echo ""
            if [[ "$AUTO" == "true" ]]; then
                exit 1
            fi
            exit 1
        fi

        ok "${CONTAINER_NAME} is running"
        echo ""

        # Offer to delegate to the container
        echo "  The guide will now continue inside ${CONTAINER_NAME}."
        echo "  This is where all anklume commands run."
        echo ""

        if [[ "$AUTO" == "true" ]]; then
            info "Auto-mode: delegating to container"
            local step_arg=""
            if [[ "$START_STEP" -gt 0 ]]; then
                step_arg="--step $((START_STEP))"
            else
                step_arg="--step 1"
            fi
            # shellcheck disable=SC2086
            exec incus exec "$CONTAINER_NAME" -- bash -c \
                "cd /root/anklume && bash scripts/guide.sh --auto $step_arg"
        fi

        echo -e "  ${BOLD}How to enter the admin container manually:${RESET}"
        echo ""
        echo -e "    ${CYAN}incus exec ${CONTAINER_NAME} -- bash${RESET}"
        echo -e "    ${CYAN}cd /root/anklume${RESET}"
        echo ""

        if confirm "Continue the guide inside ${CONTAINER_NAME}?"; then
            local step_arg="--step 1"
            exec incus exec "$CONTAINER_NAME" -- bash -c \
                "cd /root/anklume && bash scripts/guide.sh $step_arg"
        else
            echo ""
            info "To resume later from inside the container:"
            echo -e "    ${CYAN}incus exec ${CONTAINER_NAME} -- bash${RESET}"
            echo -e "    ${CYAN}cd /root/anklume && make guide${RESET}"
            exit 0
        fi
    else
        ok "You are inside a container"
        echo ""

        if [[ "$(hostname 2>/dev/null)" == "$CONTAINER_NAME" ]] || \
           [[ -d /root/anklume ]]; then
            ok "This looks like the admin container — good!"
        else
            warn "This does not look like ${CONTAINER_NAME}"
            info "The guide expects to run from inside the admin container."
            info "Run: incus exec ${CONTAINER_NAME} -- bash"
        fi

        # Check Incus socket access
        if incus info &>/dev/null 2>&1; then
            ok "Incus socket accessible"
        else
            fail "Cannot access Incus socket"
            echo ""
            echo "  The admin container needs the Incus socket mounted."
            echo "  This is normally set up by bootstrap.sh."
            if [[ "$AUTO" == "true" ]]; then
                exit 1
            fi
        fi
        pause
    fi
}

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
        info "Installing dependencies (output in /tmp/anklume-init.log)..."
        if (cd "$PROJECT_DIR" && make init > /tmp/anklume-init.log 2>&1); then
            ok "Dependencies installed"
        else
            warn "make init had warnings (see /tmp/anklume-init.log)"
        fi
    fi

    ok "All prerequisites satisfied"
    pause
}

step_2_use_case() {
    step_header 2 "Use Case Selection"
    echo "  anklume ships with example configurations for common use cases."
    echo "  Each example includes a ready-to-use infra.yml."
    echo ""

    select_option "Select your use case:" \
        "Student sysadmin — 2 domains (anklume + lab)" \
        "Teacher lab — anklume + N student domains" \
        "Pro workstation — anklume/work with isolation" \
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
        # Check if infra is already deployed (inventory files exist)
        local deployed=false
        if [[ -d "$PROJECT_DIR/inventory" ]] && ls "$PROJECT_DIR/inventory"/*.yml >/dev/null 2>&1; then
            deployed=true
        fi

        if [[ "$deployed" == "true" ]]; then
            warn "infra.yml already exists AND inventory files are present"
            warn "An infrastructure appears to be deployed from this file."
            echo ""
            info "Current project: $(grep 'project_name:' "$dest" 2>/dev/null | awk '{print $2}' || echo 'unknown')"
            echo ""

            if [[ "$AUTO" == "true" ]]; then
                ok "Keeping existing infra.yml (deployed infrastructure detected)"
                INFRA_SRC=""
            elif confirm "Keep existing infra.yml (recommended)?"; then
                ok "Keeping existing infra.yml"
                INFRA_SRC=""
            else
                warn "Overwriting will disconnect from the deployed infrastructure!"
                if confirm "Are you sure? A backup will be saved as infra.yml.bak"; then
                    cp "$dest" "${dest}.bak"
                    ok "Backup saved: infra.yml.bak"
                    cp "$INFRA_SRC" "$dest"
                    ok "Replaced infra.yml"
                else
                    ok "Keeping existing infra.yml"
                    INFRA_SRC=""
                fi
            fi
        else
            warn "infra.yml already exists (no deployed infrastructure detected)"
            echo ""
            if confirm "Overwrite with the selected example?"; then
                cp "$dest" "${dest}.bak"
                ok "Backup saved: infra.yml.bak"
                cp "$INFRA_SRC" "$dest"
                ok "Replaced infra.yml"
            else
                ok "Keeping existing infra.yml"
            fi
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
        if [[ "$AUTO" == "true" ]]; then
            exit 1
        fi
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
        ok "anklume networks found"
    else
        warn "No anklume networks found (net-* pattern)"
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

step_9_access() {
    step_header 9 "Access Your Infrastructure"
    echo "  Your containers are running. Here is how to access them."
    echo ""

    echo -e "  ${BOLD}Enter any container from the admin container:${RESET}"
    echo ""
    info "  incus exec <machine-name> --project <domain> -- bash"
    echo ""

    # Show available instances
    if incus info &>/dev/null 2>&1; then
        echo "  Your instances:"
        echo ""
        incus list --all-projects --format json 2>/dev/null | \
            python3 -c "
import json, sys
data = json.load(sys.stdin)
for i in sorted(data, key=lambda x: x.get('project','')):
    if i['status'] != 'Running': continue
    p = i.get('project','')
    n = i['name']
    if n == '$(hostname 2>/dev/null)': continue
    print(f'    incus exec {n} --project {p} -- bash')
" 2>/dev/null || true
        echo ""
    fi

    echo -e "  ${BOLD}Or use the tmux console (colored by domain):${RESET}"
    echo ""
    info "  make console"
    info "  (requires: pip install libtmux)"
    echo ""

    echo -e "  ${BOLD}From the host (without entering the admin container):${RESET}"
    echo ""
    info "  incus exec <machine-name> --project <domain> -- bash"
    info "  (works because Incus runs on the host)"

    pause
}

step_10_next_steps() {
    step_header 10 "Next Steps"
    echo "  Your anklume infrastructure is set up. Here is what to explore next:"
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

if [[ "$START_STEP" -gt 0 ]]; then
    info "Resuming from step $START_STEP"
    echo ""
fi

# Variables shared across steps
USE_CASE=""
INFRA_SRC=""
SELECTED=0

for step in $(seq "$START_STEP" "$TOTAL_STEPS"); do
    case "$step" in
        0)  step_0_environment ;;
        1)  step_1_prerequisites ;;
        2)  step_2_use_case ;;
        3)  step_3_infra_yml ;;
        4)  step_4_generate ;;
        5)  step_5_validate ;;
        6)  step_6_apply ;;
        7)  step_7_verify ;;
        8)  step_8_snapshot ;;
        9)  step_9_access ;;
        10) step_10_next_steps ;;
    esac
done
