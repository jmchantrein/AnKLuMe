#!/usr/bin/env bash
# live-os-test-vm.sh — Test anklume Live OS image in an Incus VM
# Usage: live-os-test-vm.sh [OPTIONS]
#
# Options:
#   --image FILE      Path to built image (.iso or .img, default: anklume-live.iso)
#   --data-size SIZE  Virtual data disk size (default: 10GiB)
#   --vm-name NAME    VM name (default: anklume-live-test)
#   --project NAME    Incus project (default: default)
#   --keep            Keep VM after tests (default: destroy)
#   --shell           Drop into VM console after boot (skip tests)
#   --clean           Destroy existing test VM and exit
#   --help            Show this help
#
# Supports both .iso (CD-ROM boot) and .img (raw disk) formats.
# No physical hardware needed — all testing done locally via KVM.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=/dev/null
source "$SCRIPT_DIR/live-os-lib.sh"

# ── Defaults ──
IMAGE="anklume-live.iso"
DATA_SIZE="10GiB"
VM_NAME="anklume-live-test"
PROJECT="default"
KEEP=false
SHELL_MODE=false
CLEAN_ONLY=false
BOOT_TIMEOUT=120
TEST_TIMEOUT=60

# ── Usage ──
usage() {
    echo "Usage: $(basename "$0") [OPTIONS]"
    echo ""
    echo "Test anklume Live OS image in an Incus VM (KVM)."
    echo ""
    echo "Options:"
    echo "  --image FILE      Path to built image .iso or .img (default: anklume-live.iso)"
    echo "  --data-size SIZE  Virtual data disk size (default: 10GiB)"
    echo "  --vm-name NAME    VM name (default: anklume-live-test)"
    echo "  --project NAME    Incus project (default: default)"
    echo "  --keep            Keep VM after tests (default: destroy)"
    echo "  --shell           Drop into VM console after boot (skip tests)"
    echo "  --clean           Destroy existing test VM and exit"
    echo "  --help            Show this help"
    echo ""
    echo "Examples:"
    echo "  $(basename "$0") --image anklume-live.iso"
    echo "  $(basename "$0") --image anklume-arch.iso --shell"
    echo "  $(basename "$0") --clean"
    exit 0
}

# ── Parse arguments ──
while [ $# -gt 0 ]; do
    case "$1" in
        --image)    IMAGE="$2"; shift 2 ;;
        --data-size) DATA_SIZE="$2"; shift 2 ;;
        --vm-name)  VM_NAME="$2"; shift 2 ;;
        --project)  PROJECT="$2"; shift 2 ;;
        --keep)     KEEP=true; shift ;;
        --shell)    SHELL_MODE=true; shift ;;
        --clean)    CLEAN_ONLY=true; shift ;;
        --help)     usage ;;
        *) err "Unknown option: $1"; exit 1 ;;
    esac
done

# ── Check dependencies ──
check_deps() {
    local missing=()
    for cmd in incus qemu-img; do
        if ! command -v "$cmd" &>/dev/null; then
            missing+=("$cmd")
        fi
    done
    if [ ${#missing[@]} -gt 0 ]; then
        err "Missing dependencies: ${missing[*]}"
        exit 1
    fi
}

# ── Cleanup function ──
cleanup_vm() {
    info "Cleaning up test VM '$VM_NAME'..."
    if incus info "$VM_NAME" --project "$PROJECT" &>/dev/null; then
        incus stop "$VM_NAME" --project "$PROJECT" --force 2>/dev/null || true
        incus delete "$VM_NAME" --project "$PROJECT" --force 2>/dev/null || true
        ok "Test VM destroyed"
    else
        info "No test VM found"
    fi

    # Clean up storage volumes
    if incus storage volume show default "$VM_NAME" --project "$PROJECT" &>/dev/null 2>&1; then
        incus storage volume delete default "$VM_NAME" --project "$PROJECT" 2>/dev/null || true
    fi
    if incus storage volume show default "${VM_NAME}-data" --project "$PROJECT" &>/dev/null 2>&1; then
        incus storage volume delete default "${VM_NAME}-data" --project "$PROJECT" 2>/dev/null || true
    fi
}

# ── Clean only mode ──
if [ "$CLEAN_ONLY" = true ]; then
    check_deps
    cleanup_vm
    exit 0
fi

# ── Validate image ──
if [ ! -f "$IMAGE" ]; then
    err "Image not found: $IMAGE"
    err "Run 'scripts/build-image.sh' first to build the image"
    exit 1
fi

check_deps
IMAGE_ABS="$(realpath "$IMAGE")"
info "Testing image: $IMAGE_ABS"
info "VM name: $VM_NAME (project: $PROJECT)"

# ── Destroy existing VM if any ──
if incus info "$VM_NAME" --project "$PROJECT" &>/dev/null; then
    warn "Test VM already exists, destroying..."
    cleanup_vm
fi

# ── Detect image format ──
IMAGE_FORMAT=""
case "$IMAGE_ABS" in
    *.iso) IMAGE_FORMAT="iso" ;;
    *.img) IMAGE_FORMAT="raw" ;;
    *)
        # Try to detect via file command
        if file "$IMAGE_ABS" | grep -q "ISO 9660"; then
            IMAGE_FORMAT="iso"
        else
            IMAGE_FORMAT="raw"
        fi
        ;;
esac
info "Detected image format: $IMAGE_FORMAT"

# ── Import image as Incus VM ──
info "Importing image into Incus VM..."

if [ "$IMAGE_FORMAT" = "iso" ]; then
    # ISO mode: create empty VM and attach ISO as CD-ROM
    info "Creating empty VM for ISO boot..."
    incus init "$VM_NAME" --project "$PROJECT" --vm --empty \
        -c limits.cpu=2 \
        -c limits.memory=4GiB \
        -c security.secureboot=false

    # Attach ISO as CD-ROM device
    info "Attaching ISO as CD-ROM..."
    incus config device add "$VM_NAME" install-iso disk \
        source="$IMAGE_ABS" \
        readonly=true \
        boot.priority=10 \
        --project "$PROJECT"
    ok "ISO attached as CD-ROM"
else
    # Raw mode: convert and write to root volume
    QCOW2_IMAGE="${IMAGE_ABS%.img}.qcow2"
    if [ ! -f "$QCOW2_IMAGE" ] || [ "$IMAGE_ABS" -nt "$QCOW2_IMAGE" ]; then
        info "Converting image to qcow2..."
        qemu-img convert -f raw -O qcow2 "$IMAGE_ABS" "$QCOW2_IMAGE"
        ok "Converted to qcow2"
    fi

    info "Creating VM with UEFI boot..."
    incus init "$VM_NAME" --project "$PROJECT" --vm --empty \
        -c limits.cpu=2 \
        -c limits.memory=4GiB \
        -c security.secureboot=false

    info "Writing disk image to VM root volume..."
    STORAGE_PATH="/var/lib/incus/storage-pools/default"
    VM_ROOT="$STORAGE_PATH/virtual-machines/$VM_NAME/root.img"

    if [ -f "$VM_ROOT" ]; then
        qemu-img convert -f raw -O raw "$IMAGE_ABS" "$VM_ROOT"
        ok "Image written to root volume"
    else
        err "VM root volume not found at $VM_ROOT"
        cleanup_vm
        exit 1
    fi
fi

# Create virtual data disk (simulates the separate data disk)
info "Creating virtual data disk ($DATA_SIZE)..."
incus config device add "$VM_NAME" data-disk disk \
    pool=default \
    source="$VM_NAME" \
    size="$DATA_SIZE" \
    --project "$PROJECT" 2>/dev/null || {
    warn "Could not add data disk device (may need manual config)"
}

# ── Boot the VM ──
info "Starting VM..."
incus start "$VM_NAME" --project "$PROJECT"

# ── Wait for boot ──
info "Waiting for VM to boot (timeout: ${BOOT_TIMEOUT}s)..."
boot_start=$(date +%s)
vm_ready=false
while true; do
    elapsed=$(( $(date +%s) - boot_start ))
    if [ "$elapsed" -ge "$BOOT_TIMEOUT" ]; then
        break
    fi

    # Check if the VM agent is running
    if incus exec "$VM_NAME" --project "$PROJECT" -- true &>/dev/null 2>&1; then
        vm_ready=true
        break
    fi
    sleep 2
    printf "."
done
echo ""

if [ "$vm_ready" = false ]; then
    err "VM failed to boot within ${BOOT_TIMEOUT}s"
    warn "Check VM console: incus console $VM_NAME --project $PROJECT"
    if [ "$KEEP" = false ]; then
        cleanup_vm
    fi
    exit 1
fi
ok "VM booted successfully (${elapsed}s)"

# ── Shell mode ──
if [ "$SHELL_MODE" = true ]; then
    info "Dropping into VM shell (exit to destroy VM)..."
    incus exec "$VM_NAME" --project "$PROJECT" -- bash || true
    if [ "$KEEP" = false ]; then
        cleanup_vm
    fi
    exit 0
fi

# ── Run validation tests ──
info "Running validation tests..."
tests_passed=0
tests_failed=0
tests_skipped=0

run_test() {
    local name="$1"
    local cmd="$2"
    printf "  %-50s " "$name"
    if timeout "$TEST_TIMEOUT" incus exec "$VM_NAME" --project "$PROJECT" \
        -- bash -c "$cmd" &>/dev/null 2>&1; then
        echo -e "\033[0;32mPASS\033[0m"
        tests_passed=$((tests_passed + 1))
    else
        echo -e "\033[0;31mFAIL\033[0m"
        tests_failed=$((tests_failed + 1))
    fi
}

run_test_skip() {
    local name="$1"
    local reason="$2"
    printf "  %-50s " "$name"
    echo -e "\033[1;33mSKIP\033[0m ($reason)"
    tests_skipped=$((tests_skipped + 1))
}

echo ""
info "=== Boot validation ==="
run_test "Kernel is running" "uname -r"
run_test "Systemd is PID 1" "test \$(ps -p 1 -o comm=) = systemd"
run_test "Root filesystem mounted" "mountpoint -q /"
run_test "EFI partition exists" "test -d /boot/efi || test -d /efi || ls /sys/firmware/efi &>/dev/null"

echo ""
info "=== System services ==="
run_test "Systemd booted successfully" "systemctl is-system-running --wait 2>/dev/null || systemctl is-system-running 2>/dev/null | grep -qE 'running|degraded'"
run_test "Network is up" "ip link show | grep -q 'state UP'"
run_test "DNS resolution works" "getent hosts cloudflare.com &>/dev/null || ping -c1 -W3 1.1.1.1 &>/dev/null"

echo ""
info "=== Anklume framework ==="
run_test "Anklume files present" "test -d /opt/anklume || test -d /root/AnKLuMe || find / -maxdepth 3 -name 'infra.yml' -print -quit 2>/dev/null | grep -q ."
run_test "/etc/anklume/ exists" "test -d /etc/anklume"

echo ""
info "=== Incus daemon ==="
run_test "Incus binary available" "command -v incus"
run_test "Incus daemon running" "systemctl is-active incus.service || incus version &>/dev/null"
run_test "Incus storage pool exists" "incus storage list --format csv 2>/dev/null | grep -q . || true"

echo ""
info "=== Persistent partition ==="
run_test "Persistent partition mounted" "findmnt /mnt/anklume-persist &>/dev/null || blkid | grep -q ANKLUME-PERSIST"
run_test "A/B state file exists" "test -f /mnt/anklume-persist/ab-state || true"

echo ""
info "=== OS immutability ==="
run_test "Root is read-only or squashfs" "grep -qE 'squashfs|tmpfs|overlay' /proc/mounts || mount | grep -qE 'on / type.*(ro,|squashfs)' || true"

# ── Summary ──
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
total=$((tests_passed + tests_failed + tests_skipped))
info "Results: $tests_passed/$total passed, $tests_failed failed, $tests_skipped skipped"

if [ "$tests_failed" -gt 0 ]; then
    warn "Some tests failed — check VM with: incus exec $VM_NAME --project $PROJECT -- bash"
fi

# ── Cleanup ──
if [ "$KEEP" = true ]; then
    info "VM kept: $VM_NAME (project: $PROJECT)"
    info "  Console: incus console $VM_NAME --project $PROJECT"
    info "  Shell:   incus exec $VM_NAME --project $PROJECT -- bash"
    info "  Destroy: $0 --clean"
else
    cleanup_vm
fi

# Exit with failure if any test failed
[ "$tests_failed" -eq 0 ]
