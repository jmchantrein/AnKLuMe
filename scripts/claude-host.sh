#!/usr/bin/env bash
# Launch Claude Code as root for AnKLuMe host development.
#
# Two modes:
#
#   make claude-host                 # Guarded mode: guard hook + audit log
#   make claude-host YOLO=1          # YOLO mode: no restrictions, just SANDBOX=1
#
# Guarded mode:
#   - PreToolUse guard hook (allow/block/ask per command)
#   - Full audit logging to ~/.anklume/host-audit/
#   - --skip-permissions (guard hook is the permission layer)
#
# YOLO mode:
#   - No guard hook, no audit, no settings file
#   - --dangerously-skip-permissions (maximum permissiveness)
#   - SANDBOX=1 only (required to bypass Claude Code's root refusal)
#   - This is what you use when you need Claude to just work™
#
# Both modes:
#   RESUME=1   Resume last session (--continue)
#   CMD="..."  One-shot prompt mode (--prompt)
#
# Prerequisites: Claude Code CLI installed, root/sudo access
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SETTINGS_FILE="$PROJECT_DIR/.claude/host-settings.json"
LOG_DIR="${HOME}/.anklume/host-audit"
RESUME="${RESUME:-}"
CMD="${CMD:-}"
YOLO="${YOLO:-}"

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${BLUE}[AnKLuMe]${NC} $*"; }
warn()  { echo -e "${YELLOW}[AnKLuMe]${NC} $*"; }
error() { echo -e "${RED}[AnKLuMe]${NC} $*" >&2; }

# --- Pre-flight checks ---

if [ "$(id -u)" -ne 0 ]; then
    error "This script must be run as root (sudo -s or sudo make claude-host)"
    error ""
    error "Recommended way:"
    error "  sudo -s"
    error "  cd $(pwd)"
    error "  make claude-host"
    exit 1
fi

if ! command -v claude &>/dev/null; then
    error "Claude Code CLI not found. Install with:"
    error "  npm install -g @anthropic-ai/claude-code"
    exit 1
fi

# Detect the real user's home (when using sudo -s)
REAL_HOME="${HOME}"
if [ -n "${SUDO_USER:-}" ]; then
    REAL_HOME="$(getent passwd "$SUDO_USER" | cut -d: -f6)"
fi

# --- Mode-specific setup ---

if [ -n "$YOLO" ]; then
    # ══════════════════════════════════════════════════
    # YOLO MODE — no restrictions
    # ══════════════════════════════════════════════════
    echo ""
    warn "╔══════════════════════════════════════════════════╗"
    warn "║       AnKLuMe Host — ${RED}${BOLD}YOLO MODE${NC}${YELLOW}                  ║"
    warn "╠══════════════════════════════════════════════════╣"
    warn "║  ${RED}No guard hook, no audit, no restrictions${NC}${YELLOW}        ║"
    warn "║  SANDBOX=1 (only to allow root execution)       ║"
    warn "║  --dangerously-skip-permissions                 ║"
    warn "╚══════════════════════════════════════════════════╝"
    echo ""

    CLAUDE_ARGS=(
        "--project-dir" "$PROJECT_DIR"
        "--dangerously-skip-permissions"
    )
else
    # ══════════════════════════════════════════════════
    # GUARDED MODE — guard hook + audit
    # ══════════════════════════════════════════════════
    mkdir -p "$PROJECT_DIR/.claude" "$LOG_DIR"

    cat > "$SETTINGS_FILE" << 'SETTINGS_EOF'
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "bash scripts/claude-host-guard.sh"
          }
        ]
      }
    ]
  }
}
SETTINGS_EOF

    echo ""
    info "╔══════════════════════════════════════════════════╗"
    info "║       AnKLuMe Host — ${GREEN}${BOLD}GUARDED MODE${NC}${BLUE}              ║"
    info "╠══════════════════════════════════════════════════╣"
    info "║  SANDBOX=1 + --skip-permissions + guard hook    ║"
    info "║  Audit log: ~/.anklume/host-audit/              ║"
    info "╠══════════════════════════════════════════════════╣"
    info "║  Guard: scripts/claude-host-guard.sh            ║"
    info "║  ALLOW: incus, nft, systemctl, make, git,       ║"
    info "║         ansible, pytest, molecule, nvidia-smi   ║"
    info "║  BLOCK: rm -rf /, dd, mkfs, reboot, shutdown,   ║"
    info "║         force-push main, curl|bash, passwd      ║"
    info "║  ASK:   anything else → user confirmation       ║"
    info "╚══════════════════════════════════════════════════╝"

    AUDIT_COUNT=0
    if [ -f "$LOG_DIR/session-$(date +%Y%m%d).jsonl" ]; then
        AUDIT_COUNT=$(wc -l < "$LOG_DIR/session-$(date +%Y%m%d).jsonl")
    fi
    info "Audit entries today: ${AUDIT_COUNT}"
    echo ""

    CLAUDE_ARGS=(
        "--project-dir" "$PROJECT_DIR"
        "--skip-permissions"
    )

    export CLAUDE_CODE_SETTINGS_FILE="$SETTINGS_FILE"
fi

# --- Common options ---

if [ -n "$RESUME" ]; then
    CLAUDE_ARGS+=("--continue")
    info "Resuming last session..."
fi

if [ -n "$CMD" ]; then
    CLAUDE_ARGS+=("--prompt" "$CMD")
    info "Running: $CMD"
fi

# SANDBOX=1 is required — Claude Code refuses to run as root without it
export SANDBOX=1
export HOME="$REAL_HOME"

cd "$PROJECT_DIR"
info "Executing: claude ${CLAUDE_ARGS[*]}"
exec claude "${CLAUDE_ARGS[@]}"
