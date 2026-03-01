#!/usr/bin/env bash
# guide.sh — Interactive capability tour dispatcher for anklume
# Usage: scripts/guide.sh [--chapter N] [--setup] [--auto] [--lang fr|en]
#        scripts/guide.sh [--step N] [--auto]  (legacy, delegates to --setup)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=guide-lib.sh
source "$SCRIPT_DIR/guide-lib.sh"

# ── Argument parsing ─────────────────────────────────────────
CHAPTER=""
SETUP=false
LEGACY_STEP=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --chapter)  CHAPTER="$2"; shift 2 ;;
        --setup)    SETUP=true; shift ;;
        --auto)     export GUIDE_AUTO=true; shift ;;
        --lang)     export GUIDE_LANG="$2"; shift 2 ;;
        --step)     LEGACY_STEP="$2"; SETUP=true; shift 2 ;;
        --help|-h)
            echo "Usage: $0 [--chapter N] [--setup] [--auto] [--lang fr|en]"
            echo ""
            echo "  --chapter N   Run chapter N (1-${GUIDE_TOTAL_CHAPTERS})"
            echo "  --setup       Run initial setup wizard"
            echo "  --auto        Non-interactive mode (no prompts)"
            echo "  --lang fr|en  Language (default: en)"
            echo "  --step N      Legacy: same as --setup --step N"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# ── Global prerequisites ─────────────────────────────────────
section_title "Prerequisites"
check_prerequisite "incus"
check_incus_socket

# ── Dispatch: setup mode ─────────────────────────────────────
if [[ "$SETUP" == "true" ]]; then
    step_arg=""
    [[ -n "$LEGACY_STEP" ]] && step_arg="--step $LEGACY_STEP"
    [[ "$GUIDE_AUTO" == "true" ]] && step_arg="$step_arg --auto"
    # shellcheck disable=SC2086
    exec bash "$SCRIPT_DIR/guide-setup.sh" $step_arg
fi

# ── Dispatch: single chapter ─────────────────────────────────
if [[ -n "$CHAPTER" ]]; then
    ch_glob="$SCRIPT_DIR/guide/ch$(printf '%02d' "$CHAPTER")-"
    ch_scripts=("${ch_glob}"*.sh)
    if [[ -f "${ch_scripts[0]}" ]]; then
        exec bash "${ch_scripts[0]}"
    fi
    error_box "Chapter $CHAPTER not found" \
        "Available: 1-${GUIDE_TOTAL_CHAPTERS}"
    exit 1
fi

# ── Chapter menu ──────────────────────────────────────────────
check_deployed_domains
echo ""
echo -e "  ${C_BOLD}${C_CYAN}anklume Capability Tour${C_RESET}"
echo ""
echo -e "  ${C_DIM}Discover what anklume can do for you.${C_RESET}"
echo -e "  ${C_DIM}Each chapter: explain → demo → try it → recap${C_RESET}"
echo ""

if [[ "$GUIDE_AUTO" == "true" ]]; then
    for n in $(seq 1 "$GUIDE_TOTAL_CHAPTERS"); do
        ch_scripts=("$SCRIPT_DIR/guide/ch$(printf '%02d' "$n")-"*.sh)
        [[ -f "${ch_scripts[0]}" ]] && bash "${ch_scripts[0]}" || true
    done
    echo ""
    echo -e "  ${C_GREEN}${C_BOLD}Tour complete!${C_RESET}"
    exit 0
fi

# Interactive menu
while true; do
    echo -e "  ${C_BOLD}Chapters:${C_RESET}"
    for n in $(seq 1 "$GUIDE_TOTAL_CHAPTERS"); do
        _g_arr=("$SCRIPT_DIR/guide/ch$(printf '%02d' "$n")-"*.sh)
        title=$(head -3 "${_g_arr[0]}" 2>/dev/null | grep '^# ' | sed 's/^# //' || echo "Chapter $n")
        echo -e "    ${C_CYAN}${n})${C_RESET} ${title}"
    done
    echo -e "    ${C_CYAN}s)${C_RESET} Initial setup wizard"
    echo -e "    ${C_CYAN}a)${C_RESET} Run all chapters"
    echo -e "    ${C_CYAN}q)${C_RESET} Quit"
    echo ""
    echo -ne "  ${C_BOLD}Choice:${C_RESET} "
    read -r choice
    case "$choice" in
        [1-8])
            _g_arr=("$SCRIPT_DIR/guide/ch$(printf '%02d' "$choice")-"*.sh)
            [[ -f "${_g_arr[0]}" ]] && bash "${_g_arr[0]}"
            echo ""
            ;;
        s|S) bash "$SCRIPT_DIR/guide-setup.sh" ;;
        a|A)
            for n in $(seq 1 "$GUIDE_TOTAL_CHAPTERS"); do
                _g_arr=("$SCRIPT_DIR/guide/ch$(printf '%02d' "$n")-"*.sh)
                [[ -f "${_g_arr[0]}" ]] && bash "${_g_arr[0]}" || true
            done
            ;;
        q|Q) echo ""; exit 0 ;;
        *) echo -e "  ${C_RED}Invalid choice${C_RESET}" ;;
    esac
done
