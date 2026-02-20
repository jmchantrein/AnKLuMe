#!/usr/bin/env bash
# Launch Claude Code with root access for AnKLuMe host development.
#
# This script configures Claude Code with:
#   - AnKLuMe-specific PreToolUse guard hook (allowlist/blocklist)
#   - Full audit logging to ~/.anklume/host-audit/
#   - Scoped permissions for infrastructure operations
#   - Sandbox mode (SANDBOX=1) for base protection
#
# Usage:
#   make claude-host                    # Interactive mode
#   make claude-host RESUME=1           # Resume last session
#   make claude-host CMD="fix the bug"  # One-shot prompt
#   make claude-host YOLO=1             # Disable sandbox (full filesystem access)
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
NC='\033[0m'

info()  { echo -e "${BLUE}[AnKLuMe]${NC} $*"; }
warn()  { echo -e "${YELLOW}[AnKLuMe]${NC} $*"; }
error() { echo -e "${RED}[AnKLuMe]${NC} $*" >&2; }

# --- Pre-flight checks ---

# Must be root
if [ "$(id -u)" -ne 0 ]; then
    error "This script must be run as root (sudo -s or sudo make claude-host)"
    error ""
    error "Recommended way:"
    error "  sudo -s"
    error "  cd $(pwd)"
    error "  make claude-host"
    exit 1
fi

# Claude Code must be installed
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

# --- Generate settings ---

mkdir -p "$PROJECT_DIR/.claude" "$LOG_DIR"

info "Generating host-mode settings..."

# Settings file: only the guard hook.
# Permission control is handled entirely by the guard hook (exit 0/1/2).
# --skip-permissions disables Claude Code's built-in permission system,
# so the "permissions" section is intentionally absent.
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

# --- Print status ---

echo ""
if [ -n "$YOLO" ]; then
    SANDBOX_LABEL="DISABLED (--yolo)"
    SANDBOX_COLOR="${RED}"
else
    SANDBOX_LABEL="SANDBOX=1 (base protection)"
    SANDBOX_COLOR="${GREEN}"
fi

info "╔══════════════════════════════════════════════════╗"
info "║       AnKLuMe Host Development Mode             ║"
info "╠══════════════════════════════════════════════════╣"
info "║  Root access:     YES (infrastructure ops)      ║"
info "║  --skip-permissions + guard hook (see below)    ║"
info "║  Audit log:       ~/.anklume/host-audit/        ║"
printf "  ${BLUE}[AnKLuMe]${NC} ║  Sandbox:         ${SANDBOX_COLOR}%-29s${NC}║\n" "$SANDBOX_LABEL"
info "╠══════════════════════════════════════════════════╣"
info "║  Guard hook: scripts/claude-host-guard.sh       ║"
info "║  ALLOW: incus, nft, systemctl, make, git,       ║"
info "║         ansible, pytest, molecule, nvidia-smi   ║"
info "║  BLOCK: rm -rf /, dd, mkfs, reboot, shutdown,   ║"
info "║         force-push main, curl|bash, passwd      ║"
info "║  ASK:   anything else → user confirmation       ║"
info "╚══════════════════════════════════════════════════╝"

if [ -n "$YOLO" ]; then
    warn "YOLO mode: sandbox disabled — Claude has full filesystem access"
    warn "Guard hook and audit logging still active"
fi
echo ""

# Show audit log info
AUDIT_COUNT=0
if [ -f "$LOG_DIR/session-$(date +%Y%m%d).jsonl" ]; then
    AUDIT_COUNT=$(wc -l < "$LOG_DIR/session-$(date +%Y%m%d).jsonl")
fi
info "Audit entries today: ${AUDIT_COUNT}"
echo ""

# --- Launch Claude Code ---
#
# Permission model (explicit):
#   --skip-permissions   : disables Claude Code's built-in permission prompts
#   Guard hook           : AnKLuMe-specific allow/block/ask (the REAL protection)
#   Audit log            : every Bash command logged to ~/.anklume/host-audit/
#
# Without YOLO: SANDBOX=1 restricts filesystem writes to CWD (bubblewrap)
# With    YOLO: no sandbox, full filesystem access
#
# The guard hook is ALWAYS active regardless of YOLO.

CLAUDE_ARGS=(
    "--project-dir" "$PROJECT_DIR"
    "--skip-permissions"
)

# Resume last session if requested
if [ -n "$RESUME" ]; then
    CLAUDE_ARGS+=("--continue")
    info "Resuming last session..."
fi

# One-shot prompt mode
if [ -n "$CMD" ]; then
    CLAUDE_ARGS+=("--prompt" "$CMD")
    info "Running: $CMD"
fi

# Set environment and launch
if [ -z "$YOLO" ]; then
    export SANDBOX=1
fi
export HOME="$REAL_HOME"
export CLAUDE_CODE_SETTINGS_FILE="$SETTINGS_FILE"

cd "$PROJECT_DIR"
info "Executing: claude --skip-permissions --project-dir $PROJECT_DIR"
exec claude "${CLAUDE_ARGS[@]}"
