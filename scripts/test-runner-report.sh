#!/usr/bin/env bash
# test-runner-report.sh — Comprehensive test runner with JSON reports.
#
# Runs all test suites (pytest, lint, matrix-coverage, shellcheck) and
# produces structured JSON reports for delegation to Ada or other agents.
#
# Usage:
#   scripts/test-runner-report.sh [--output-dir DIR] [--suite SUITE]
#
# Options:
#   --output-dir DIR   Directory for report files (default: /tmp/anklume-test-report)
#   --suite SUITE      Run only one suite: pytest|lint|matrix|shellcheck|ruff
#                      (default: all suites)
#
# Output files:
#   progress.json   — Real-time progress (updated after each suite)
#   report.json     — Final structured report with all results
#
# Exit codes:
#   0 — All suites passed
#   1 — One or more suites failed
#   2 — Script error (bad arguments, missing tools)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
OUTPUT_DIR="/tmp/anklume-test-report"
SUITE_FILTER=""

# ── Argument parsing ──────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --output-dir) OUTPUT_DIR="$2"; shift 2 ;;
        --suite)      SUITE_FILTER="$2"; shift 2 ;;
        -h|--help)
            sed -n '2,/^$/p' "$0" | sed 's/^# \?//'
            exit 0
            ;;
        *) echo "ERROR: unknown argument: $1" >&2; exit 2 ;;
    esac
done

mkdir -p "$OUTPUT_DIR"

PROGRESS_FILE="$OUTPUT_DIR/progress.json"
REPORT_FILE="$OUTPUT_DIR/report.json"
START_TIME=$(date +%s)
START_ISO=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# ── Helpers ───────────────────────────────────────────────

update_progress() {
    local current_suite="$1"
    local completed="$2"
    local total="$3"
    local status="$4"
    local pct=$(( completed * 100 / total ))
    python3 - "$START_ISO" "$current_suite" "$completed" "$total" "$pct" "$status" <<'PYEOF'
import json, sys
started, suite, done, tot, pct, status = sys.argv[1:7]
json.dump({
    "started_at": started,
    "current_suite": suite,
    "suites_completed": int(done),
    "suites_total": int(tot),
    "percent": int(pct),
    "status": status,
}, open(sys.argv[0].replace(sys.argv[1], "").rstrip() or "/dev/null", "w"), indent=2)
PYEOF
    # Simpler approach: just write directly
    cat > "$PROGRESS_FILE" <<EOF
{
  "started_at": "$START_ISO",
  "current_suite": "$current_suite",
  "suites_completed": $completed,
  "suites_total": $total,
  "percent": $pct,
  "status": "$status"
}
EOF
}

# Parse pytest verbose output into JSON array of failures
parse_pytest_failures() {
    local log_file="$1"
    python3 - "$log_file" <<'PYEOF'
import json, re, sys

log_file = sys.argv[1]
failures = []
try:
    with open(log_file) as f:
        content = f.read()
except FileNotFoundError:
    print("[]")
    sys.exit(0)

# Parse FAILED lines: "FAILED tests/test_foo.py::TestBar::test_baz - AssertionError: ..."
for m in re.finditer(r'FAILED\s+(\S+?)(?:\s+-\s+(.+))?$', content, re.MULTILINE):
    test_path = m.group(1)
    message = m.group(2) or ""
    # Extract file and line from path
    parts = test_path.split("::")
    file_path = parts[0] if parts else test_path
    failures.append({
        "test": test_path,
        "message": message,
        "file": file_path,
    })

# Parse ERROR lines: "ERROR tests/test_foo.py - ImportError: ..."
for m in re.finditer(r'ERROR\s+(\S+?)(?:\s+-\s+(.+))?$', content, re.MULTILINE):
    test_path = m.group(1)
    message = m.group(2) or ""
    parts = test_path.split("::")
    file_path = parts[0] if parts else test_path
    failures.append({
        "test": test_path,
        "message": message,
        "file": file_path,
        "error": True,
    })

print(json.dumps(failures))
PYEOF
}

# Parse pytest summary line: "X passed, Y failed, Z errors, W skipped"
parse_pytest_summary() {
    local log_file="$1"
    python3 - "$log_file" <<'PYEOF'
import json, re, sys

log_file = sys.argv[1]
result = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0, "total": 0}
try:
    with open(log_file) as f:
        content = f.read()
except FileNotFoundError:
    print(json.dumps(result))
    sys.exit(0)

# Match the summary line: "= 120 passed, 5 failed, 2 errors, 1 skipped in 12.34s ="
# or "= 120 passed in 12.34s ="
summary_match = re.search(r'=+\s+(.*?)\s+in\s+[\d.]+s\s+=+', content)
if summary_match:
    summary = summary_match.group(1)
    for key in ["passed", "failed", "errors", "error", "skipped", "warnings", "warning"]:
        m = re.search(rf'(\d+)\s+{key}', summary)
        if m:
            canonical = key.rstrip("s") if key.endswith("s") and key != "errors" else key
            if canonical == "error":
                canonical = "errors"
            if canonical == "warning":
                canonical = "warnings"
            if canonical in result:
                result[canonical] = int(m.group(1))

result["total"] = result["passed"] + result["failed"] + result["errors"] + result["skipped"]
print(json.dumps(result))
PYEOF
}

# Parse matrix-coverage output
parse_matrix_coverage() {
    local log_file="$1"
    python3 - "$log_file" <<'PYEOF'
import json, re, sys

log_file = sys.argv[1]
result = {"coverage_percent": 0, "total_cells": 0, "covered_cells": 0, "uncovered_by_capability": {}}
try:
    with open(log_file) as f:
        content = f.read()
except FileNotFoundError:
    print(json.dumps(result))
    sys.exit(0)

# Parse TOTAL line: "TOTAL    120   58   48%"
total_match = re.search(r'TOTAL\s+(\d+)\s+(\d+)\s+(\d+)%', content)
if total_match:
    result["total_cells"] = int(total_match.group(1))
    result["covered_cells"] = int(total_match.group(2))
    result["coverage_percent"] = int(total_match.group(3))

# Parse per-capability lines
for m in re.finditer(r'(\S+)\s+(depth\s*\d)\s+(\d+)\s+(\d+)\s+(\d+)%', content):
    cap = m.group(1)
    depth = m.group(2).replace(" ", "_")
    total = int(m.group(3))
    covered = int(m.group(4))
    uncovered = total - covered
    if uncovered > 0:
        if cap not in result["uncovered_by_capability"]:
            result["uncovered_by_capability"][cap] = {}
        result["uncovered_by_capability"][cap][depth] = {
            "total": total, "covered": covered, "uncovered": uncovered
        }

print(json.dumps(result))
PYEOF
}

# Count lint issues from output
parse_lint_output() {
    local log_file="$1"
    local linter="$2"
    python3 - "$log_file" "$linter" <<'PYEOF'
import json, re, sys

log_file, linter = sys.argv[1], sys.argv[2]
issues = []
try:
    with open(log_file) as f:
        content = f.read()
except FileNotFoundError:
    print(json.dumps({"count": 0, "issues": []}))
    sys.exit(0)

# Extract first 20 issue lines (file:line patterns)
for line in content.strip().split("\n")[:20]:
    line = line.strip()
    if not line or line.startswith("=") or line.startswith("-"):
        continue
    # Match common patterns: file.py:42:10: E501 or file.yml:3: [error] ...
    if re.match(r'\S+:\d+', line):
        issues.append(line[:200])

print(json.dumps({"count": len(issues), "issues": issues}))
PYEOF
}


# ── Suite definitions ─────────────────────────────────────

declare -A SUITE_NAMES
SUITE_NAMES=(
    [pytest]="Unit Tests (pytest)"
    [lint]="Linters (ansible-lint + yamllint)"
    [ruff]="Python Lint (ruff)"
    [shellcheck]="Shell Lint (shellcheck)"
    [matrix]="Behavior Matrix Coverage"
)

# Order of execution
ALL_SUITES=(pytest lint ruff shellcheck matrix)

# Filter suites if --suite specified
if [[ -n "$SUITE_FILTER" ]]; then
    if [[ -z "${SUITE_NAMES[$SUITE_FILTER]+_}" ]]; then
        echo "ERROR: unknown suite '$SUITE_FILTER'. Valid: ${!SUITE_NAMES[*]}" >&2
        exit 2
    fi
    ALL_SUITES=("$SUITE_FILTER")
fi

TOTAL_SUITES=${#ALL_SUITES[@]}
COMPLETED=0

# Initialize results array (built up as suites complete)
SUITE_RESULTS=()
OVERALL_STATUS="passed"

# ── Run suites ────────────────────────────────────────────

run_suite_pytest() {
    local log="$OUTPUT_DIR/pytest.log"
    update_progress "pytest" "$COMPLETED" "$TOTAL_SUITES" "running"

    local suite_start
    suite_start=$(date +%s)
    local exit_code=0
    python3 -m pytest tests/ -v --tb=short > "$log" 2>&1 || exit_code=$?
    local suite_end
    suite_end=$(date +%s)
    local duration=$(( suite_end - suite_start ))

    local summary
    summary=$(parse_pytest_summary "$log")
    local failures
    failures=$(parse_pytest_failures "$log")

    local status="passed"
    local failed_count
    failed_count=$(echo "$summary" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['failed']+d['errors'])")
    if [[ "$failed_count" -gt 0 ]]; then
        status="failed"
        OVERALL_STATUS="failed"
    fi

    local result
    result=$(python3 - "$status" "$duration" "$summary" "$failures" <<'PYEOF'
import json, sys
status, dur = sys.argv[1], int(sys.argv[2])
summary = json.loads(sys.argv[3])
failures = json.loads(sys.argv[4])
print(json.dumps({
    "name": "pytest",
    "display_name": "Unit Tests (pytest)",
    "status": status,
    "duration_seconds": dur,
    "tests_total": summary["total"],
    "tests_passed": summary["passed"],
    "tests_failed": summary["failed"],
    "tests_errors": summary["errors"],
    "tests_skipped": summary["skipped"],
    "failures": failures,
}))
PYEOF
)
    SUITE_RESULTS+=("$result")
    COMPLETED=$((COMPLETED + 1))
    echo "  pytest: $status (${failed_count} failures, ${duration}s)"
}

run_suite_lint() {
    local log="$OUTPUT_DIR/lint.log"
    update_progress "lint" "$COMPLETED" "$TOTAL_SUITES" "running"

    local suite_start
    suite_start=$(date +%s)
    local exit_code=0

    # Run ansible-lint + yamllint combined
    {
        echo "=== ansible-lint ==="
        ansible-lint 2>&1 || true
        echo ""
        echo "=== yamllint ==="
        yamllint . 2>&1 || true
    } > "$log" 2>&1 || exit_code=$?
    local suite_end
    suite_end=$(date +%s)
    local duration=$(( suite_end - suite_start ))

    local lint_data
    lint_data=$(parse_lint_output "$log" "lint")
    local issue_count
    issue_count=$(echo "$lint_data" | python3 -c "import json,sys; print(json.load(sys.stdin)['count'])")

    local status="passed"
    if [[ "$issue_count" -gt 0 ]]; then
        status="failed"
        OVERALL_STATUS="failed"
    fi

    local result
    result=$(python3 - "$status" "$duration" "$lint_data" <<'PYEOF'
import json, sys
status, dur = sys.argv[1], int(sys.argv[2])
lint = json.loads(sys.argv[3])
print(json.dumps({
    "name": "lint",
    "display_name": "Linters (ansible-lint + yamllint)",
    "status": status,
    "duration_seconds": dur,
    "issue_count": lint["count"],
    "issues": lint["issues"],
}))
PYEOF
)
    SUITE_RESULTS+=("$result")
    COMPLETED=$((COMPLETED + 1))
    echo "  lint: $status (${issue_count} issues, ${duration}s)"
}

run_suite_ruff() {
    local log="$OUTPUT_DIR/ruff.log"
    update_progress "ruff" "$COMPLETED" "$TOTAL_SUITES" "running"

    local suite_start
    suite_start=$(date +%s)
    local exit_code=0
    ruff check . > "$log" 2>&1 || exit_code=$?
    local suite_end
    suite_end=$(date +%s)
    local duration=$(( suite_end - suite_start ))

    local lint_data
    lint_data=$(parse_lint_output "$log" "ruff")
    local issue_count
    issue_count=$(echo "$lint_data" | python3 -c "import json,sys; print(json.load(sys.stdin)['count'])")

    local status="passed"
    if [[ "$exit_code" -ne 0 ]]; then
        status="failed"
        OVERALL_STATUS="failed"
    fi

    local result
    result=$(python3 - "$status" "$duration" "$lint_data" <<'PYEOF'
import json, sys
status, dur = sys.argv[1], int(sys.argv[2])
lint = json.loads(sys.argv[3])
print(json.dumps({
    "name": "ruff",
    "display_name": "Python Lint (ruff)",
    "status": status,
    "duration_seconds": dur,
    "issue_count": lint["count"],
    "issues": lint["issues"],
}))
PYEOF
)
    SUITE_RESULTS+=("$result")
    COMPLETED=$((COMPLETED + 1))
    echo "  ruff: $status (${issue_count} issues, ${duration}s)"
}

run_suite_shellcheck() {
    local log="$OUTPUT_DIR/shellcheck.log"
    update_progress "shellcheck" "$COMPLETED" "$TOTAL_SUITES" "running"

    local suite_start
    suite_start=$(date +%s)
    local exit_code=0
    # shellcheck all .sh files in scripts/ and host/
    find "$PROJECT_DIR/scripts" "$PROJECT_DIR/host" -name '*.sh' -print0 2>/dev/null \
        | xargs -0 shellcheck 2>&1 > "$log" || exit_code=$?
    local suite_end
    suite_end=$(date +%s)
    local duration=$(( suite_end - suite_start ))

    local lint_data
    lint_data=$(parse_lint_output "$log" "shellcheck")
    local issue_count
    issue_count=$(echo "$lint_data" | python3 -c "import json,sys; print(json.load(sys.stdin)['count'])")

    local status="passed"
    if [[ "$exit_code" -ne 0 ]]; then
        status="failed"
        OVERALL_STATUS="failed"
    fi

    local result
    result=$(python3 - "$status" "$duration" "$lint_data" <<'PYEOF'
import json, sys
status, dur = sys.argv[1], int(sys.argv[2])
lint = json.loads(sys.argv[3])
print(json.dumps({
    "name": "shellcheck",
    "display_name": "Shell Lint (shellcheck)",
    "status": status,
    "duration_seconds": dur,
    "issue_count": lint["count"],
    "issues": lint["issues"],
}))
PYEOF
)
    SUITE_RESULTS+=("$result")
    COMPLETED=$((COMPLETED + 1))
    echo "  shellcheck: $status (${issue_count} issues, ${duration}s)"
}

run_suite_matrix() {
    local log="$OUTPUT_DIR/matrix.log"
    update_progress "matrix" "$COMPLETED" "$TOTAL_SUITES" "running"

    local suite_start
    suite_start=$(date +%s)
    local exit_code=0
    python3 scripts/matrix-coverage.py > "$log" 2>&1 || exit_code=$?
    local suite_end
    suite_end=$(date +%s)
    local duration=$(( suite_end - suite_start ))

    local matrix_data
    matrix_data=$(parse_matrix_coverage "$log")
    local coverage
    coverage=$(echo "$matrix_data" | python3 -c "import json,sys; print(json.load(sys.stdin)['coverage_percent'])")

    # Matrix is informational, never fails the overall status
    local result
    result=$(python3 - "$duration" "$matrix_data" <<'PYEOF'
import json, sys
dur = int(sys.argv[1])
matrix = json.loads(sys.argv[2])
print(json.dumps({
    "name": "matrix",
    "display_name": "Behavior Matrix Coverage",
    "status": "info",
    "duration_seconds": dur,
    "coverage_percent": matrix["coverage_percent"],
    "total_cells": matrix["total_cells"],
    "covered_cells": matrix["covered_cells"],
    "uncovered_by_capability": matrix["uncovered_by_capability"],
}))
PYEOF
)
    SUITE_RESULTS+=("$result")
    COMPLETED=$((COMPLETED + 1))
    echo "  matrix: ${coverage}% coverage (${duration}s)"
}


# ── Main ──────────────────────────────────────────────────

cd "$PROJECT_DIR"
echo "AnKLuMe Test Runner — $(date -u +"%Y-%m-%d %H:%M UTC")"
echo "Output: $OUTPUT_DIR"
echo "Suites: ${ALL_SUITES[*]}"
echo ""

for suite in "${ALL_SUITES[@]}"; do
    "run_suite_$suite"
done

END_TIME=$(date +%s)
TOTAL_DURATION=$(( END_TIME - START_TIME ))

update_progress "done" "$COMPLETED" "$TOTAL_SUITES" "$OVERALL_STATUS"

# ── Build final report ────────────────────────────────────

# Join suite results into a JSON array
SUITES_JSON="["
for i in "${!SUITE_RESULTS[@]}"; do
    if [[ $i -gt 0 ]]; then
        SUITES_JSON+=","
    fi
    SUITES_JSON+="${SUITE_RESULTS[$i]}"
done
SUITES_JSON+="]"

python3 - "$START_ISO" "$TOTAL_DURATION" "$OVERALL_STATUS" "$SUITES_JSON" "$REPORT_FILE" <<'PYEOF'
import json, sys

started = sys.argv[1]
duration = int(sys.argv[2])
status = sys.argv[3]
suites = json.loads(sys.argv[4])
output_file = sys.argv[5]

# Build summary from suites
total_tests = 0
total_passed = 0
total_failed = 0
total_errors = 0
total_skipped = 0
passed_suites = 0
failed_suites = 0

for s in suites:
    if s["status"] == "passed":
        passed_suites += 1
    elif s["status"] == "failed":
        failed_suites += 1
    # Aggregate test counts (pytest suite has these)
    total_tests += s.get("tests_total", 0)
    total_passed += s.get("tests_passed", 0)
    total_failed += s.get("tests_failed", 0)
    total_errors += s.get("tests_errors", 0)
    total_skipped += s.get("tests_skipped", 0)

report = {
    "timestamp": started,
    "duration_seconds": duration,
    "overall_status": status,
    "summary": {
        "total_suites": len(suites),
        "passed_suites": passed_suites,
        "failed_suites": failed_suites,
        "total_tests": total_tests,
        "passed": total_passed,
        "failed": total_failed,
        "errors": total_errors,
        "skipped": total_skipped,
    },
    "suites": suites,
}

with open(output_file, "w") as f:
    json.dump(report, f, indent=2)

# Also print a human-readable summary
print("")
print(f"{'=' * 60}")
print(f"  RESULT: {status.upper()}")
print(f"  Duration: {duration}s")
print(f"  Suites: {passed_suites} passed, {failed_suites} failed")
if total_tests > 0:
    print(f"  Tests:  {total_passed} passed, {total_failed} failed, {total_errors} errors, {total_skipped} skipped")
print(f"  Report: {output_file}")
print(f"{'=' * 60}")
PYEOF

if [[ "$OVERALL_STATUS" == "failed" ]]; then
    exit 1
fi
exit 0
