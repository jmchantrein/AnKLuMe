#!/usr/bin/env bash
# AI-assisted autonomous development for AnKLuMe (Phase 13).
# Takes a task description, creates a feature branch, uses an LLM
# to implement the task, runs tests, and optionally creates a PR.
#
# Usage: ai-develop.sh "Task description"
# See docs/ai-testing.md for full documentation.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

die() { echo "ERROR: $*" >&2; exit 1; }

# shellcheck source=scripts/ai-config.sh
source "$SCRIPT_DIR/ai-config.sh"

# ── Task-to-branch slug ──────────────────────────────────────
slugify() {
    echo "$1" | tr '[:upper:]' '[:lower:]' | tr -cs '[:alnum:]' '-' \
        | sed 's/^-//;s/-$//' | cut -c1-50
}

# ── Build project context ────────────────────────────────────
build_project_context() {
    local context_file="$1"
    local task="$2"

    {
        echo "=== Task Description ==="
        echo "$task"
        echo ""
        echo "=== Project Conventions (CLAUDE.md) ==="
        if [ -f CLAUDE.md ]; then
            cat CLAUDE.md
        fi
        echo ""
        echo "=== Current Roadmap Status ==="
        if [ -f docs/ROADMAP.md ]; then
            # Extract the "Current State" section
            sed -n '/^## Current State/,/^---/p' docs/ROADMAP.md 2>/dev/null || true
        fi
        echo ""
        echo "=== Experience library (known patterns and fixes) ==="
        if [ -d experiences/fixes ]; then
            for exp_file in experiences/fixes/*.yml; do
                [ -f "$exp_file" ] || continue
                echo "--- $(basename "$exp_file") ---"
                cat "$exp_file"
            done
        fi
        if [ -d experiences/patterns ]; then
            for exp_file in experiences/patterns/*.yml; do
                [ -f "$exp_file" ] || continue
                echo "--- $(basename "$exp_file") ---"
                cat "$exp_file"
            done
        fi
    } > "$context_file"
}

# ── Backend dispatch for development tasks ────────────────────

develop_with_ollama() {
    local context_file="$1"
    local task="$2"
    local context
    context="$(cat "$context_file")"

    local prompt="You are an expert Ansible/infrastructure developer working on AnKLuMe.

Task: ${task}

Project context:
${context}

Implement the task following the project conventions. Respond with:
1. A list of files to create or modify
2. For each file, provide the complete content or a unified diff

Use YAML best practices, FQCN for Ansible modules, and follow DRY/KISS."

    local response_file="${AI_LOG_DIR}/${_ai_session_id}-develop-response.txt"

    ai_log "Querying Ollama for development task..."
    if ! curl -sf "${AI_OLLAMA_URL}/api/generate" \
        -d "$(python3 -c "import json; print(json.dumps({'model':'${AI_OLLAMA_MODEL}','prompt':'''${prompt}''','stream':False}))")" \
        | python3 -c "import json,sys; print(json.load(sys.stdin)['response'])" \
        > "$response_file" 2>/dev/null; then
        ai_log "ERROR: Ollama query failed"
        return 1
    fi

    ai_log "Response saved to: ${response_file}"
    if [ "$AI_DRY_RUN" = "true" ]; then
        ai_log "DRY_RUN: Proposed implementation saved (not applied)"
        cat "$response_file"
        return 1
    fi

    ai_log "WARNING: Ollama responses for development tasks may need manual application"
    cat "$response_file"
    return 1
}

develop_with_claude_code() {
    local context_file="$1"
    local task="$2"

    local prompt="Read CLAUDE.md for project conventions. Read docs/ROADMAP.md for phase details.

Your task: ${task}

Implementation requirements:
- Follow all conventions in CLAUDE.md
- Write tests before implementation (TDD)
- Run ruff and yamllint after changes
- Commit with descriptive messages
- Keep changes minimal and focused"

    if [ "$AI_DRY_RUN" = "true" ]; then
        ai_log "DRY_RUN: would run Claude Code with task: ${task}"
        echo "$prompt" > "${AI_LOG_DIR}/${_ai_session_id}-prompt.txt"
        ai_log "Prompt saved to: ${AI_LOG_DIR}/${_ai_session_id}-prompt.txt"
        return 0
    fi

    ai_log "Launching Claude Code for development..."
    claude -p "$prompt" --dangerously-skip-permissions \
        >> "$_ai_log_file" 2>&1
}

develop_with_aider() {
    local context_file="$1"
    local task="$2"

    local msg="Read CLAUDE.md for project conventions. ${task}"

    if [ "$AI_DRY_RUN" = "true" ]; then
        ai_log "DRY_RUN: would run Aider with task: ${task}"
        return 0
    fi

    local model_arg="--model ollama_chat/${AI_OLLAMA_MODEL}"

    ai_log "Launching Aider for development..."
    # shellcheck disable=SC2086
    aider $model_arg --yes --message "$msg" >> "$_ai_log_file" 2>&1
}

develop_with_remote() {
    local context_file="$1"
    local task="$2"
    local context
    context="$(cat "$context_file")"

    local prompt="You are an expert developer. Implement this task:

${task}

Project context:
${context}

Provide complete file contents for each file that needs to be created or modified.
Format: filename followed by content in a code block."

    local response_file="${AI_LOG_DIR}/${_ai_session_id}-develop-response.txt"

    ai_log "Querying Claude API for development task..."
    local payload
    payload="$(python3 -c "
import json
print(json.dumps({
    'model': 'claude-sonnet-4-5-20250929',
    'max_tokens': 8192,
    'messages': [{'role': 'user', 'content': '''${prompt}'''}]
}))
")"

    if ! curl -sf "https://api.anthropic.com/v1/messages" \
        -H "x-api-key: ${AI_ANTHROPIC_KEY}" \
        -H "anthropic-version: 2023-06-01" \
        -H "content-type: application/json" \
        -d "$payload" \
        | python3 -c "import json,sys; r=json.load(sys.stdin); print(r['content'][0]['text'])" \
        > "$response_file" 2>/dev/null; then
        ai_log "ERROR: Claude API query failed"
        return 1
    fi

    ai_log "Response saved to: ${response_file}"
    if [ "$AI_DRY_RUN" = "true" ]; then
        cat "$response_file"
        return 1
    fi

    ai_log "WARNING: API responses for development tasks may need manual application"
    cat "$response_file"
    return 1
}

# ── Run tests ────────────────────────────────────────────────
run_all_tests() {
    local log_file="${AI_LOG_DIR}/${_ai_session_id}-tests.log"

    ai_log "Running test suite..."

    # Generator tests (always available)
    if python3 -m pytest tests/ -v > "$log_file" 2>&1; then
        ai_log "Generator tests: PASS"
    else
        ai_log "Generator tests: FAIL"
        tail -20 "$log_file"
        return 1
    fi

    # Molecule tests (if roles have molecule dirs and incus is available)
    if command -v molecule &>/dev/null && command -v incus &>/dev/null; then
        for role_dir in roles/*/molecule; do
            local role
            role="$(basename "$(dirname "$role_dir")")"
            ai_log "Molecule test: ${role}"
            if (cd "roles/${role}" && molecule test) >> "$log_file" 2>&1; then
                ai_log "  PASS: ${role}"
            else
                ai_log "  FAIL: ${role}"
                return 1
            fi
        done
    else
        ai_log "Skipping Molecule tests (molecule or incus not available)"
    fi

    return 0
}

# ── Entry point ──────────────────────────────────────────────

usage() {
    cat <<'USAGE'
Usage: ai-develop.sh [options] "Task description"

Autonomous development: creates a feature branch, uses an LLM to
implement the task, runs tests, and optionally creates a PR.

Options:
  -h, --help     Show this help
  --mode MODE    Override AI_MODE
  --dry-run      Show what would be done without applying changes
  --no-dry-run   Apply changes directly

Environment:
  ANKLUME_AI_MODE         AI backend (default: none)
  ANKLUME_AI_DRY_RUN      Dry-run mode (default: true)
  ANKLUME_AI_AUTO_PR      Auto-create PRs (default: false)
  ANKLUME_AI_MAX_RETRIES  Max test+fix iterations (default: 3)

Examples:
  ai-develop.sh "Add monitoring role with Prometheus node exporter"
  ai-develop.sh --mode claude-code "Implement Phase 14 STT service"
  ai-develop.sh --mode local --dry-run "Add backup role"
USAGE
}

main() {
    local task=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            -h|--help) usage; exit 0 ;;
            --mode) AI_MODE="$2"; shift 2 ;;
            --dry-run) AI_DRY_RUN="true"; shift ;;
            --no-dry-run) AI_DRY_RUN="false"; shift ;;
            -*) die "Unknown option: $1" ;;
            *) task="$1"; shift ;;
        esac
    done

    [ -n "$task" ] || die "Task description required. Usage: ai-develop.sh \"Task description\""
    [ "$AI_MODE" != "none" ] || die "AI_MODE must be set for development. Use --mode <backend>"

    ai_validate_config
    ai_init_session "ai-dev"

    local branch_slug
    branch_slug="$(slugify "$task")"
    local branch="feature/${branch_slug}"

    # Create feature branch (unless dry-run)
    if [ "$AI_DRY_RUN" != "true" ]; then
        ai_create_branch "$branch"
    fi

    # Build context
    local context_file="${AI_LOG_DIR}/${_ai_session_id}-context.txt"
    build_project_context "$context_file" "$task"

    # Dispatch to backend
    local attempt=1
    local success=false

    while [ "$attempt" -le "$AI_MAX_RETRIES" ]; do
        ai_log "Development attempt ${attempt}/${AI_MAX_RETRIES}"

        case "$AI_MODE" in
            local)       develop_with_ollama "$context_file" "$task" ;;
            remote)      develop_with_remote "$context_file" "$task" ;;
            claude-code) develop_with_claude_code "$context_file" "$task" ;;
            aider)       develop_with_aider "$context_file" "$task" ;;
        esac

        # In dry-run, we stop after showing the proposal
        if [ "$AI_DRY_RUN" = "true" ]; then
            ai_log "DRY_RUN: development proposal shown above"
            break
        fi

        # Run tests
        if run_all_tests; then
            ai_log "All tests pass after attempt ${attempt}"
            success=true
            break
        fi

        ai_log "Tests failed, retrying..."
        attempt=$((attempt + 1))
    done

    # Summary
    ai_log ""
    ai_log "===== Development Session ====="
    ai_log "Task: ${task}"
    ai_log "Branch: ${branch}"
    ai_log "Mode: ${AI_MODE}"
    ai_log "Dry-run: ${AI_DRY_RUN}"
    ai_log "Success: ${success}"
    ai_log "Session log: ${_ai_log_file}"

    # Auto-learn: mine experiences from successful development
    if [ "$success" = "true" ]; then
        ai_log "Mining experiences from development session..."
        python3 "$SCRIPT_DIR/mine-experiences.py" --incremental 2>&1 | while IFS= read -r line; do
            ai_log "  $line"
        done
    fi

    # Create PR if successful
    if [ "$success" = "true" ]; then
        ai_create_pr \
            "feat: ${task}" \
            "$(cat <<EOF
## Summary
- Task: ${task}
- AI mode: ${AI_MODE}
- Attempts: ${attempt}

## Session
- Session ID: ${_ai_session_id}
- Full log: ${_ai_log_file}

🤖 Generated with AI-assisted development (AnKLuMe Phase 13)
EOF
)"
    fi

    [ "$success" = "true" ] || [ "$AI_DRY_RUN" = "true" ]
}

main "$@"
