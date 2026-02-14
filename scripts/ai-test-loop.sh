#!/usr/bin/env bash
# AI-assisted test loop for AnKLuMe (Phase 13).
# Runs Molecule tests, sends failures to an LLM backend,
# applies fixes, and re-tests. Supports pluggable backends.
#
# Usage: ai-test-loop.sh [role]
# See docs/ai-testing.md for full documentation.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

die() { echo "ERROR: $*" >&2; exit 1; }

# shellcheck source=scripts/ai-config.sh
source "$SCRIPT_DIR/ai-config.sh"

# ── Main logic ───────────────────────────────────────────────

run_molecule_test() {
    local role="$1"
    local log_file="$2"

    ai_log "Running Molecule test: ${role}"
    if (cd "roles/${role}" && molecule test) > "$log_file" 2>&1; then
        ai_log "PASS: ${role}"
        return 0
    else
        ai_log "FAIL: ${role}"
        return 1
    fi
}

build_context() {
    # Build a context file with the failure log and relevant source code.
    local role="$1"
    local log_file="$2"
    local context_file="$3"

    {
        echo "=== Molecule test failure for role: ${role} ==="
        echo ""
        echo "=== Test log (last 100 lines) ==="
        tail -100 "$log_file"
        echo ""
        echo "=== Role tasks ==="
        if [ -f "roles/${role}/tasks/main.yml" ]; then
            cat "roles/${role}/tasks/main.yml"
        fi
        echo ""
        echo "=== Role defaults ==="
        if [ -f "roles/${role}/defaults/main.yml" ]; then
            cat "roles/${role}/defaults/main.yml"
        fi
        echo ""
        echo "=== Molecule verify ==="
        if [ -f "roles/${role}/molecule/default/verify.yml" ]; then
            cat "roles/${role}/molecule/default/verify.yml"
        fi
        echo ""
        echo "=== Known fix patterns (experience library) ==="
        if [ -d "${PROJECT_DIR}/experiences/fixes" ]; then
            for exp_file in "${PROJECT_DIR}/experiences/fixes"/*.yml; do
                [ -f "$exp_file" ] || continue
                echo "--- $(basename "$exp_file") ---"
                cat "$exp_file"
            done
        fi
    } > "$context_file"
}

search_experiences() {
    # Search the experience library for a matching fix pattern.
    # Sets EXP_MATCH_SOLUTION and EXP_MATCH_PREVENTION if found.
    # Returns 0 if match found, 1 otherwise.
    local log_file="$1"
    local exp_dir="${PROJECT_DIR}/experiences/fixes"

    EXP_MATCH_SOLUTION=""
    EXP_MATCH_PREVENTION=""
    EXP_MATCH_ID=""

    if [ ! -d "$exp_dir" ]; then
        return 1
    fi

    # Extract key error patterns from the log (more lines, deduplicated)
    local errors
    errors=$(grep -i "error\|failed\|fatal\|exception\|traceback\|cannot\|unable" \
        "$log_file" 2>/dev/null | sort -u | head -20) || true

    if [ -z "$errors" ]; then
        return 1
    fi

    # Search through experience files — match on problem AND solution keywords
    local errors_file
    errors_file="$(mktemp)"
    printf '%s' "$errors" > "$errors_file"

    local match
    match=$(python3 - "$exp_dir" "$errors_file" <<'PYEOF' 2>/dev/null) || true
import yaml, sys, os

errors = open(sys.argv[2]).read().lower()
exp_dir = sys.argv[1]
best_score = 0
best_entry = None

for fname in sorted(os.listdir(exp_dir)):
    if not fname.endswith('.yml'):
        continue
    fpath = os.path.join(exp_dir, fname)
    try:
        data = yaml.safe_load(open(fpath))
    except Exception:
        continue
    if not isinstance(data, list):
        continue
    for entry in data:
        if not isinstance(entry, dict) or 'problem' not in entry:
            continue
        words = entry['problem'].lower().split()
        score = sum(1 for w in words if len(w) > 3 and w in errors)
        if score > best_score and score >= 3:
            best_score = score
            best_entry = entry

if best_entry:
    eid = best_entry.get('id', 'unknown')
    sol = best_entry.get('solution', '').replace(chr(10), ' ')
    prev = best_entry.get('prevention', '').replace(chr(10), ' ')
    prob = best_entry.get('problem', '')
    print(f'{eid}|||{prob}|||{sol}|||{prev}')
PYEOF
    rm -f "$errors_file"

    if [ -n "$match" ]; then
        EXP_MATCH_ID="$(echo "$match" | cut -d'|' -f1)"
        local problem
        problem="$(echo "$match" | cut -d'|' -f4)"
        EXP_MATCH_SOLUTION="$(echo "$match" | cut -d'|' -f7)"
        EXP_MATCH_PREVENTION="$(echo "$match" | cut -d'|' -f10)"
        ai_log "Experience match: ${EXP_MATCH_ID} — ${problem}"
        ai_log "  Known solution: ${EXP_MATCH_SOLUTION}"
        return 0
    fi

    return 1
}

attempt_fix() {
    local context_file="$1"
    local role="$2"
    local log_file="${AI_LOG_DIR}/${_ai_session_id}-${role}-molecule.log"

    local instruction="Analyze this Molecule test failure for the '${role}' Ansible role and fix the issue."

    # Check experiences first (faster, no LLM cost)
    if search_experiences "$log_file"; then
        ai_log "Known fix pattern found in experience library (${EXP_MATCH_ID})"
        # Enrich the context file with the known solution
        {
            echo ""
            echo "=== KNOWN FIX FROM EXPERIENCE LIBRARY (${EXP_MATCH_ID}) ==="
            echo "Solution: ${EXP_MATCH_SOLUTION}"
            echo "Prevention: ${EXP_MATCH_PREVENTION}"
            echo "Apply this known fix first. Only deviate if it clearly doesn't match."
        } >> "$context_file"
        instruction="A known fix exists in the experience library for this error pattern.
Experience ID: ${EXP_MATCH_ID}
Known solution: ${EXP_MATCH_SOLUTION}
Prevention: ${EXP_MATCH_PREVENTION}

Apply this known fix to the '${role}' Ansible role. If the known fix doesn't apply exactly, adapt it to the specific context."
    fi

    case "$AI_MODE" in
        none)
            ai_log "AI_MODE=none: no automatic fix attempted"
            return 1
            ;;
        local)
            ai_fix_ollama "$context_file" "$instruction"
            ;;
        remote)
            ai_fix_remote "$context_file" "$instruction"
            ;;
        claude-code)
            ai_fix_claude_code "$context_file" "$instruction"
            ;;
        aider)
            ai_fix_aider "$context_file" "$instruction"
            ;;
    esac
}

test_and_fix_role() {
    local role="$1"
    local log_file="${AI_LOG_DIR}/${_ai_session_id}-${role}-molecule.log"
    local context_file="${AI_LOG_DIR}/${_ai_session_id}-${role}-context.txt"

    # Initial test
    if run_molecule_test "$role" "$log_file"; then
        return 0
    fi

    # No AI? Just report failure.
    if [ "$AI_MODE" = "none" ]; then
        return 1
    fi

    # AI fix loop
    local attempt=1
    while [ "$attempt" -le "$AI_MAX_RETRIES" ]; do
        ai_log "Fix attempt ${attempt}/${AI_MAX_RETRIES} for ${role}"

        build_context "$role" "$log_file" "$context_file"

        if ! attempt_fix "$context_file" "$role"; then
            ai_log "No fix produced for ${role}"
            return 1
        fi

        # Re-test after fix
        if run_molecule_test "$role" "$log_file"; then
            ai_log "Fix successful on attempt ${attempt} for ${role}"
            ai_commit_fix "fix(${role}): AI-assisted fix (${AI_MODE}, attempt ${attempt})"
            return 0
        fi

        attempt=$((attempt + 1))
    done

    ai_log "Max retries reached for ${role}"
    return 1
}

# ── Entry point ──────────────────────────────────────────────

usage() {
    cat <<'USAGE'
Usage: ai-test-loop.sh [options] [role]

Run Molecule tests with optional AI-assisted fixing.
If no role is specified, tests all roles with molecule/ directories.

Options:
  -h, --help     Show this help
  --mode MODE    Override AI_MODE (none, local, remote, claude-code, aider)
  --dry-run      Force dry-run mode (show fixes without applying)
  --no-dry-run   Disable dry-run mode
  --learn        After fixing, mine new experiences from this session

Environment:
  ANKLUME_AI_MODE         AI backend (default: none)
  ANKLUME_AI_DRY_RUN      Dry-run mode (default: true)
  ANKLUME_AI_AUTO_PR      Auto-create PRs (default: false)
  ANKLUME_AI_MAX_RETRIES  Max fix attempts per role (default: 3)
  ANKLUME_AI_OLLAMA_URL   Ollama API URL
  ANKLUME_AI_OLLAMA_MODEL Ollama model name
  ANTHROPIC_API_KEY       API key for remote mode

Examples:
  ai-test-loop.sh                          # Test all roles, no AI
  ai-test-loop.sh base_system              # Test one role
  ai-test-loop.sh --mode local             # Test + AI fix via Ollama
  ai-test-loop.sh --mode claude-code       # Test + AI fix via Claude Code
  ai-test-loop.sh --mode local --dry-run   # Show proposed fixes only
USAGE
}

main() {
    local target_role=""
    local learn_mode="false"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            -h|--help) usage; exit 0 ;;
            --mode) AI_MODE="$2"; shift 2 ;;
            --dry-run) AI_DRY_RUN="true"; shift ;;
            --no-dry-run) AI_DRY_RUN="false"; shift ;;
            --learn) learn_mode="true"; shift ;;
            -*) die "Unknown option: $1" ;;
            *) target_role="$1"; shift ;;
        esac
    done

    ai_validate_config
    ai_init_session "ai-test"

    # Create fix branch if AI is enabled and not in dry-run
    if [ "$AI_MODE" != "none" ] && [ "$AI_DRY_RUN" != "true" ]; then
        ai_create_branch "fix/ai-${_ai_session_id}"
    fi

    local passed=0
    local failed=0
    local failed_roles=""

    if [ -n "$target_role" ]; then
        # Test a single role
        if [ ! -d "roles/${target_role}/molecule" ]; then
            die "Role '${target_role}' has no molecule/ directory"
        fi

        if test_and_fix_role "$target_role"; then
            passed=1
        else
            failed=1
            failed_roles="$target_role"
        fi
    else
        # Test all roles with molecule directories
        for role_dir in roles/*/molecule; do
            local role
            role="$(basename "$(dirname "$role_dir")")"

            if test_and_fix_role "$role"; then
                passed=$((passed + 1))
            else
                failed=$((failed + 1))
                failed_roles="${failed_roles} ${role}"
            fi
        done
    fi

    # Summary
    ai_log ""
    ai_log "===== Test Results ====="
    ai_log "Passed: ${passed}"
    ai_log "Failed: ${failed}"
    [ -n "$failed_roles" ] && ai_log "Failed roles:${failed_roles}"
    ai_log "Session log: ${_ai_log_file}"

    # Auto-learn: mine experiences after any successful fix (not just --learn)
    # --learn forces mining even when no fixes were applied
    local should_mine="false"
    if [ "$learn_mode" = "true" ]; then
        should_mine="true"
    elif [ "$AI_MODE" != "none" ] && [ "$AI_DRY_RUN" != "true" ] && [ "$passed" -gt 0 ]; then
        # Auto-learn when AI actually applied fixes
        should_mine="true"
    fi

    if [ "$should_mine" = "true" ]; then
        ai_log "Mining new experiences from recent commits..."
        python3 "$SCRIPT_DIR/mine-experiences.py" --incremental 2>&1 | while IFS= read -r line; do
            ai_log "  $line"
        done
    fi

    # Create PR if fixes were committed and auto_pr is enabled
    if [ "$AI_MODE" != "none" ] && [ "$AI_DRY_RUN" != "true" ] && [ "$failed" -eq 0 ] && [ "$passed" -gt 0 ]; then
        ai_create_pr \
            "fix: AI-assisted test fixes (${AI_MODE})" \
            "$(cat <<EOF
## Summary
- AI mode: ${AI_MODE}
- Roles tested: $((passed + failed))
- All tests passing

## Session
- Session ID: ${_ai_session_id}
- Full log: ${_ai_log_file}

🤖 Generated with AI-assisted testing (AnKLuMe Phase 13)
EOF
)"
    fi

    [ "$failed" -eq 0 ]
}

main "$@"
