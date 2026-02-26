#!/usr/bin/env bash
# scripts/test-summary.sh — Unified test report across all test layers
#
# Runs each test layer and produces a combined summary table.
# Layers that are unavailable (missing tools) are marked SKIP.
#
# Usage:
#   scripts/test-summary.sh            # run all layers
#   scripts/test-summary.sh --quick    # skip slow layers (chains)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

QUICK=false
if [[ "${1:-}" == "--quick" ]]; then
    QUICK=true
fi

# Collect results: layer, status, count, duration
declare -a LAYERS=()
declare -a STATUSES=()
declare -a COUNTS=()
declare -a DURATIONS=()
OVERALL="PASS"

run_layer() {
    local name="$1"
    local cmd="$2"
    local start duration rc output count status

    start=$(date +%s%N)
    rc=0
    output=$(eval "$cmd" 2>&1) || rc=$?
    duration=$(( ($(date +%s%N) - start) / 1000000 ))
    local dur_s
    dur_s=$(awk "BEGIN {printf \"%.1f\", $duration/1000}")

    if [[ $rc -eq 0 ]]; then
        status="PASS"
    else
        status="FAIL"
        OVERALL="FAIL"
    fi

    # Extract count from output (layer-specific parsing)
    count="$3"
    case "$name" in
        "pytest")
            local passed failed
            passed=$(echo "$output" | grep -oP '\d+ passed' | grep -oP '\d+' || echo "0")
            failed=$(echo "$output" | grep -oP '\d+ failed' | grep -oP '\d+' || echo "0")
            total=$((passed + failed))
            count="${passed}/${total}"
            ;;
        "behave scenarios")
            local bp bf bs
            bp=$(echo "$output" | grep -oP '\d+ scenarios? passed' | grep -oP '^\d+' || echo "0")
            bf=$(echo "$output" | grep -oP '\d+ failed' | head -1 | grep -oP '^\d+' || echo "0")
            bs=$(echo "$output" | grep -oP '\d+ skipped' | head -1 | grep -oP '^\d+' || echo "0")
            total=$((bp + bf + bs))
            count="${bp}/${total}"
            # Skipped scenarios are not failures
            if [[ "$bf" == "0" ]]; then
                status="PASS"
                if [[ "$OVERALL" == "FAIL" ]] && [[ "$rc" -ne 0 ]]; then
                    : # keep FAIL if other layers failed
                fi
            fi
            ;;
        "behavioral chains")
            local cp ct
            cp=$(echo "$output" | grep -oP '\d+/\d+ chains passed' | head -1 || echo "")
            if [[ -n "$cp" ]]; then
                count="$cp"
                count="${count/ chains passed/}"
            fi
            ;;
        "matrix coverage")
            local pct
            pct=$(echo "$output" | grep -oP '\d+%' | tail -1 || echo "?%")
            count="$pct"
            status="$pct"
            ;;
        "hypothesis")
            local hp hf
            hp=$(echo "$output" | grep -oP '\d+ passed' | grep -oP '\d+' || echo "0")
            hf=$(echo "$output" | grep -oP '\d+ failed' | grep -oP '\d+' || echo "0")
            total=$((hp + hf))
            count="${hp}/${total}"
            ;;
    esac

    LAYERS+=("$name")
    STATUSES+=("$status")
    COUNTS+=("$count")
    DURATIONS+=("${dur_s}s")
}

skip_layer() {
    local name="$1"
    local reason="$2"
    LAYERS+=("$name")
    STATUSES+=("SKIP")
    COUNTS+=("$reason")
    DURATIONS+=("-")
}

echo "Running test layers..."
echo ""

# Layer 1: pytest
if command -v python3 >/dev/null 2>&1 && python3 -c "import pytest" 2>/dev/null; then
    run_layer "pytest" "python3 -m pytest tests/ -x -q --tb=no 2>&1" ""
else
    skip_layer "pytest" "pytest not installed"
fi

# Layer 2: behave scenarios
if command -v python3 >/dev/null 2>&1 && python3 -c "import behave" 2>/dev/null; then
    run_layer "behave scenarios" "python3 -m behave scenarios/ --no-capture 2>&1" ""
else
    skip_layer "behave scenarios" "behave not installed"
fi

# Layer 3: behavioral chains (slow — skip in quick mode)
if [[ "$QUICK" == "true" ]]; then
    skip_layer "behavioral chains" "skipped (--quick)"
elif [[ -f scripts/run-behavioral-tests.py ]]; then
    run_layer "behavioral chains" "python3 scripts/run-behavioral-tests.py 2>&1" ""
else
    skip_layer "behavioral chains" "runner not found"
fi

# Layer 4: matrix coverage
if [[ -f scripts/matrix-coverage.py ]]; then
    run_layer "matrix coverage" "python3 scripts/matrix-coverage.py 2>&1" ""
else
    skip_layer "matrix coverage" "script not found"
fi

# Layer 5: hypothesis (subset of pytest)
if command -v python3 >/dev/null 2>&1 && python3 -c "import hypothesis" 2>/dev/null; then
    run_layer "hypothesis" "python3 -m pytest tests/test_properties.py -x -q --tb=no 2>&1" ""
else
    skip_layer "hypothesis" "hypothesis not installed"
fi

# Print summary table
echo ""
echo "======================================================================"
printf "%-22s | %-6s | %-12s | %s\n" "Test Layer" "Status" "Count" "Duration"
echo "--------------------------------------------------------------------"
for i in "${!LAYERS[@]}"; do
    printf "%-22s | %-6s | %-12s | %s\n" \
        "${LAYERS[$i]}" "${STATUSES[$i]}" "${COUNTS[$i]}" "${DURATIONS[$i]}"
done
echo "--------------------------------------------------------------------"
printf "%-22s | %-6s |\n" "OVERALL" "$OVERALL"
echo "======================================================================"

if [[ "$OVERALL" == "FAIL" ]]; then
    exit 1
fi
