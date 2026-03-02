#!/usr/bin/env bash
# guide-lib.sh — UI toolkit for the anklume interactive guide
# Sourced by guide.sh and chapter scripts. Not executed directly.

# Guard against double-sourcing
[[ -n "${_GUIDE_LIB_LOADED:-}" ]] && return 0
_GUIDE_LIB_LOADED=1

# ── ANSI 256-color palette ──────────────────────────────────
# shellcheck disable=SC2034
C_RED='\033[38;5;196m'; C_GREEN='\033[38;5;82m'; C_YELLOW='\033[38;5;220m'
# shellcheck disable=SC2034
C_BLUE='\033[38;5;69m'; C_CYAN='\033[38;5;80m'
# shellcheck disable=SC2034
C_MAGENTA='\033[38;5;170m'; C_DIM='\033[2m'; C_BOLD='\033[1m'; C_RESET='\033[0m'
CHK='✓'; CROSS='✗'; ARROW='▸'; BAR_FULL='█'; BAR_EMPTY='░'
SPINNER_CHARS='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
export GUIDE_AUTO="${GUIDE_AUTO:-false}" GUIDE_LANG="${GUIDE_LANG:-en}"
SPINNER_PID=""
GUIDE_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GUIDE_PROJECT_DIR="$(cd "$GUIDE_SCRIPT_DIR/.." && pwd)"
export GUIDE_PROJECT_DIR
export GUIDE_TOTAL_CHAPTERS=8

# ── Box drawing ─────────────────────────────────────────────

box_header() {
    local ch="$1" total="$2" title="$3" w=52
    local bar filled empty pbar
    bar=$(printf '━%.0s' $(seq 1 $((w - 2))))
    echo ""
    echo -e "${C_CYAN}┏━${bar}━┓${C_RESET}"
    printf "${C_CYAN}┃${C_RESET}  ${C_BOLD}Chapter %d / %d — %-*s${C_RESET}${C_CYAN}┃${C_RESET}\n" \
        "$ch" "$total" $((w - 20)) "$title"
    filled=$((ch * (w - 12) / total))
    empty=$((w - 12 - filled))
    pbar=""
    for ((i = 0; i < filled; i++)); do pbar+="$BAR_FULL"; done
    for ((i = 0; i < empty; i++)); do pbar+="$BAR_EMPTY"; done
    printf "${C_CYAN}┃${C_RESET}  [${C_GREEN}%s${C_RESET}] %d/%d %*s${C_CYAN}┃${C_RESET}\n" \
        "$pbar" "$ch" "$total" $((w - ${#pbar} - 12)) ""
    echo -e "${C_CYAN}┗━${bar}━┛${C_RESET}"
    echo ""
}

section_title() {
    echo -e "\n  ${C_BOLD}${C_CYAN}── $1 ──${C_RESET}\n"
}

# ── Status indicators ───────────────────────────────────────

check_ok()   { echo -e "  ${C_GREEN}${CHK}${C_RESET} $1"; }
check_fail() { echo -e "  ${C_RED}${CROSS}${C_RESET} $1"; }
check_warn() { echo -e "  ${C_YELLOW}!${C_RESET} $1"; }
check_info() { echo -e "  ${C_DIM}$1${C_RESET}"; }

error_box() {
    local title="$1"; shift
    local w=52 bar
    bar=$(printf '━%.0s' $(seq 1 $((w - 2))))
    echo -e "\n${C_RED}┏━${bar}━┓${C_RESET}"
    printf "${C_RED}┃ ${CROSS} %-$((w - 5))s┃${C_RESET}\n" "$title"
    for line in "$@"; do
        printf "${C_RED}┃${C_RESET}   %-$((w - 5))s${C_RED}┃${C_RESET}\n" "$line"
    done
    echo -e "${C_RED}┗━${bar}━┛${C_RESET}\n"
}

key_value() {
    local k="$1" v="$2" w="${3:-40}" dots
    dots=$((w - ${#k} - ${#v}))
    [[ $dots -lt 2 ]] && dots=2
    local dotstr
    dotstr=$(printf '.%.0s' $(seq 1 "$dots"))
    echo -e "  ${k}${C_DIM}${dotstr}${C_RESET}${C_BOLD}${v}${C_RESET}"
}

# ── Spinner ─────────────────────────────────────────────────

spinner_start() {
    local msg="$1"
    [[ "$GUIDE_AUTO" == "true" ]] && { check_info "$msg"; return; }
    (
        local i=0 len=${#SPINNER_CHARS}
        while true; do
            printf "\r  ${C_CYAN}%s${C_RESET} %s" "${SPINNER_CHARS:$((i % len)):1}" "$msg"
            sleep 0.1
            i=$((i + 1))
        done
    ) &
    SPINNER_PID=$!
    disown "$SPINNER_PID" 2>/dev/null
}

spinner_stop() {
    [[ -n "$SPINNER_PID" ]] || return 0
    kill "$SPINNER_PID" 2>/dev/null
    wait "$SPINNER_PID" 2>/dev/null || true
    SPINNER_PID=""
    printf "\r%60s\r" ""
}

# ── Prompts ─────────────────────────────────────────────────

guide_confirm() {
    [[ "$GUIDE_AUTO" == "true" ]] && return 0
    echo -ne "\n  ${C_BOLD}$1${C_RESET} ${C_DIM}[Y/n]${C_RESET} "
    local ans
    read -r ans
    [[ -z "$ans" || "$ans" =~ ^[Yy] ]]
}

guide_pause() {
    [[ "$GUIDE_AUTO" == "true" ]] && return
    echo -e "\n  ${C_DIM}Press Enter to continue...${C_RESET}"
    read -r
}

# ── Prerequisite checks ────────────────────────────────────

detect_distro() {
    if [[ -f /etc/os-release ]]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        echo "${ID:-unknown}"
    else
        echo "unknown"
    fi
}

install_hint() {
    local t="$1" d
    d="$(detect_distro)"
    case "$d" in
        debian|ubuntu)            echo "sudo apt install $t" ;;
        arch|cachyos|endeavouros) echo "sudo pacman -S $t" ;;
        fedora)                   echo "sudo dnf install $t" ;;
        *)                        echo "Install $t via your package manager" ;;
    esac
}

check_prerequisite() {
    local tool="$1" msg="${2:-}"
    if command -v "$tool" &>/dev/null; then
        check_ok "$tool"
        return 0
    fi
    [[ -z "$msg" ]] && msg="$(install_hint "$tool")"
    error_box "$tool is required" "$msg" "" "Install it, then re-run the guide."
    exit 1
}

check_incus_socket() {
    if incus info &>/dev/null 2>&1; then
        check_ok "Incus daemon accessible"
        return 0
    fi
    error_box "Incus daemon not accessible" \
        "Start incusd or check socket permissions." \
        "  systemctl start incus"
    exit 1
}

check_deployed_domains() {
    local out
    out="$(incus list --all-projects --format csv -c n 2>/dev/null)" || true
    if [[ -n "$out" ]]; then
        check_ok "Deployed instances found"
        return 0
    fi
    error_box "No deployed infrastructure" \
        "Deploy your infrastructure first:" \
        "  anklume sync && anklume domain apply"
    exit 1
}

skip_chapter() {
    echo -e "\n  ${C_YELLOW}${ARROW} Chapter skipped:${C_RESET} $1\n"
}

# ── Demo / navigation ──────────────────────────────────────
run_demo() {
    check_info "$ $1"
    echo ""
    if bash -c "$1" 2>&1 | sed 's/^/    /'; then
        check_ok "Done"
    else
        check_warn "Command had warnings"
    fi
}

chapter_recap() {
    echo -e "\n  ${C_GREEN}${CHK} Recap:${C_RESET} ${C_BOLD}$1${C_RESET}"
}

next_chapter() { guide_pause; }

# ── Cleanup trap ────────────────────────────────────────────
_guide_cleanup() { spinner_stop; }
trap _guide_cleanup EXIT
