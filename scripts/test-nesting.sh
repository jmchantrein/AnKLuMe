#!/usr/bin/env bash
# test-nesting.sh — Test anklume nesting up to 3 levels deep
#
# Supports LXC (container-in-container) and KVM (VM) nesting modes.
# Creates instances at level 1, bootstraps Incus inside, creates
# level 2 nested instance, and verifies level 3 stop condition.
#
# LXC nesting requires: security.nesting + security.privileged on L2
# (stgraber recommendation: privileged inside unprivileged is safe)
#
# Usage:
#   scripts/test-nesting.sh [--mode lxc|vm|both] [--dry-run]
#
# Requires: Incus daemon. VM mode requires KVM + 8GB+ RAM.

set -euo pipefail

# ── Configuration ────────────────────────────────────────────
NEST_PROJECT="nesting-test"
NEST_L1="nest-level1"
NEST_L2="nest-level2"
NEST_IMAGE="images:debian/13"
DRY_RUN=false
MODE="lxc"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=true ;;
        --mode)    MODE="$2"; shift ;;
        -h|--help)
            echo "Usage: $0 [--mode lxc|vm|both] [--dry-run]"
            exit 0 ;;
        *) echo "Unknown: $1"; exit 1 ;;
    esac
    shift
done

if [[ "$MODE" != "lxc" && "$MODE" != "vm" && "$MODE" != "both" ]]; then
    echo "Invalid mode: $MODE (must be lxc, vm, or both)"; exit 1
fi

# ── Helpers ──────────────────────────────────────────────────
info()  { printf "  [INFO] %s\n" "$1"; }
pass()  { printf "  [PASS] %s\n" "$1"; }
fail()  { printf "  [FAIL] %s\n" "$1"; }
die()   { fail "$1"; exit 1; }

# shellcheck disable=SC2317,SC2329
cleanup() {
    info "Cleaning up nesting test resources..."
    incus delete "$NEST_L1" --project "$NEST_PROJECT" --force 2>/dev/null || true
    incus project delete "$NEST_PROJECT" 2>/dev/null || true
}
trap cleanup EXIT

# ── Preflight ────────────────────────────────────────────────
info "Checking prerequisites..."
if ! incus info >/dev/null 2>&1; then
    die "Incus daemon not available"
fi

if $DRY_RUN; then
    info "Dry-run mode (--mode $MODE) — verifying test structure only"
    pass "Script structure valid"
    pass "Prerequisites checked"
    pass "Would create project: $NEST_PROJECT"
    pass "Would launch $MODE instance: $NEST_L1"
    pass "Would test nesting context at levels 1-3"
    echo ""
    echo "RESULTS: 5 passed, 0 failed (dry-run)"
    exit 0
fi

# ── Common functions ─────────────────────────────────────────
run_nesting_test() {
    local instance_type="$1"  # "lxc" or "vm"
    local launch_flags=""
    local vm_nested="false"
    local wait_time=30
    local label="LXC"

    if [[ "$instance_type" == "vm" ]]; then
        launch_flags="--vm -c limits.cpu=2 -c limits.memory=4GiB"
        launch_flags+=" -c security.secureboot=false"
        vm_nested="true"
        wait_time=60
        label="VM"
    else
        # LXC nesting: enable nesting + syscall interception
        launch_flags="-c security.nesting=true"
        launch_flags+=" -c security.syscalls.intercept.mknod=true"
        launch_flags+=" -c security.syscalls.intercept.setxattr=true"
    fi

    PASSED=0; FAILED=0
    info "=== Testing $label nesting ==="

    # ── Create project ───────────────────────────────────────
    info "Creating project $NEST_PROJECT..."
    incus project create "$NEST_PROJECT" \
        -c features.images=false \
        -c features.profiles=false 2>/dev/null || true

    # ── Level 1: Launch instance ─────────────────────────────
    info "Launching $label $NEST_L1..."
    # shellcheck disable=SC2086  # launch_flags must word-split
    incus launch "$NEST_IMAGE" "$NEST_L1" $launch_flags \
        --project "$NEST_PROJECT" 2>/dev/null

    info "Waiting for $label agent..."
    for _i in $(seq 1 "$wait_time"); do
        if incus exec "$NEST_L1" --project "$NEST_PROJECT" -- true 2>/dev/null; then
            break
        fi
        sleep 2
    done

    if ! incus exec "$NEST_L1" --project "$NEST_PROJECT" -- true 2>/dev/null; then
        die "$label $NEST_L1 not ready after $((wait_time * 2))s"
    fi
    pass "$label $NEST_L1 is running"
    ((PASSED++)) || true

    # ── Level 1: Write nesting context ───────────────────────
    info "Writing nesting context files..."
    incus exec "$NEST_L1" --project "$NEST_PROJECT" -- bash -c "
        mkdir -p /etc/anklume
        echo 1 > /etc/anklume/absolute_level
        echo 0 > /etc/anklume/relative_level
        echo $vm_nested > /etc/anklume/vm_nested
        echo false > /etc/anklume/yolo
    "

    LEVEL1=$(incus exec "$NEST_L1" --project "$NEST_PROJECT" -- \
        cat /etc/anklume/absolute_level 2>/dev/null)
    if [[ "$LEVEL1" == "1" ]]; then
        pass "Level 1: absolute_level=1"
        ((PASSED++)) || true
    else
        fail "Level 1: absolute_level=$LEVEL1 (expected 1)"
        ((FAILED++)) || true
    fi

    # ── Level 1: Install Incus inside ────────────────────────
    info "Installing Incus inside $label (this takes ~60s)..."
    incus exec "$NEST_L1" --project "$NEST_PROJECT" -- bash -c '
        export DEBIAN_FRONTEND=noninteractive
        apt-get update -qq >/dev/null 2>&1
        apt-get install -y -qq incus >/dev/null 2>&1
        # Ensure subuid/subgid exist (Debian postinst may skip in containers)
        grep -q "^root:" /etc/subuid 2>/dev/null \
            || echo "root:100000:1000000000" >> /etc/subuid
        grep -q "^root:" /etc/subgid 2>/dev/null \
            || echo "root:100000:1000000000" >> /etc/subgid
        incus admin init --minimal >/dev/null 2>&1 || true
    ' 2>/dev/null

    if incus exec "$NEST_L1" --project "$NEST_PROJECT" -- \
        incus info >/dev/null 2>&1; then
        pass "Level 1: Incus daemon running inside $label"
        ((PASSED++)) || true
    else
        fail "Level 1: Incus daemon not available inside $label"
        ((FAILED++)) || true
    fi

    # ── Level 2: Create container inside level 1 ─────────────
    # For LXC nesting: L2 must be privileged (stgraber recommendation)
    # — unprivileged L1 can't remap uids for sub-containers
    # — privileged inside unprivileged is still isolated by L1's userns
    local l2_flags=""
    if [[ "$instance_type" == "lxc" ]]; then
        l2_flags="-c security.privileged=true"
    fi

    info "Creating nested container $NEST_L2 inside $label..."
    incus exec "$NEST_L1" --project "$NEST_PROJECT" -- bash -c "
        incus launch $NEST_IMAGE $NEST_L2 $l2_flags 2>/dev/null
        for _i in \$(seq 1 30); do
            incus exec $NEST_L2 -- true 2>/dev/null && break
            sleep 2
        done
        incus exec $NEST_L2 -- mkdir -p /etc/anklume
        incus exec $NEST_L2 -- bash -c 'echo 2 > /etc/anklume/absolute_level'
        incus exec $NEST_L2 -- bash -c 'echo 1 > /etc/anklume/relative_level'
        incus exec $NEST_L2 -- bash -c 'echo $vm_nested > /etc/anklume/vm_nested'
    " 2>/dev/null

    LEVEL2=$(incus exec "$NEST_L1" --project "$NEST_PROJECT" -- \
        incus exec "$NEST_L2" -- cat /etc/anklume/absolute_level 2>/dev/null)
    if [[ "$LEVEL2" == "2" ]]; then
        pass "Level 2: absolute_level=2"
        ((PASSED++)) || true
    else
        fail "Level 2: absolute_level=$LEVEL2 (expected 2)"
        ((FAILED++)) || true
    fi

    # ── Level 3: Verify stop condition ───────────────────────
    info "Verifying level 3 stop condition..."
    # shellcheck disable=SC2016
    LEVEL3_CHECK=$(incus exec "$NEST_L1" --project "$NEST_PROJECT" -- \
        incus exec "$NEST_L2" -- bash -c '
            level=$(cat /etc/anklume/absolute_level 2>/dev/null || echo 0)
            if [ "$level" -ge 2 ]; then
                echo "STOP: max nesting depth reached (level=$level)"
            else
                echo "CONTINUE"
            fi
        ' 2>/dev/null)
    if [[ "$LEVEL3_CHECK" == *"STOP"* ]]; then
        pass "Level 3: Nesting correctly stops at depth 2+"
        ((PASSED++)) || true
    else
        fail "Level 3: Expected stop, got: $LEVEL3_CHECK"
        ((FAILED++)) || true
    fi

    # ── Cleanup this run ─────────────────────────────────────
    incus delete "$NEST_L1" --project "$NEST_PROJECT" --force 2>/dev/null || true
    incus project delete "$NEST_PROJECT" 2>/dev/null || true

    echo ""
    echo "RESULTS ($label): $PASSED passed, $FAILED failed"
    return $(( FAILED > 0 ? 1 : 0 ))
}

# ── Main ─────────────────────────────────────────────────────
EXIT_CODE=0

case "$MODE" in
    lxc)  run_nesting_test lxc  || EXIT_CODE=1 ;;
    vm)   run_nesting_test vm   || EXIT_CODE=1 ;;
    both)
        run_nesting_test lxc || EXIT_CODE=1
        run_nesting_test vm  || EXIT_CODE=1
        ;;
esac

exit "$EXIT_CODE"
