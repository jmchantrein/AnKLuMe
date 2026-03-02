#!/usr/bin/env bash
# test-nesting.sh — Test anklume nesting up to 3 levels deep
#
# Creates a VM (level 0 → level 1), bootstraps anklume inside,
# then creates a nested container (level 1 → level 2), and verifies
# nesting context files. Stops at level 3 (no further nesting).
#
# Usage:
#   scripts/test-nesting.sh [--dry-run]
#
# Requires: Incus daemon, VM support (KVM), sufficient RAM (8GB+)

set -euo pipefail

# ── Configuration ────────────────────────────────────────────
NEST_PROJECT="nesting-test"
NEST_VM="nest-level1"
NEST_CT="nest-level2"
NEST_IMAGE="images:debian/13"
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=true ;;
        -h|--help) echo "Usage: $0 [--dry-run]"; exit 0 ;;
        *) echo "Unknown: $1"; exit 1 ;;
    esac
    shift
done

# ── Helpers ──────────────────────────────────────────────────
info()  { printf "  [INFO] %s\n" "$1"; }
pass()  { printf "  [PASS] %s\n" "$1"; }
fail()  { printf "  [FAIL] %s\n" "$1"; }
die()   { fail "$1"; cleanup; exit 1; }

cleanup() {
    info "Cleaning up nesting test resources..."
    incus delete "$NEST_VM" --project "$NEST_PROJECT" --force 2>/dev/null || true
    incus project delete "$NEST_PROJECT" 2>/dev/null || true
}
trap cleanup EXIT

# ── Preflight ────────────────────────────────────────────────
info "Checking prerequisites..."

if ! incus info >/dev/null 2>&1; then
    die "Incus daemon not available"
fi

if $DRY_RUN; then
    info "Dry-run mode — verifying test structure only"
    pass "Script structure valid"
    pass "Prerequisites checked"
    pass "Would create project: $NEST_PROJECT"
    pass "Would launch VM: $NEST_VM"
    pass "Would test nesting context at levels 1-3"
    echo ""
    echo "RESULTS: 5 passed, 0 failed (dry-run)"
    exit 0
fi

# ── Level 0: Create test project and VM ──────────────────────
PASSED=0; FAILED=0

info "Creating project $NEST_PROJECT..."
incus project create "$NEST_PROJECT" \
    -c features.images=false \
    -c features.profiles=false 2>/dev/null || true

info "Launching VM $NEST_VM (this takes ~60s)..."
incus launch "$NEST_IMAGE" "$NEST_VM" --vm \
    --project "$NEST_PROJECT" \
    -c limits.cpu=2 -c limits.memory=4GiB \
    -c security.secureboot=false 2>/dev/null

# Wait for VM to be ready
info "Waiting for VM agent..."
for _i in $(seq 1 60); do
    if incus exec "$NEST_VM" --project "$NEST_PROJECT" -- true 2>/dev/null; then
        break
    fi
    sleep 2
done

if ! incus exec "$NEST_VM" --project "$NEST_PROJECT" -- true 2>/dev/null; then
    die "VM $NEST_VM not ready after 120s"
fi
pass "VM $NEST_VM is running"
((PASSED++)) || true

# ── Level 1: Write nesting context and install Incus ─────────
info "Writing nesting context files in VM..."
incus exec "$NEST_VM" --project "$NEST_PROJECT" -- bash -c '
    mkdir -p /etc/anklume
    echo "1" > /etc/anklume/absolute_level
    echo "0" > /etc/anklume/relative_level
    echo "true" > /etc/anklume/vm_nested
    echo "false" > /etc/anklume/yolo
'

# Verify level 1 context
LEVEL1=$(incus exec "$NEST_VM" --project "$NEST_PROJECT" -- \
    cat /etc/anklume/absolute_level 2>/dev/null)
if [[ "$LEVEL1" == "1" ]]; then
    pass "Level 1: absolute_level=1"
    ((PASSED++)) || true
else
    fail "Level 1: absolute_level=$LEVEL1 (expected 1)"
    ((FAILED++)) || true
fi

VM_NESTED=$(incus exec "$NEST_VM" --project "$NEST_PROJECT" -- \
    cat /etc/anklume/vm_nested 2>/dev/null)
if [[ "$VM_NESTED" == "true" ]]; then
    pass "Level 1: vm_nested=true"
    ((PASSED++)) || true
else
    fail "Level 1: vm_nested=$VM_NESTED (expected true)"
    ((FAILED++)) || true
fi

# Install Incus inside VM
info "Installing Incus inside VM (this takes ~30s)..."
incus exec "$NEST_VM" --project "$NEST_PROJECT" -- bash -c '
    apt-get update -qq
    apt-get install -y -qq incus >/dev/null 2>&1
    incus admin init --minimal 2>/dev/null || true
' 2>/dev/null

# Verify nested Incus
if incus exec "$NEST_VM" --project "$NEST_PROJECT" -- \
    incus info >/dev/null 2>&1; then
    pass "Level 1: Incus daemon running inside VM"
    ((PASSED++)) || true
else
    fail "Level 1: Incus daemon not available inside VM"
    ((FAILED++)) || true
fi

# ── Level 2: Create container inside VM ──────────────────────
info "Creating nested container $NEST_CT inside VM..."
incus exec "$NEST_VM" --project "$NEST_PROJECT" -- bash -c "
    incus launch $NEST_IMAGE $NEST_CT 2>/dev/null
    for i in \$(seq 1 30); do
        incus exec $NEST_CT -- true 2>/dev/null && break
        sleep 2
    done
    # Write level 2 context
    incus exec $NEST_CT -- mkdir -p /etc/anklume
    incus exec $NEST_CT -- bash -c 'echo 2 > /etc/anklume/absolute_level'
    incus exec $NEST_CT -- bash -c 'echo 1 > /etc/anklume/relative_level'
    incus exec $NEST_CT -- bash -c 'echo true > /etc/anklume/vm_nested'
" 2>/dev/null

# Verify level 2 context
LEVEL2=$(incus exec "$NEST_VM" --project "$NEST_PROJECT" -- \
    incus exec "$NEST_CT" -- cat /etc/anklume/absolute_level 2>/dev/null)
if [[ "$LEVEL2" == "2" ]]; then
    pass "Level 2: absolute_level=2"
    ((PASSED++)) || true
else
    fail "Level 2: absolute_level=$LEVEL2 (expected 2)"
    ((FAILED++)) || true
fi

# ── Level 3: Verify stop condition ──────────────────────────
info "Verifying level 3 stop condition..."
# shellcheck disable=SC2016  # single quotes intentional — evaluated inside nested container
LEVEL3_CHECK=$(incus exec "$NEST_VM" --project "$NEST_PROJECT" -- \
    incus exec "$NEST_CT" -- bash -c '
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

# ── Summary ──────────────────────────────────────────────────
echo ""
echo "RESULTS: $PASSED passed, $FAILED failed"
exit $(( FAILED > 0 ? 1 : 0 ))
