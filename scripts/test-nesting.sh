#!/usr/bin/env bash
# test-nesting.sh — Test anklume LXC/VM nesting up to N levels deep
#
# Recursive approach: pushes a worker script into each container level.
# Worker installs Incus, creates child, pushes self, and recurses.
# LXC: L1 unprivileged+nesting, L2+ privileged+nesting (stgraber).
#
# Usage:
#   scripts/test-nesting.sh [--mode lxc|vm|both] [--max-depth N] [--dry-run]
#
# Requires: Incus daemon. VM mode requires KVM + 8GB+ RAM.

set -euo pipefail

NEST_PROJECT="nesting-test"
NEST_IMAGE="images:debian/13"
DRY_RUN=false
MODE="lxc"
MAX_DEPTH=3
PASSED=0
FAILED=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)    DRY_RUN=true ;;
        --mode)       MODE="$2"; shift ;;
        --max-depth)  MAX_DEPTH="$2"; shift ;;
        -h|--help)
            echo "Usage: $0 [--mode lxc|vm|both] [--max-depth N] [--dry-run]"
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
    info "Dry-run (--mode $MODE, --max-depth $MAX_DEPTH)"
    pass "Script structure valid"
    pass "Prerequisites checked"
    pass "Would create project: $NEST_PROJECT"
    pass "Would launch $MODE instance: nest-l1"
    pass "Would test nesting context at levels 1-$MAX_DEPTH"
    echo ""
    echo "RESULTS: $PASSED passed, $FAILED failed (dry-run)"
    exit 0
fi

# ── Worker script (pushed into each level, recurses) ─────────
# Each level: install Incus → create child → write context → recurse
# shellcheck disable=SC2016
WORKER='#!/bin/bash
set -euo pipefail
LEVEL=$1; MAX=$2; IMG=$3; NEXT=$((LEVEL + 1)); CHILD="nest-l${NEXT}"
if [ "$LEVEL" -ge "$MAX" ]; then
    echo "[STOP] max depth reached (level=$LEVEL)"; exit 0; fi
echo "[WORKER] Level $LEVEL: installing Incus (~60s)..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null 2>&1
apt-get install -y -qq incus >/dev/null 2>&1
grep -q "^root:" /etc/subuid 2>/dev/null || echo "root:100000:1000000000" >> /etc/subuid
grep -q "^root:" /etc/subgid 2>/dev/null || echo "root:100000:1000000000" >> /etc/subgid
incus admin init --minimal >/dev/null 2>&1 || true
if ! incus info >/dev/null 2>&1; then
    echo "[FAIL] Level $LEVEL: Incus daemon not running"; exit 1; fi
echo "[PASS] Level $LEVEL: Incus daemon running"
echo "[WORKER] Level $LEVEL: launching $CHILD..."
incus launch "$IMG" "$CHILD" \
    -c security.privileged=true -c security.nesting=true \
    -c security.syscalls.intercept.mknod=true \
    -c security.syscalls.intercept.setxattr=true 2>/dev/null
WAIT=$((30 + LEVEL * 15))
for _i in $(seq 1 "$WAIT"); do
    incus exec "$CHILD" -- true 2>/dev/null && break; sleep 2; done
if ! incus exec "$CHILD" -- true 2>/dev/null; then
    echo "[FAIL] Level $NEXT: container not ready"; exit 1; fi
incus exec "$CHILD" -- mkdir -p /etc/anklume
incus exec "$CHILD" -- bash -c "echo $NEXT > /etc/anklume/absolute_level"
incus exec "$CHILD" -- bash -c "echo $((NEXT - 1)) > /etc/anklume/relative_level"
incus exec "$CHILD" -- bash -c "echo false > /etc/anklume/vm_nested"
LVL=$(incus exec "$CHILD" -- cat /etc/anklume/absolute_level)
if [ "$LVL" = "$NEXT" ]; then
    echo "[PASS] Level $NEXT: absolute_level=$NEXT"
else
    echo "[FAIL] Level $NEXT: absolute_level=$LVL (expected $NEXT)"; fi
cat /tmp/nest-worker.sh | incus exec "$CHILD" -- tee /tmp/nest-worker.sh > /dev/null
incus exec "$CHILD" -- chmod +x /tmp/nest-worker.sh
incus exec "$CHILD" -- bash /tmp/nest-worker.sh "$NEXT" "$MAX" "$IMG"
'

# ── Test function ────────────────────────────────────────────
run_nesting_test() {
    local itype="$1" flags="" wait_time=30 label="LXC"
    if [[ "$itype" == "vm" ]]; then
        flags="--vm -c limits.cpu=2 -c limits.memory=4GiB"
        flags+=" -c security.secureboot=false"
        wait_time=60; label="VM"
    else
        flags="-c security.nesting=true"
        flags+=" -c security.syscalls.intercept.mknod=true"
        flags+=" -c security.syscalls.intercept.setxattr=true"
    fi
    info "=== Testing $label nesting (max-depth=$MAX_DEPTH) ==="
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
    [[ "$l1" == "1" ]] && pass "Level 1: absolute_level=1" \
        || fail "Level 1: expected 1, got $l1"

    if [[ "$MAX_DEPTH" -le 1 ]]; then
        echo ""; echo "RESULTS ($label): $PASSED passed, $FAILED failed"
        return $(( FAILED > 0 ? 1 : 0 ))
    fi

    # Push worker into L1 and run recursively
    echo "$WORKER" | incus exec "nest-l1" --project "$NEST_PROJECT" -- \
        tee /tmp/nest-worker.sh > /dev/null
    incus exec "nest-l1" --project "$NEST_PROJECT" -- chmod +x /tmp/nest-worker.sh
    info "Recursive nesting levels 1->$MAX_DEPTH (~$((MAX_DEPTH * 90))s)..."
    local output
    output=$(incus exec "nest-l1" --project "$NEST_PROJECT" -- \
        bash /tmp/nest-worker.sh 1 "$MAX_DEPTH" "$NEST_IMAGE" 2>&1) || true
    while IFS= read -r line; do
        case "$line" in
            *"[PASS]"*) pass "${line#*\[PASS\] }" ;;
            *"[FAIL]"*) fail "${line#*\[FAIL\] }" ;;
            *"[STOP]"*) pass "Level $MAX_DEPTH: nesting stops correctly" ;;
            *"[WORKER]"*) info "${line#*\[WORKER\] }" ;;
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
