#!/usr/bin/env bash
# Agent Teams develop mode — autonomous feature development with Claude Code.
# Creates/reuses the test-runner container, launches Claude Code
# with Agent Teams to implement a task with testing and review.
#
# Usage: agent-develop.sh "Task description"
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
SESSION_ID="agent-dev-$(date +%Y%m%d-%H%M%S)"
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

    # Push key via stdin to avoid exposure in process list
    printf 'export ANTHROPIC_API_KEY=%s\n' "$api_key" \
        | incus file push - "${RUNNER_NAME}/root/.anthropic_key" --project "$RUNNER_PROJECT"
    incus exec "$RUNNER_NAME" --project "$RUNNER_PROJECT" -- chmod 600 /root/.anthropic_key
    log "API key injected"
}

# ── Task slug for branch name ────────────────────────────────
slugify() {
    echo "$1" | tr '[:upper:]' '[:lower:]' | tr -cs '[:alnum:]' '-' \
        | sed 's/^-//;s/-$//' | cut -c1-50
}

# ── Develop mode ─────────────────────────────────────────────
run_develop() {
    local task="$1"
    local branch_slug
    branch_slug="$(slugify "$task")"

    local prompt="Read ROADMAP.md and CLAUDE.md. Your task: ${task}

Use agent teams to parallelize the work:
- Builder teammate(s) for implementation
- Tester teammate to run molecule tests continuously
- Reviewer teammate to check code quality and ADR compliance

Workflow:
1. Create feature branch: feature/${branch_slug}
2. Implement following all CLAUDE.md conventions
3. Write/update tests (TDD: tests before implementation)
4. Run all validators: ruff, yamllint, ansible-lint
5. Iterate until Tester + Reviewer both approve
6. Commit with descriptive messages
7. Create a PR with a comprehensive description"

    log "Launching Claude Code Agent Teams (develop mode)"
    log "Task: ${task}"
    log "Branch: feature/${branch_slug}"

    incus exec "$RUNNER_NAME" --project "$RUNNER_PROJECT" -- \
        bash -c "
            source /root/.anthropic_key 2>/dev/null || true
            cd ${REPO_DIR}
            git fetch origin && git pull origin main || true
            claude -p '${prompt}' --dangerously-skip-permissions
        " 2>&1 | tee -a "$SESSION_LOG"

    log "Development session complete"
}

# ── Entry point ──────────────────────────────────────────────
usage() {
    cat <<'USAGE'
Usage: agent-develop.sh [options] "Task description"

Autonomous development with Claude Code Agent Teams.
Runs inside the Incus-in-Incus sandbox (Phase 12).

Options:
  -h, --help    Show this help

Prerequisites:
  1. Runner container: make runner-create
  2. Agent setup: make agent-runner-setup
  3. ANTHROPIC_API_KEY environment variable

Examples:
  agent-develop.sh "Implement Phase 14 STT service"
  agent-develop.sh "Add monitoring role with Prometheus node exporter"
  agent-develop.sh "Refactor incus_instances to support storage volumes"
USAGE
}

main() {
    local task=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            -h|--help) usage; exit 0 ;;
            -*) die "Unknown option: $1" ;;
            *) task="$1"; shift ;;
        esac
    done

    [ -n "$task" ] || die "Task description required. Usage: agent-develop.sh \"Task description\""

    log "=== Agent Develop Session: ${SESSION_ID} ==="
    verify_runner
    inject_api_key
    run_develop "$task"
    log "Session log: ${SESSION_LOG}"
}

main "$@"
