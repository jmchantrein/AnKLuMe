#!/usr/bin/env bash
# guide-setup.sh — Initial setup wizard (extracted from original guide.sh)
# Usage: scripts/guide-setup.sh [--step N] [--auto]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=guide-lib.sh
source "$SCRIPT_DIR/guide-lib.sh"

START_STEP=0
TOTAL_STEPS=8

while [[ $# -gt 0 ]]; do
    case "$1" in
        --step)  START_STEP="$2"; shift 2 ;;
        --auto)  export GUIDE_AUTO=true; shift ;;
        *)       shift ;;
    esac
done

[[ "$START_STEP" -ge 0 && "$START_STEP" -le "$TOTAL_STEPS" ]] || {
    echo "Step must be between 0 and $TOTAL_STEPS"; exit 1
}

step_header() {
    echo ""
    echo -e "${C_BOLD}${C_BLUE}━━━ Step ${1}/${TOTAL_STEPS}: ${2} ━━━${C_RESET}"
    echo ""
}

# ── Step 0: Environment Detection ────────────────────────────
step_0() {
    step_header 0 "Environment Detection"
    if command -v systemd-detect-virt &>/dev/null; then
        local virt
        virt="$(systemd-detect-virt 2>/dev/null)" || true
        if [[ "$virt" == "none" ]]; then
            check_ok "Running on host"
            if incus list anklume-instance --format csv -c s 2>/dev/null | grep -q RUNNING; then
                check_ok "anklume-instance is running"
                if guide_confirm "Continue inside anklume-instance?"; then
                    local args="--step 1"
                    [[ "$GUIDE_AUTO" == "true" ]] && args="$args --auto"
                    exec incus exec anklume-instance -- bash -c \
                        "cd /root/anklume && bash scripts/guide-setup.sh $args"
                fi
            else
                check_warn "anklume-instance not running"
                check_info "Start it: incus start anklume-instance"
            fi
        else
            check_ok "Running inside container ($virt)"
        fi
    fi
    check_prerequisite "incus"
    check_incus_socket
    guide_pause
}

# ── Step 1: Prerequisites ────────────────────────────────────
step_1() {
    step_header 1 "Prerequisites"
    for tool in incus ansible-playbook python3 git make; do
        check_prerequisite "$tool"
    done
    echo ""
    check_info "Optional: ansible-lint yamllint shellcheck ruff"
    for tool in ansible-lint yamllint shellcheck ruff; do
        if command -v "$tool" &>/dev/null; then
            check_ok "$tool"
        else
            check_warn "$tool (install for linting)"
        fi
    done
    guide_pause
}

# ── Step 2: Use Case Selection ────────────────────────────────
step_2() {
    step_header 2 "Use Case Selection"
    echo "  Select a pre-built example:"
    echo ""
    echo -e "    ${C_CYAN}1)${C_RESET} Student sysadmin"
    echo -e "    ${C_CYAN}2)${C_RESET} Teacher lab"
    echo -e "    ${C_CYAN}3)${C_RESET} Pro workstation"
    echo -e "    ${C_CYAN}4)${C_RESET} Custom (default template)"
    echo ""
    if [[ "$GUIDE_AUTO" == "true" ]]; then
        USE_CASE="custom"
    else
        echo -ne "  ${C_BOLD}Choice [1-4]:${C_RESET} "
        read -r choice
        case "${choice:-4}" in
            1) USE_CASE="student-sysadmin" ;;
            2) USE_CASE="teacher-lab" ;;
            3) USE_CASE="pro-workstation" ;;
            *) USE_CASE="custom" ;;
        esac
    fi
    check_ok "Selected: $USE_CASE"
    guide_pause
}

# ── Step 3: Create infra.yml ──────────────────────────────────
step_3() {
    step_header 3 "Create infra.yml"
    local dest="$GUIDE_PROJECT_DIR/infra.yml"
    if [[ -f "$dest" ]]; then
        check_ok "infra.yml already exists"
        check_info "Keeping existing file"
    else
        local src="$GUIDE_PROJECT_DIR/infra.yml.example"
        if [[ "$USE_CASE" != "custom" ]]; then
            local ex="$GUIDE_PROJECT_DIR/examples/${USE_CASE}/infra.yml"
            [[ -f "$ex" ]] && src="$ex"
        fi
        cp "$src" "$dest"
        check_ok "Created infra.yml from ${src##*/}"
    fi
    check_warn "Content between '=== MANAGED ===' markers is overwritten by sync"
    guide_pause
}

# ── Step 4: Generate Ansible Files ────────────────────────────
step_4() {
    step_header 4 "Generate Ansible Files (sync)"
    run_demo "python3 scripts/generate.py infra.yml --dry-run"
    if guide_confirm "Apply changes (anklume sync)?"; then
        run_demo "cd $GUIDE_PROJECT_DIR && make sync"
    fi
    guide_pause
}

# ── Step 5: Validate ──────────────────────────────────────────
step_5() {
    step_header 5 "Validate Configuration"
    if command -v ansible-playbook &>/dev/null; then
        run_demo "ansible-playbook site.yml --syntax-check"
    fi
    guide_pause
}

# ── Step 6: Apply Infrastructure ──────────────────────────────
step_6() {
    step_header 6 "Apply Infrastructure"
    if [[ "$GUIDE_AUTO" == "true" ]]; then
        check_info "Auto-mode: skipping apply"
        return
    fi
    if guide_confirm "Apply infrastructure now (anklume domain apply)?"; then
        run_demo "cd $GUIDE_PROJECT_DIR && make apply"
    fi
    guide_pause
}

# ── Step 7: Verify & Snapshot ─────────────────────────────────
step_7() {
    step_header 7 "Verify & Snapshot"
    run_demo "incus list --all-projects --format compact"
    echo ""
    if guide_confirm "Create initial snapshot?"; then
        run_demo "cd $GUIDE_PROJECT_DIR && make snapshot NAME=guide-initial"
    fi
    guide_pause
}

# ── Step 8: Next Steps ────────────────────────────────────────
step_8() {
    step_header 8 "Setup Complete"
    echo ""
    key_value "Capability tour" "scripts/guide.sh"
    key_value "Console" "anklume console"
    key_value "Dashboard" "anklume dashboard"
    key_value "Network isolation" "docs/network-isolation.md"
    key_value "GPU & AI" "docs/gpu-advanced.md"
    key_value "Labs" "anklume lab list"
    echo ""
    echo -e "  ${C_GREEN}${C_BOLD}Setup complete. Run the capability tour next!${C_RESET}"
    echo ""
}

# ── Main ──────────────────────────────────────────────────────
USE_CASE="custom"

for step in $(seq "$START_STEP" "$TOTAL_STEPS"); do
    case "$step" in
        0) step_0 ;; 1) step_1 ;; 2) step_2 ;; 3) step_3 ;;
        4) step_4 ;; 5) step_5 ;; 6) step_6 ;; 7) step_7 ;;
        8) step_8 ;;
    esac
done
