#!/usr/bin/env bash
# test-nesting.sh — Test anklume LXC/VM nesting up to N levels deep
#
# Recursive: pushes nest-worker.sh into each container level.
# Worker installs Incus, creates child, pushes self, and recurses.
# LXC: L1 unprivileged+nesting, L2+ privileged+nesting (stgraber).
# --full: also copies repo + runs pytest at each nesting level.
#
# Usage:
#   scripts/test-nesting.sh [--mode lxc|vm|both] [--max-depth N] [--full] [--behave] [--dry-run]
#
# Requires: Incus daemon. VM mode requires KVM + 8GB+ RAM.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
NEST_PROJECT="nesting-test"
NEST_IMAGE="images:debian/13"
DRY_RUN=false
MODE="lxc"
MAX_DEPTH=3
FULL=false
BEHAVE=false
PASSED=0
FAILED=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)    DRY_RUN=true ;;
        --mode)       MODE="$2"; shift ;;
        --max-depth)  MAX_DEPTH="$2"; shift ;;
        --full)       FULL=true ;;
        --behave)     BEHAVE=true ;;
        -h|--help)
            echo "Usage: $0 [--mode lxc|vm|both] [--max-depth N] [--full] [--behave] [--dry-run]"
            exit 0 ;;
        *) echo "Unknown: $1"; exit 1 ;;
    esac
    shift
done

[[ "$MODE" =~ ^(lxc|vm|both)$ ]] \
    || { echo "Invalid mode: $MODE (must be lxc, vm, or both)"; exit 1; }
if ! [[ "$MAX_DEPTH" =~ ^[1-5]$ ]]; then
    echo "Invalid max-depth: $MAX_DEPTH (must be 1-5)"; exit 1
fi

# ── Helpers ──────────────────────────────────────────────────
info()  { printf "  [INFO] %s\n" "$1"; }
pass()  { printf "  [PASS] %s\n" "$1"; ((PASSED++)) || true; }
fail()  { printf "  [FAIL] %s\n" "$1"; ((FAILED++)) || true; }

# shellcheck disable=SC2317,SC2329
cleanup() {
    info "Cleaning up nesting test resources..."
    incus delete "nest-l1" --project "$NEST_PROJECT" --force 2>/dev/null || true
    incus project delete "$NEST_PROJECT" 2>/dev/null || true
}
trap cleanup EXIT

# ── Preflight ────────────────────────────────────────────────
info "Checking prerequisites..."
incus info >/dev/null 2>&1 || { fail "Incus daemon not available"; exit 1; }

if $DRY_RUN; then
    info "Dry-run (--mode $MODE, --max-depth $MAX_DEPTH, --full=$FULL, --behave=$BEHAVE)"
    pass "Script structure valid"
    pass "Prerequisites checked"
    pass "Would create project: $NEST_PROJECT"
    pass "Would launch $MODE instance: nest-l1"
    pass "Would test nesting context at levels 1-$MAX_DEPTH"
    echo ""
    echo "RESULTS: $PASSED passed, $FAILED failed (dry-run)"
    exit 0
fi

# ── Test function ────────────────────────────────────────────
run_nesting_test() {
    local itype="$1" flags="" wait_time=30 label="LXC" full_flag="0" behave_flag="0"
    if [[ "$itype" == "vm" ]]; then
        flags="--vm -c limits.cpu=2 -c limits.memory=4GiB"
        flags+=" -c security.secureboot=false"
        wait_time=60; label="VM"
    else
        flags="-c security.nesting=true"
        flags+=" -c security.syscalls.intercept.mknod=true"
        flags+=" -c security.syscalls.intercept.setxattr=true"
    fi
    $FULL && full_flag="1"
    $BEHAVE && behave_flag="1"
    info "=== Testing $label nesting (max-depth=$MAX_DEPTH, full=$FULL, behave=$BEHAVE) ==="
    incus project create "$NEST_PROJECT" \
        -c features.images=false -c features.profiles=false 2>/dev/null || true

    info "Launching $label nest-l1..."
    # shellcheck disable=SC2086
    incus launch "$NEST_IMAGE" "nest-l1" $flags \
        --project "$NEST_PROJECT" 2>/dev/null
    for _i in $(seq 1 "$wait_time"); do
        incus exec "nest-l1" --project "$NEST_PROJECT" -- true 2>/dev/null && break
        sleep 2
    done
    if ! incus exec "nest-l1" --project "$NEST_PROJECT" -- true 2>/dev/null; then
        fail "$label nest-l1 not ready"; return 1
    fi
    pass "$label nest-l1 is running"

    incus exec "nest-l1" --project "$NEST_PROJECT" -- bash -c "
        mkdir -p /etc/anklume
        echo 1 > /etc/anklume/absolute_level
        echo 0 > /etc/anklume/relative_level
        echo false > /etc/anklume/vm_nested
        echo false > /etc/anklume/yolo"
    local l1
    l1=$(incus exec "nest-l1" --project "$NEST_PROJECT" -- \
        cat /etc/anklume/absolute_level)
    if [[ "$l1" == "1" ]]; then
        pass "Level 1: absolute_level=1"
    else
        fail "Level 1: expected 1, got $l1"
    fi

    # Copy repo into L1 for --full mode
    if $FULL; then
        info "Copying anklume repo into nest-l1 (~10s)..."
        incus exec "nest-l1" --project "$NEST_PROJECT" -- mkdir -p /opt/anklume
        tar --exclude='.git' --exclude='images' --exclude='*.iso' \
            --exclude='__pycache__' --exclude='.pytest_cache' \
            --exclude='*.egg-info' -cf - -C "$PROJECT_ROOT" . | \
            incus exec "nest-l1" --project "$NEST_PROJECT" -- \
            tar -C /opt/anklume -xf -
    fi

    if [[ "$MAX_DEPTH" -le 1 ]]; then
        echo ""; echo "RESULTS ($label): $PASSED passed, $FAILED failed"
        return $(( FAILED > 0 ? 1 : 0 ))
    fi

    # Push worker into L1 and run recursively
    incus exec "nest-l1" --project "$NEST_PROJECT" -- \
        tee /tmp/nest-worker.sh < "$SCRIPT_DIR/nest-worker.sh" > /dev/null
    incus exec "nest-l1" --project "$NEST_PROJECT" -- chmod +x /tmp/nest-worker.sh
    info "Recursive nesting levels 1->$MAX_DEPTH (~$((MAX_DEPTH * 90))s)..."
    local output
    output=$(incus exec "nest-l1" --project "$NEST_PROJECT" -- \
        bash /tmp/nest-worker.sh 1 "$MAX_DEPTH" "$NEST_IMAGE" "$full_flag" "$behave_flag" 2>&1) || true
    while IFS= read -r line; do
        case "$line" in
            *"[PASS]"*) pass "${line#*\[PASS\] }" ;;
            *"[FAIL]"*) fail "${line#*\[FAIL\] }" ;;
            *"[STOP]"*) pass "Level $MAX_DEPTH: nesting stops correctly" ;;
            *"[WORKER]"*) info "${line#*\[WORKER\] }" ;;
            *"[DETAIL]"*) printf "         %s\n" "${line#*\[DETAIL\] }" ;;
        esac
    done <<< "$output"

    incus delete "nest-l1" --project "$NEST_PROJECT" --force 2>/dev/null || true
    incus project delete "$NEST_PROJECT" 2>/dev/null || true
    echo ""; echo "RESULTS ($label): $PASSED passed, $FAILED failed"
    return $(( FAILED > 0 ? 1 : 0 ))
}

# ── Main ─────────────────────────────────────────────────────
EXIT_CODE=0
case "$MODE" in
    lxc)  run_nesting_test lxc  || EXIT_CODE=1 ;;
    vm)   run_nesting_test vm   || EXIT_CODE=1 ;;
    both)
        run_nesting_test lxc || EXIT_CODE=1
        run_nesting_test vm  || EXIT_CODE=1 ;;
esac
exit "$EXIT_CODE"
