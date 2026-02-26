#!/usr/bin/env bash
# lab-runner.sh — Lab management for anklume educational platform
# Usage: scripts/lab-runner.sh <command> [L=<num>]
#
# Commands:
#   list                List available labs
#   start   L=<num>     Start a lab, display first step
#   check   L=<num>     Run validation for current step
#   hint    L=<num>     Show hint for current step
#   reset   L=<num>     Reset lab progress
#   solution L=<num>    Show solution (marks as assisted)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LABS_DIR="$PROJECT_DIR/labs"
STATE_DIR="${HOME}/.anklume/labs"

# shellcheck source=lab-lib.sh disable=SC1091
source "$SCRIPT_DIR/lab-lib.sh"

# ── Commands ─────────────────────────────────────────────

cmd_list() {
    echo ""
    echo -e "${BOLD}  Available Labs${RESET}"
    echo ""
    printf "  ${DIM}%-6s %-30s %-14s %-8s${RESET}\n" "NUM" "TITLE" "DIFFICULTY" "DURATION"
    printf "  ${DIM}%-6s %-30s %-14s %-8s${RESET}\n" "---" "-----" "----------" "--------"
    for lab_dir in "$LABS_DIR"/[0-9]*/; do
        [[ -d "$lab_dir" ]] || continue
        local lab_yml="$lab_dir/lab.yml"
        [[ -f "$lab_yml" ]] || continue
        local num title difficulty duration
        num=$(basename "$lab_dir" | cut -d- -f1)
        title=$(read_lab_field "$lab_yml" "title")
        difficulty=$(read_lab_field "$lab_yml" "difficulty")
        duration=$(read_lab_field "$lab_yml" "duration")
        printf "  %-6s %-30s %-14s %-8s\n" "$num" "$title" "$difficulty" "$duration"
    done
    echo ""
}

cmd_start() {
    local num="$1" lab_dir lab_id lab_yml title description
    lab_dir=$(find_lab_dir "$num")
    lab_id=$(basename "$lab_dir")
    lab_yml="$lab_dir/lab.yml"
    title=$(read_lab_field "$lab_yml" "title")
    description=$(read_lab_field "$lab_yml" "description")
    ensure_state_dir "$lab_id"
    save_progress "$lab_id" "0" "false"
    echo ""
    echo -e "${BOLD}  Lab $num: $title${RESET}"
    echo ""
    echo -e "  $description"
    echo ""
    local step_title instruction_file
    step_title=$(get_step_field "$lab_yml" "0" "title")
    instruction_file=$(get_step_field "$lab_yml" "0" "instruction_file")
    echo -e "${GREEN}  Step 1: $step_title${RESET}"
    echo ""
    if [[ -n "$instruction_file" && -f "$lab_dir/$instruction_file" ]]; then
        cat "$lab_dir/$instruction_file"
    fi
    echo ""
}

cmd_check() {
    local num="$1" lab_dir lab_id lab_yml current_step total_steps
    lab_dir=$(find_lab_dir "$num")
    lab_id=$(basename "$lab_dir")
    lab_yml="$lab_dir/lab.yml"
    current_step=$(get_current_step "$lab_id")
    total_steps=$(get_step_count "$lab_yml")
    if [[ "$current_step" -ge "$total_steps" ]]; then
        echo -e "${GREEN}Lab already completed.${RESET}"
        return 0
    fi
    local validation
    validation=$(get_step_field "$lab_yml" "$current_step" "validation")
    if [[ -z "$validation" ]]; then
        info "No validation for this step. Advancing."
        _advance_step "$lab_dir" "$lab_id" "$lab_yml" "$current_step" "$total_steps"
        return 0
    fi
    echo -e "${DIM}Running: $validation${RESET}"
    if eval "$validation" 2>/dev/null; then
        echo -e "${GREEN}PASS${RESET} - Step $((current_step + 1)) validated."
        _advance_step "$lab_dir" "$lab_id" "$lab_yml" "$current_step" "$total_steps"
    else
        echo -e "${RED}FAIL${RESET} - Step $((current_step + 1)) not yet complete."
        echo "  Use 'make lab-hint L=$num' for help."
    fi
}

_advance_step() {
    local lab_dir="$1" lab_id="$2" lab_yml="$3" current_step="$4" total_steps="$5"
    local next_step=$((current_step + 1))
    save_progress "$lab_id" "$next_step" "false"
    if [[ "$next_step" -ge "$total_steps" ]]; then
        echo -e "${GREEN}Lab complete!${RESET}"
    else
        local step_title instruction_file
        step_title=$(get_step_field "$lab_yml" "$next_step" "title")
        instruction_file=$(get_step_field "$lab_yml" "$next_step" "instruction_file")
        echo ""
        echo -e "${GREEN}  Next: Step $((next_step + 1)): $step_title${RESET}"
        echo ""
        if [[ -n "$instruction_file" && -f "$lab_dir/$instruction_file" ]]; then
            cat "$lab_dir/$instruction_file"
        fi
    fi
}

cmd_hint() {
    local num="$1" lab_dir lab_id lab_yml current_step hint
    lab_dir=$(find_lab_dir "$num")
    lab_id=$(basename "$lab_dir")
    lab_yml="$lab_dir/lab.yml"
    current_step=$(get_current_step "$lab_id")
    hint=$(get_step_field "$lab_yml" "$current_step" "hint")
    if [[ -n "$hint" ]]; then
        echo -e "${YELLOW}Hint:${RESET} $hint"
    else
        echo "No hint available for this step."
    fi
}

cmd_reset() {
    local num="$1" lab_dir lab_id
    lab_dir=$(find_lab_dir "$num")
    lab_id=$(basename "$lab_dir")
    rm -rf "${STATE_DIR:?}/$lab_id"
    echo -e "${GREEN}Lab $num reset.${RESET} Run 'make lab-start L=$num' to begin again."
}

cmd_solution() {
    local num="$1" lab_dir lab_id solution current_step
    lab_dir=$(find_lab_dir "$num")
    lab_id=$(basename "$lab_dir")
    solution="$lab_dir/solution/commands.sh"
    [[ -f "$solution" ]] || die "No solution file found for lab $num."
    current_step=$(get_current_step "$lab_id")
    save_progress "$lab_id" "$current_step" "true"
    echo -e "${YELLOW}Solution (lab marked as assisted):${RESET}"
    echo ""
    cat "$solution"
    echo ""
}

# ── Main ─────────────────────────────────────────────────

COMMAND="${1:-}"
shift || true
LAB_NUM=""

for arg in "$@"; do
    if [[ "$arg" =~ ^L=(.+)$ ]]; then
        LAB_NUM="${BASH_REMATCH[1]}"
    fi
done

# Also check the L environment variable (from Make)
if [[ -z "$LAB_NUM" && -n "${L:-}" ]]; then
    LAB_NUM="$L"
fi

case "$COMMAND" in
    list)       cmd_list ;;
    start)
        [[ -n "$LAB_NUM" ]] || die "Lab number required. Usage: lab-runner.sh start L=01"
        cmd_start "$LAB_NUM" ;;
    check)
        [[ -n "$LAB_NUM" ]] || die "Lab number required. Usage: lab-runner.sh check L=01"
        cmd_check "$LAB_NUM" ;;
    hint)
        [[ -n "$LAB_NUM" ]] || die "Lab number required. Usage: lab-runner.sh hint L=01"
        cmd_hint "$LAB_NUM" ;;
    reset)
        [[ -n "$LAB_NUM" ]] || die "Lab number required. Usage: lab-runner.sh reset L=01"
        cmd_reset "$LAB_NUM" ;;
    solution)
        [[ -n "$LAB_NUM" ]] || die "Lab number required. Usage: lab-runner.sh solution L=01"
        cmd_solution "$LAB_NUM" ;;
    *)
        echo "Usage: lab-runner.sh <list|start|check|hint|reset|solution> [L=<num>]"
        exit 1 ;;
esac
