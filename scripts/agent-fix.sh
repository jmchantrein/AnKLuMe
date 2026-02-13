#!/usr/bin/env bash
# Agent Teams fix mode — autonomous test fixing with Claude Code.
# Creates/reuses the test-runner container, launches Claude Code
# with Agent Teams to fix failing Molecule tests.
#
# Usage: agent-fix.sh [role]
# See docs/agent-teams.md for documentation.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

die() { echo "ERROR: $*" >&2; exit 1; }

# ── Configuration ────────────────────────────────────────────
RUNNER_NAME="${ANKLUME_RUNNER_NAME:-anklume}"
RUNNER_PROJECT="${ANKLUME_RUNNER_PROJECT:-default}"
REPO_DIR="/root/AnKLuMe"
LOG_DIR="${ANKLUME_AGENT_LOG_DIR:-logs}"
SESSION_ID="agent-fix-$(date +%Y%m%d-%H%M%S)"
SESSION_LOG="${LOG_DIR}/${SESSION_ID}.log"

mkdir -p "$LOG_DIR"

log() {
    local msg
    msg="[$(date '+%Y-%m-%d %H:%M:%S')] $*"
    echo "$msg" | tee -a "$SESSION_LOG"
}

# ── Verify prerequisites ────────────────────────────────────
verify_runner() {
    if ! incus project list --format csv >/dev/null 2>&1; then
        die "Cannot connect to the Incus daemon. Check that incus is installed and you have socket access."
    fi

    if ! incus info "$RUNNER_NAME" --project "$RUNNER_PROJECT" &>/dev/null; then
        die "Runner '${RUNNER_NAME}' not found. Run 'make runner-create' and 'make agent-runner-setup' first."
    fi

    if ! incus exec "$RUNNER_NAME" --project "$RUNNER_PROJECT" -- \
        command -v claude &>/dev/null; then
        die "Claude Code not installed in runner. Run 'make agent-runner-setup' first."
    fi

    log "Runner '${RUNNER_NAME}' verified with Claude Code"
}

inject_api_key() {
    local api_key="${ANTHROPIC_API_KEY:-}"
    if [ -z "$api_key" ]; then
        die "ANTHROPIC_API_KEY not set. Required for Claude Code Agent Teams."
    fi

    incus exec "$RUNNER_NAME" --project "$RUNNER_PROJECT" -- \
        bash -c "echo 'export ANTHROPIC_API_KEY=${api_key}' > /root/.anthropic_key"
    log "API key injected"
}

# ── Fix mode ─────────────────────────────────────────────────
run_fix() {
    local target_role="${1:-all}"

    local prompt
    if [ "$target_role" = "all" ]; then
        prompt="Run molecule test for all roles that have molecule/ directories.
For each failure:
1. Analyze the error log and the relevant source files
2. Create a fix branch (fix/<role>-<issue>)
3. Apply the minimal fix following CLAUDE.md conventions
4. Re-run the test for that role
5. If it passes, commit with message: fix(<role>): <description>
If all tests pass, create a single PR summarizing all fixes.
Use agent teams: spawn a Tester and a Fixer teammate.
Max retries per role: 3."
    else
        prompt="Run molecule test for the '${target_role}' role.
If it fails:
1. Analyze the error log and source files in roles/${target_role}/
2. Apply the minimal fix following CLAUDE.md conventions
3. Re-run the test
4. Commit if it passes: fix(${target_role}): <description>
Max retries: 3."
    fi

    log "Launching Claude Code Agent Teams (fix mode, target: ${target_role})"
    log "Prompt: ${prompt}"

    incus exec "$RUNNER_NAME" --project "$RUNNER_PROJECT" -- \
        bash -c "
            source /root/.anthropic_key 2>/dev/null || true
            cd ${REPO_DIR}
            git fetch origin && git pull origin main || true
            claude -p '${prompt}' --dangerously-skip-permissions
        " 2>&1 | tee -a "$SESSION_LOG"

    log "Fix session complete"
}

# ── Entry point ──────────────────────────────────────────────
usage() {
    cat <<'USAGE'
Usage: agent-fix.sh [options] [role]

Autonomous test fixing with Claude Code Agent Teams.
Runs inside the Incus-in-Incus sandbox (Phase 12).

Options:
  -h, --help    Show this help

Prerequisites:
  1. Runner container: make runner-create
  2. Agent setup: make agent-runner-setup
  3. ANTHROPIC_API_KEY environment variable

Examples:
  agent-fix.sh                 # Fix all failing roles
  agent-fix.sh base_system     # Fix one role
USAGE
}

main() {
    local target_role="all"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            -h|--help) usage; exit 0 ;;
            -*) die "Unknown option: $1" ;;
            *) target_role="$1"; shift ;;
        esac
    done

    log "=== Agent Fix Session: ${SESSION_ID} ==="
    verify_runner
    inject_api_key
    run_fix "$target_role"
    log "Session log: ${SESSION_LOG}"
}

main "$@"
