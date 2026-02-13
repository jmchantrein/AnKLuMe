#!/usr/bin/env bash
# Generate tests for uncovered behavior matrix cells using LLM.
#
# Usage: ai-matrix-test.sh [--mode MODE] [--dry-run] [--limit N]
# See docs/ai-testing.md for backend configuration.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

die() { echo "ERROR: $*" >&2; exit 1; }

# shellcheck source=scripts/ai-config.sh
source "$SCRIPT_DIR/ai-config.sh"

# ── Configuration ─────────────────────────────────────────
MATRIX_FILE="tests/behavior_matrix.yml"
LIMIT="${ANKLUME_MATRIX_LIMIT:-10}"

# ── Usage ─────────────────────────────────────────────────
usage() {
    cat <<'USAGE'
Usage: ai-matrix-test.sh [options]

Generate tests for uncovered behavior matrix cells using an LLM backend.

Options:
  -h, --help       Show this help
  --mode MODE      Override AI_MODE (none, local, remote, claude-code, aider)
  --dry-run        Show what would be generated (default)
  --no-dry-run     Actually write generated tests
  --limit N        Max cells to process (default: 10)

Environment:
  ANKLUME_AI_MODE          AI backend (default: none)
  ANKLUME_AI_DRY_RUN       Dry-run mode (default: true)
  ANKLUME_MATRIX_LIMIT     Max cells to process (default: 10)

Examples:
  ai-matrix-test.sh                            # Show uncovered cells
  ai-matrix-test.sh --mode local --no-dry-run  # Generate with Ollama
  ai-matrix-test.sh --mode claude-code         # Generate with Claude Code
USAGE
}

# ── Find uncovered cells ──────────────────────────────────
find_uncovered_cells() {
    # Parse the matrix and coverage to find uncovered cell IDs.
    python3 -c "
import yaml, re, sys
from pathlib import Path

# Load matrix
with open('${MATRIX_FILE}') as f:
    data = yaml.safe_load(f)

all_ids = []
cell_map = {}
for cap_key, cap in (data.get('capabilities') or {}).items():
    for depth in ('depth_1', 'depth_2', 'depth_3'):
        for item in cap.get(depth) or []:
            cid = item.get('id')
            if cid:
                all_ids.append(cid)
                cell_map[cid] = {
                    'capability': cap_key,
                    'description': cap.get('description', ''),
                    'depth': depth,
                    'action': item.get('action', ''),
                    'expected': item.get('expected', ''),
                }

# Scan for covered IDs
covered = set()
ref_re = re.compile(r'#\s*Matrix:\s*([\w-]+(?:,\s*[\w-]+)*)')
for pattern in ['tests/*.py', 'roles/*/molecule/*/verify.yml']:
    for fp in sorted(Path('.').glob(pattern)):
        for m in ref_re.finditer(fp.read_text()):
            for ref in m.group(1).split(','):
                covered.add(ref.strip())

# Output uncovered cells as lines: ID|capability|depth|action|expected
for cid in all_ids:
    if cid not in covered:
        c = cell_map[cid]
        print(f\"{cid}|{c['capability']}|{c['depth']}|{c['action']}|{c['expected']}\")
" 2>/dev/null
}

# ── Build context for LLM ────────────────────────────────
build_cell_context() {
    local cell_id="$1"
    local capability="$2"
    local depth="$3"
    local action="$4"
    local expected="$5"
    local context_file="$6"

    {
        echo "=== Behavior Matrix Cell: ${cell_id} ==="
        echo "Capability: ${capability}"
        echo "Depth: ${depth}"
        echo "Action: ${action}"
        echo "Expected: ${expected}"
        echo ""
        echo "=== Project conventions (from CLAUDE.md) ==="
        echo "- Python: ruff clean, line-length 120, Python 3.11+"
        echo "- Tests use pytest with fixtures from conftest or inline"
        echo "- Generator is at scripts/generate.py with functions: validate, generate, detect_orphans, get_warnings, enrich_infra, load_infra"
        echo "- MANAGED_BEGIN / MANAGED_END markers in generated files"
        echo ""
        echo "=== Existing test patterns ==="
        # Show first few test methods as examples
        head -60 tests/test_generate.py 2>/dev/null || true
        echo ""
        echo "=== Relevant SPEC sections ==="
        # Extract relevant section based on capability
        case "$capability" in
            domain_lifecycle|psot_generator)
                sed -n '/## 5\. infra.yml format/,/## 6\./p' docs/SPEC.md 2>/dev/null | head -80
                ;;
            gpu_policy)
                sed -n '/## ADR-018/,/## ADR-019/p' docs/ARCHITECTURE.md 2>/dev/null | head -40
                ;;
            network_policies)
                sed -n '/### Network policies/,/### infra.yml as a directory/p' docs/SPEC.md 2>/dev/null | head -50
                ;;
            privileged_policy)
                sed -n '/## ADR-020/,/## ADR-021/p' docs/ARCHITECTURE.md 2>/dev/null | head -40
                ;;
            firewall_modes)
                sed -n '/## ADR-024/,/## ADR-026/p' docs/ARCHITECTURE.md 2>/dev/null | head -40
                ;;
            *)
                echo "(no specific SPEC section for ${capability})"
                ;;
        esac
    } > "$context_file"
}

# ── Generate test for a cell ─────────────────────────────
generate_test_for_cell() {
    local cell_id="$1"
    local capability="$2"
    local depth="$3"
    local action="$4"
    local expected="$5"

    # shellcheck disable=SC2154  # _ai_session_id set by ai_init_session in ai-config.sh
    local context_file="${AI_LOG_DIR}/${_ai_session_id}-${cell_id}-context.txt"

    build_cell_context "$cell_id" "$capability" "$depth" "$action" "$expected" "$context_file"

    local instruction
    instruction="Generate a pytest test function for this behavior matrix cell.
The test should:
1. Import from generate (validate, generate, detect_orphans, get_warnings, enrich_infra, load_infra, MANAGED_BEGIN, MANAGED_END)
2. Use the sample_infra fixture pattern (dict with project_name, global, domains)
3. Include '# Matrix: ${cell_id}' comment on the def line
4. Test: ${action}
5. Assert: ${expected}
Return ONLY the Python function code, no imports or class wrapper."

    case "$AI_MODE" in
        none)
            ai_log "AI_MODE=none: showing uncovered cell ${cell_id}: ${action}"
            return 1
            ;;
        local)
            ai_fix_ollama "$context_file" "$instruction" && return 0
            ;;
        remote)
            ai_fix_remote "$context_file" "$instruction" && return 0
            ;;
        claude-code)
            ai_fix_claude_code "$context_file" "$instruction" && return 0
            ;;
        aider)
            ai_fix_aider "$context_file" "$instruction" && return 0
            ;;
    esac
    return 1
}

# ── Validate generated test ──────────────────────────────
validate_generated_test() {
    local test_file="$1"
    if [ ! -s "$test_file" ]; then
        ai_log "WARNING: Empty test file"
        return 1
    fi
    if python3 -c "import ast; ast.parse(open('${test_file}').read())" 2>/dev/null; then
        ai_log "Generated test is valid Python"
        return 0
    else
        ai_log "WARNING: Generated test has syntax errors"
        return 1
    fi
}

# ── Main ──────────────────────────────────────────────────
main() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -h|--help) usage; exit 0 ;;
            --mode) AI_MODE="$2"; shift 2 ;;
            --dry-run) AI_DRY_RUN="true"; shift ;;
            --no-dry-run) AI_DRY_RUN="false"; export AI_DRY_RUN; shift ;;
            --limit) LIMIT="$2"; shift 2 ;;
            -*) die "Unknown option: $1" ;;
            *) die "Unexpected argument: $1" ;;
        esac
    done

    ai_validate_config
    ai_init_session "matrix"

    if [ ! -f "$MATRIX_FILE" ]; then
        die "Behavior matrix not found: ${MATRIX_FILE}"
    fi

    ai_log "Finding uncovered matrix cells..."
    local uncovered
    uncovered="$(find_uncovered_cells)"

    local total
    total="$(echo "$uncovered" | grep -c . || true)"
    ai_log "Uncovered cells: ${total}"

    if [ "$total" -eq 0 ]; then
        ai_log "All matrix cells are covered!"
        return 0
    fi

    local processed=0
    local generated=0

    while IFS='|' read -r cell_id capability depth action expected; do
        if [ "$processed" -ge "$LIMIT" ]; then
            ai_log "Limit reached (${LIMIT}). Remaining cells skipped."
            break
        fi

        ai_log "Processing ${cell_id}: ${action}"

        if generate_test_for_cell "$cell_id" "$capability" "$depth" "$action" "$expected"; then
            generated=$((generated + 1))
        fi

        processed=$((processed + 1))
    done <<< "$uncovered"

    ai_log ""
    ai_log "===== Matrix Test Generation ====="
    ai_log "Processed: ${processed}"
    ai_log "Generated: ${generated}"
    ai_log "Remaining: $((total - processed))"
    # shellcheck disable=SC2154  # _ai_log_file set by ai_init_session in ai-config.sh
    ai_log "Session log: ${_ai_log_file}"
}

main "$@"
