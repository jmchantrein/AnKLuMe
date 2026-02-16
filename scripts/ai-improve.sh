#!/usr/bin/env bash
# Spec-driven improvement loop for anklume.
# Proposes enhancements by comparing spec to implementation.
#
# Usage: ai-improve.sh --scope <generator|roles|nftables|all> [--dry-run]
# See docs/ai-testing.md for full documentation.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

die() { echo "ERROR: $*" >&2; exit 1; }

# shellcheck source=scripts/ai-config.sh
source "$SCRIPT_DIR/ai-config.sh"

# ── Argument parsing ──────────────────────────────────────

SCOPE="all"
IMPROVE_DRY_RUN="true"

usage() {
    cat <<'USAGE'
Usage: ai-improve.sh [options]

Spec-driven improvement loop. Compares SPEC.md and ARCHITECTURE.md
against the current implementation to identify gaps and propose fixes.

Options:
  -h, --help          Show this help
  --scope SCOPE       Focus area: generator, roles, nftables, all (default: all)
  --dry-run           Propose improvements without applying (default)
  --no-dry-run        Apply improvements automatically

Environment:
  ANKLUME_AI_MODE     AI backend (default: none)
  ANTHROPIC_API_KEY   API key for remote/claude-code mode

Examples:
  ai-improve.sh --scope generator           # Check generator vs spec
  ai-improve.sh --scope roles --no-dry-run  # Apply role improvements
  ai-improve.sh --scope all                 # Full analysis (dry-run)
USAGE
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help) usage; exit 0 ;;
        --scope) SCOPE="$2"; shift 2 ;;
        --dry-run) IMPROVE_DRY_RUN="true"; shift ;;
        --no-dry-run) IMPROVE_DRY_RUN="false"; shift ;;
        *) die "Unknown option: $1" ;;
    esac
done

case "$SCOPE" in
    generator|roles|nftables|all) ;;
    *) die "Invalid scope: '${SCOPE}'. Must be: generator, roles, nftables, all" ;;
esac

# ── Validation suite ──────────────────────────────────────

run_validation() {
    local results_file="$1"
    local failed=0

    echo "=== Running validation suite ===" | tee "$results_file"

    echo "--- make lint ---" >> "$results_file"
    if make lint >> "$results_file" 2>&1; then
        echo "LINT: PASS" | tee -a "$results_file"
    else
        echo "LINT: FAIL" | tee -a "$results_file"
        failed=1
    fi

    echo "--- make test-generator ---" >> "$results_file"
    if python3 -m pytest tests/ -v >> "$results_file" 2>&1; then
        echo "PYTEST: PASS" | tee -a "$results_file"
    else
        echo "PYTEST: FAIL" | tee -a "$results_file"
        failed=1
    fi

    return "$failed"
}

# ── Context building ──────────────────────────────────────

build_improve_context() {
    local scope="$1"
    local context_file="$2"
    local validation_file="$3"

    {
        echo "=== Improvement Analysis Request ==="
        echo "Scope: ${scope}"
        echo ""
        echo "=== SPEC.md (relevant sections) ==="
        head -200 docs/SPEC.md
        echo ""
        echo "=== ARCHITECTURE.md (relevant sections) ==="
        head -200 docs/ARCHITECTURE.md
        echo ""

        case "$scope" in
            generator)
                echo "=== Generator source ==="
                cat scripts/generate.py
                echo ""
                echo "=== Generator tests ==="
                cat tests/test_generate.py
                ;;
            roles)
                echo "=== Role listing ==="
                ls -la roles/
                echo ""
                for role_dir in roles/*/tasks/main.yml; do
                    local role
                    role="$(basename "$(dirname "$(dirname "$role_dir")")")"
                    echo "=== Role: ${role} (first 50 lines) ==="
                    head -50 "$role_dir"
                    echo ""
                done
                ;;
            nftables)
                echo "=== nftables role ==="
                cat roles/incus_nftables/tasks/main.yml
                echo ""
                cat roles/incus_nftables/defaults/main.yml
                echo ""
                if [ -d roles/incus_nftables/templates ]; then
                    for tmpl in roles/incus_nftables/templates/*; do
                        echo "=== Template: $(basename "$tmpl") ==="
                        cat "$tmpl"
                    done
                fi
                ;;
            all)
                echo "=== Generator source (first 100 lines) ==="
                head -100 scripts/generate.py
                echo ""
                echo "=== Roles overview ==="
                for role_dir in roles/*/; do
                    local role
                    role="$(basename "$role_dir")"
                    local lines=0
                    if [ -f "${role_dir}tasks/main.yml" ]; then
                        lines=$(wc -l < "${role_dir}tasks/main.yml")
                    fi
                    echo "  ${role}: ${lines} lines"
                done
                ;;
        esac

        echo ""
        echo "=== Validation results ==="
        cat "$validation_file"

        echo ""
        echo "=== Experiences library ==="
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

# ── Improvement application ───────────────────────────────

apply_improvement() {
    local context_file="$1"
    local instruction
    instruction="Analyze the gap between the specification (SPEC.md, ARCHITECTURE.md) and the current implementation.

For scope '${SCOPE}', identify concrete improvements that:
1. Close gaps between spec and implementation
2. Fix any validation failures
3. Improve code quality without changing behavior
4. Add missing test coverage

For each improvement, provide:
- Description of the gap
- The specific file and change needed
- Why this improves spec compliance

Respond ONLY with a unified diff (patch format) for each change.
Do not make changes that would break existing tests."

    case "$AI_MODE" in
        none)
            echo "AI_MODE=none: showing context only"
            echo "Context built at: ${context_file}"
            echo "Set AI_MODE to local/remote/claude-code for analysis"
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

# ── Main ──────────────────────────────────────────────────

main() {
    ai_validate_config
    ai_init_session "ai-improve"
    ai_log "Scope: ${SCOPE}, Dry-run: ${IMPROVE_DRY_RUN}"

    # Override dry-run setting (AI_DRY_RUN used by ai-config.sh backends)
    # shellcheck disable=SC2034
    AI_DRY_RUN="$IMPROVE_DRY_RUN"

    # shellcheck disable=SC2154  # _ai_session_id set by ai_init_session in ai-config.sh
    local validation_file="${AI_LOG_DIR}/${_ai_session_id}-validation.log"
    local context_file="${AI_LOG_DIR}/${_ai_session_id}-context.txt"

    # Step 1: Run validation suite
    ai_log "Running validation suite..."
    local validation_ok=0
    if run_validation "$validation_file"; then
        ai_log "All validations passed"
        validation_ok=1
    else
        ai_log "Some validations failed (see log for details)"
    fi

    # Step 2: Build context
    ai_log "Building improvement context for scope: ${SCOPE}"
    build_improve_context "$SCOPE" "$context_file" "$validation_file"
    ai_log "Context file: ${context_file}"

    # Step 3: Create branch if applying changes
    if [ "$AI_MODE" != "none" ] && [ "$IMPROVE_DRY_RUN" != "true" ]; then
        ai_create_branch "improve/${SCOPE}-${_ai_session_id}"
    fi

    # Step 4: Send to LLM for analysis
    ai_log "Requesting improvement analysis..."
    if ! apply_improvement "$context_file"; then
        ai_log "No improvements applied"
        return 0
    fi

    # Step 5: Re-validate after changes
    if [ "$IMPROVE_DRY_RUN" != "true" ]; then
        ai_log "Re-validating after improvements..."
        local revalidation_file="${AI_LOG_DIR}/${_ai_session_id}-revalidation.log"
        if run_validation "$revalidation_file"; then
            ai_log "All validations pass after improvements"
            ai_commit_fix "improve(${SCOPE}): spec-driven improvements (${AI_MODE})"

            if [ "$validation_ok" -eq 1 ]; then
                # shellcheck disable=SC2154  # _ai_log_file set by ai-config.sh
                ai_create_pr \
                    "improve(${SCOPE}): spec-driven improvements" \
                    "$(cat <<EOF
## Summary
- Scope: ${SCOPE}
- AI mode: ${AI_MODE}
- Improvements applied and validated

## Session
- Session ID: ${_ai_session_id}
- Full log: ${_ai_log_file}

Generated with anklume improvement loop (Phase 18d)
EOF
)"
            fi
        else
            ai_log "Validation failed after improvements; discarding changes"
            git checkout -- . 2>/dev/null || true
        fi
    fi

    # shellcheck disable=SC2154  # _ai_log_file set by ai_init_session in ai-config.sh
    ai_log "Session complete: ${_ai_log_file}"
}

main
