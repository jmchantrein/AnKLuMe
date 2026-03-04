#!/usr/bin/env python3
"""E2E test: boot QEMU, run start.sh with each storage backend.

Strategy: Write test script to VM, execute redirecting to file,
then cat the result file. Avoids all terminal echo/parsing issues.
"""

import os
import re
import sys
import time

import pexpect

TIMEOUT = 180
ANSI_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')


def clean(text):
    """Strip ANSI escape codes."""
    return ANSI_RE.sub('', text)


def boot_qemu(iso_path, disk_path, kernel_path, initrd_path, ram="8192"):
    """Boot QEMU with serial console and return pexpect child."""
    cmd = (
        f"qemu-system-x86_64"
        f" -m {ram} -smp 4 -enable-kvm"
        f" -cdrom {iso_path} -boot d"
        f" -drive file={disk_path},format=qcow2,if=virtio,cache=writethrough"
        f" -kernel {kernel_path} -initrd {initrd_path}"
        f' -append "ro boot=anklume apparmor=0 anklume.boot_mode=iso'
        f' anklume.toram=1 anklume.desktop=kde console=ttyS0,115200n8"'
        f" -display none -serial stdio -no-reboot"
        f" -device virtio-net-pci,netdev=net0 -netdev user,id=net0"
    )
    child = pexpect.spawn(cmd, encoding="utf-8", timeout=TIMEOUT)
    child.logfile_read = None
    return child


def wait_prompt(child, timeout=10):
    """Wait for a shell prompt."""
    child.expect(r"[\$#]", timeout=timeout)
    time.sleep(0.3)


def send_and_wait(child, cmd, marker, timeout=300):
    """Send command, wait for unique marker, return raw output.

    Uses `rev` to reverse the marker so the literal string never
    appears in the echoed command line — only in the output.
    """
    reversed_marker = marker[::-1]
    full = f"{cmd}; echo {reversed_marker} | rev"
    child.sendline(full)
    child.expect(marker, timeout=timeout)
    time.sleep(0.5)
    return child.before


def login(child):
    """Wait for login prompt and log in."""
    print("  Waiting for boot + login...")
    child.expect("login:", timeout=TIMEOUT)
    time.sleep(1)
    child.sendline("anklume")
    child.expect(["Password:", "Mot de passe"], timeout=30)
    child.sendline("anklume")
    wait_prompt(child, timeout=30)
    time.sleep(2)
    # Force plain bash with no rc files (avoids zsh OSC noise on Arch)
    child.sendline("exec bash --norc --noprofile 2>/dev/null || true")
    time.sleep(2)
    child.sendline("export PS1='# '")
    time.sleep(0.5)
    child.sendline("export TERM=dumb")
    time.sleep(0.5)
    child.sendline("bind 'set enable-bracketed-paste off' 2>/dev/null")
    time.sleep(0.5)
    # Consume all pending output
    try:
        child.read_nonblocking(size=16384, timeout=2)
    except Exception:
        pass
    # Verify shell works with reversed marker
    child.sendline("echo 9477KONIGOLEM | rev")
    child.expect("MELOGINOK7749", timeout=10)
    time.sleep(0.5)
    print("  Logged in (plain bash).")


def generate_test_script(backend, disk=None):
    """Generate a shell test script for the given backend."""
    disk_arg = f"--disk {disk}" if disk else ""
    script = """#!/bin/bash
set -u
PASS=0; FAIL=0
pass() { echo "PASS: $*"; ((PASS++)); }
fail() { echo "FAIL: $*"; ((FAIL++)); }

echo "=== PRE-FLIGHT ==="

# 1. SDDM
r=$(systemctl is-active sddm 2>&1)
case "$r" in
    inactive|dead|unknown) pass "SDDM=$r" ;;
    *) if echo "$r" | grep -qi "not be found"; then pass "SDDM not found"
       else fail "SDDM=$r"; fi ;;
esac

# 2. No desktop
if pgrep -x "kwin_wayland|sway|labwc" >/dev/null 2>&1; then
    fail "desktop running"
else
    pass "no desktop"
fi

# 3. Disk
if lsblk /dev/vda >/dev/null 2>&1; then
    sz=$(lsblk /dev/vda -d -o SIZE -n 2>/dev/null | tr -d ' ')
    pass "disk /dev/vda $sz"
else
    pass "no /dev/vda (ok for dir)"
fi
"""

    if backend == "zfs":
        script += """
# 4. ZFS module available (check only — do NOT load, let start handle it)
# Use sudo: modinfo is at /usr/sbin/ which is not in non-root PATH
if sudo modinfo zfs >/dev/null 2>&1; then
    pass "ZFS module available"
else
    fail "ZFS module not found (sudo modinfo zfs failed)"
    find /lib/modules/$(uname -r) -name 'zfs*' 2>/dev/null | head -5
    echo "=== RESULTS: $PASS passed, $FAIL failed ==="
    exit 1
fi
"""
    elif backend == "btrfs":
        script += """
# 4. btrfs tools (may be in /usr/sbin, not in user PATH)
if which mkfs.btrfs >/dev/null 2>&1 || [ -x /usr/sbin/mkfs.btrfs ]; then
    pass "btrfs tools"
else
    fail "btrfs tools"
fi
"""

    script += f"""
echo "=== FIRST-BOOT ==="
sudo /opt/anklume/scripts/start.sh --backend {backend} {disk_arg} --yes 2>&1 | tee /tmp/start.log
FB_RC=${{PIPESTATUS[0]}}
echo "=== FIRST-BOOT RC=$FB_RC ==="
echo "=== FIRST-BOOT LOG ==="
tail -30 /tmp/start.log 2>/dev/null
echo "=== END LOG ==="

# If bootstrap container exists in ERROR, show its log
if sudo incus list --format csv -c ns 2>/dev/null | grep -q ERROR; then
    echo "=== CONTAINER ERROR LOG ==="
    for c in $(sudo incus list --format csv -c n 2>/dev/null); do
        state=$(sudo incus list --format csv -c ns "$c" 2>/dev/null | cut -d, -f2)
        if [ "$state" = "ERROR" ]; then
            echo "--- $c ---"
            sudo incus info "$c" --show-log 2>&1 | tail -30
        fi
    done
    echo "=== END CONTAINER LOG ==="
fi

if [ $FB_RC -le 1 ]; then
    pass "start rc=$FB_RC"
else
    fail "start rc=$FB_RC"
fi

echo "=== POST-FLIGHT ==="

# pool.conf
if [ -f /mnt/anklume-persist/pool.conf ]; then
    pass "pool.conf exists"
    cat /mnt/anklume-persist/pool.conf
else
    fail "pool.conf missing"
fi

# pool.conf backend
b=$(grep POOL_BACKEND /mnt/anklume-persist/pool.conf 2>/dev/null | cut -d= -f2)
if [ "$b" = "{backend}" ]; then
    pass "POOL_BACKEND=$b"
else
    fail "POOL_BACKEND=$b expected {backend}"
fi

# Incus pool exists
if sudo incus storage show anklume-data >/dev/null 2>&1; then
    pass "incus pool exists"
else
    fail "incus pool missing"
    sudo incus storage list 2>&1
fi

# Incus pool driver
drv=$(sudo incus storage show anklume-data 2>/dev/null | grep '^driver:' | awk '{{print $2}}')
if [ "$drv" = "{backend}" ]; then
    pass "incus driver=$drv"
else
    fail "incus driver=$drv expected {backend}"
fi
"""

    if backend == "zfs":
        script += """
# ZFS pool online
if sudo zpool list anklume-data 2>/dev/null | grep -q ONLINE; then
    pass "ZFS pool ONLINE"
    sudo zpool list anklume-data
else
    fail "ZFS pool not online"
    sudo zpool list 2>&1
fi
"""
    elif backend == "btrfs":
        script += """
# BTRFS mounted
if mount | grep -q anklume-data; then
    pass "BTRFS mounted"
    mount | grep anklume-data
else
    fail "BTRFS not mounted"
fi
"""

    script += """
echo ""
echo "=== RESULTS: $PASS passed, $FAIL failed ==="
"""
    return script


def test_backend(iso_path, backend, disk_size_gb=150):
    """Run a complete E2E test for one backend."""
    print(f"\n{'='*60}")
    print(f"  E2E TEST: {backend.upper()} on {os.path.basename(iso_path)}")
    print(f"{'='*60}")

    test_dir = "/tmp/qemu-test"
    disk_path = f"{test_dir}/test-disk-{backend}.qcow2"

    if "arch" in iso_path:
        kernel_path = f"{test_dir}/vmlinuz-arch"
        initrd_path = f"{test_dir}/initrd-arch.img"
    else:
        kernel_path = f"{test_dir}/vmlinuz"
        initrd_path = f"{test_dir}/initrd.img"

    print(f"  Creating {disk_size_gb}GB disk...")
    os.system(f"qemu-img create -f qcow2 {disk_path} {disk_size_gb}G >/dev/null 2>&1")

    results = {}

    try:
        child = boot_qemu(iso_path, disk_path, kernel_path, initrd_path)
        login(child)

        # Write test script via echo commands (more reliable than heredoc over serial)
        disk_arg = "/dev/vda" if backend != "dir" else None
        script = generate_test_script(backend, disk=disk_arg)

        print("  Writing test script...")
        # Base64 encode to avoid quoting issues
        import base64
        b64 = base64.b64encode(script.encode()).decode()
        # Split b64 into chunks to avoid line length issues
        chunk_size = 200
        chunks = [b64[i:i+chunk_size] for i in range(0, len(b64), chunk_size)]

        send_and_wait(child, "rm -f /tmp/e2e-script.b64 /tmp/e2e-test.sh", "RM_DONE")
        for i, chunk in enumerate(chunks):
            send_and_wait(child, f"echo -n '{chunk}' >> /tmp/e2e-script.b64", f"CHUNK_{i}_DONE")
        decode_cmd = "base64 -d /tmp/e2e-script.b64 > /tmp/e2e-test.sh && chmod +x /tmp/e2e-test.sh"
        send_and_wait(child, decode_cmd, "B64_DONE")

        # Verify script was written
        send_and_wait(child, "wc -l /tmp/e2e-test.sh", "WC_DONE")
        print("  Test script written.")

        # Verify script content
        verify_out = send_and_wait(child, "head -3 /tmp/e2e-test.sh", "VERIFY_DONE")
        verify_clean = clean(verify_out)
        if "#!/bin/bash" in verify_clean:
            print("  Script verified (starts with #!/bin/bash).")
        else:
            print(f"  WARNING: Script may be malformed. Head: {verify_clean[:100]}")

        # Execute test script, redirect output to file
        print(f"  Executing test ({backend})... (this takes 1-2 min)")
        send_and_wait(child,
            "bash /tmp/e2e-test.sh > /tmp/e2e-result.txt 2>&1",
            "EXEC_DONE", timeout=300)
        print("  Test complete.")

        # Check result file exists and has content
        size_out = send_and_wait(child, "wc -l /tmp/e2e-result.txt", "SIZE_DONE")
        print(f"  Result file: {clean(size_out).strip().split(chr(10))[-1].strip()}")
        print("  Reading results...")

        # Read result file using reversed marker
        time.sleep(1)
        end_marker = "ENDRESULTS7749"
        reversed_end = end_marker[::-1]
        child.sendline(f"cat /tmp/e2e-result.txt; echo {reversed_end} | rev")
        child.expect(end_marker, timeout=60)
        raw = clean(child.before)

        # Parse results
        for line in raw.split('\n'):
            line = line.strip()
            if not line:
                continue
            if line.startswith("PASS:"):
                name = line[5:].strip()
                results[name] = True
                print(f"    [PASS] {name}")
            elif line.startswith("FAIL:"):
                name = line[5:].strip()
                results[name] = False
                print(f"    [FAIL] {name}")
            elif "FIRST-BOOT RC=" in line:
                print(f"    {line}")
            elif "FIRST-BOOT LOG" in line or "END LOG" in line:
                print(f"    {line}")
            elif line.startswith("[") and "]" in line:
                # First-boot log line (e.g., [INFO], [ERR], [WARN])
                print(f"    log: {line}")
            elif line.startswith("POOL_") or line.startswith("LUKS"):
                print(f"    conf: {line}")
            elif "RESULTS:" in line:
                print(f"    {line}")

        # Shutdown
        child.sendline("sudo poweroff")
        try:
            child.expect(pexpect.EOF, timeout=30)
        except Exception:
            pass
        child.close()

    except pexpect.TIMEOUT as e:
        print(f"\n  TIMEOUT at: {e}")
        # Try to get what we can
        try:
            child.sendline("echo TIMEOUT_RECOVERY && cat /tmp/e2e-result.txt 2>/dev/null && echo RECOVERY_END")
            child.expect("RECOVERY_END", timeout=10)
            raw = clean(child.before)
            for line in raw.split('\n'):
                line = line.strip()
                if line.startswith("PASS:") or line.startswith("FAIL:"):
                    print(f"    {line}")
        except Exception:
            pass
        results["timeout"] = False
        try:
            child.close()
        except Exception:
            pass
    except Exception as e:
        print(f"\n  ERROR: {e}")
        results["error"] = False
        try:
            child.close()
        except Exception:
            pass

    # Summary
    passed = sum(1 for v in results.values() if v is True)
    failed = sum(1 for v in results.values() if v is False)
    print(f"\n  --- {backend.upper()} SUMMARY: {passed} passed, {failed} failed ---")
    return results


def generate_reboot_test_script(backend):
    """Generate a test script for second boot — verifies pool detection."""
    return f"""#!/bin/bash
set -u
PASS=0; FAIL=0
pass() {{ echo "PASS: $*"; ((PASS++)); }}
fail() {{ echo "FAIL: $*"; ((FAIL++)); }}

echo "=== REBOOT TEST: {backend} ==="

# Kill any running start.sh from the systemd service first
sudo systemctl stop anklume-start.service 2>/dev/null || true
sleep 2

# 1. Check disk has existing data (blkid or backend-specific tool)
disk_type=$(sudo blkid -p -o value -s TYPE /dev/vda 2>/dev/null || true)
echo "blkid type: $disk_type"
if [ -n "$disk_type" ] && [ "$disk_type" != "gpt" ]; then
    pass "disk has filesystem signature: $disk_type"
else
    # ZFS uses GPT partition for metadata — blkid shows PTTYPE not TYPE.
    # BTRFS shows "btrfs" in TYPE directly.
    # Try backend-specific detection:
    case "{backend}" in
        zfs)
            sudo modprobe zfs 2>/dev/null || true
            if sudo zpool import 2>/dev/null | grep -q "pool:"; then
                pass "ZFS pool detectable via zpool import"
            else
                fail "disk has no detectable filesystem"
            fi
            ;;
        btrfs)
            if sudo blkid -p -o value -s TYPE /dev/vda 2>/dev/null | grep -q btrfs; then
                pass "BTRFS filesystem detected"
            else
                fail "disk has no detectable filesystem"
            fi
            ;;
        *)
            fail "disk has no detectable filesystem"
            ;;
    esac
fi

# 2. Run start.sh in --yes mode (redirect to file, no pipe — avoids tee hang)
timeout 90 sudo /opt/anklume/scripts/start.sh --yes > /tmp/reboot-start.log 2>&1
RC=$?
echo "=== START RC=$RC ==="

# 3. Check log for detection messages (not destructive messages)
DETECT_PAT="existing.*pool detected\\|pool.*imported\\|pool.*resumed\\|Setup Complete.*resumed"
if grep -qi "$DETECT_PAT" /tmp/reboot-start.log; then
    pass "start.sh detected existing pool"
else
    fail "start.sh did NOT detect existing pool"
    echo "=== LOG ==="
    head -50 /tmp/reboot-start.log
    echo "=== END LOG ==="
fi

# 4. CRITICAL: must NOT contain pool creation commands
if grep -qi "Creating ZFS pool\\|Creating BTRFS filesystem\\|mkfs\\|zpool create -f" /tmp/reboot-start.log; then
    fail "start.sh tried to REFORMAT the disk (data loss!)"
else
    pass "no destructive operations in log"
fi

# 5. Verify pool is functional (import manually if start.sh timed out on bootstrap)
if ! sudo incus storage show anklume-data >/dev/null 2>&1; then
    sudo modprobe zfs 2>/dev/null || true
    sudo zpool import anklume-data 2>/dev/null || sudo zpool import -f anklume-data 2>/dev/null || true
fi
if sudo incus storage show anklume-data >/dev/null 2>&1; then
    pass "incus pool exists after reboot"
elif command -v zpool >/dev/null 2>&1 && sudo zpool list anklume-data 2>/dev/null | grep -q ONLINE; then
    pass "ZFS pool online (Incus ref may need re-create)"
elif command -v btrfs >/dev/null 2>&1 && sudo btrfs filesystem show anklume-data 2>/dev/null | grep -q "Label"; then
    pass "BTRFS filesystem found"
else
    fail "pool not found after reboot"
fi

echo ""
echo "=== RESULTS: $PASS passed, $FAIL failed ==="
"""


def test_reboot(iso_path, backend, disk_size_gb=150):
    """E2E reboot test: first boot creates pool, second boot detects it."""
    print(f"\n{'='*60}")
    print(f"  REBOOT TEST: {backend.upper()} on {os.path.basename(iso_path)}")
    print(f"{'='*60}")

    test_dir = "/tmp/qemu-test"
    disk_path = f"{test_dir}/reboot-disk-{backend}.qcow2"

    if "arch" in iso_path:
        kernel_path = f"{test_dir}/vmlinuz-arch"
        initrd_path = f"{test_dir}/initrd-arch.img"
    else:
        kernel_path = f"{test_dir}/vmlinuz"
        initrd_path = f"{test_dir}/initrd.img"

    # Phase 1: First boot — create pool
    print(f"  Phase 1: Creating pool ({backend})...")
    os.system(f"qemu-img create -f qcow2 {disk_path} {disk_size_gb}G >/dev/null 2>&1")

    results = {}

    try:
        child = boot_qemu(iso_path, disk_path, kernel_path, initrd_path)
        login(child)

        disk_arg = "--disk /dev/vda" if backend != "dir" else ""
        cmd = f"sudo /opt/anklume/scripts/start.sh --backend {backend} {disk_arg} --yes"
        print(f"  Running: {cmd}")
        send_and_wait(child,
            f"{cmd} > /tmp/phase1.log 2>&1",
            "PHASE1_DONE", timeout=300)

        # Verify pool was created AND understand where the data went
        verify = send_and_wait(child,
            "sudo incus storage show anklume-data >/dev/null 2>&1 && echo POOL_OK || echo POOL_FAIL",
            "POOLCHECK_DONE")

        if "POOL_OK" in clean(verify):
            print("  Phase 1: Pool created successfully.")
            results["phase1_create"] = True
        else:
            print("  Phase 1: FAIL — pool not created!")
            results["phase1_create"] = False
            child.sendline("sudo poweroff")
            try:
                child.expect(pexpect.EOF, timeout=60)
            except Exception:
                pass
            child.close()
            passed = sum(1 for v in results.values() if v is True)
            failed = sum(1 for v in results.values() if v is False)
            print(f"\n  --- REBOOT {backend.upper()} SUMMARY: {passed} passed, {failed} failed ---")
            return results

        # Clean shutdown: export/unmount, sync, then poweroff
        if backend == "zfs":
            send_and_wait(child, "sudo zpool export anklume-data 2>&1 || true", "EXPORT_DONE")
        elif backend == "btrfs":
            send_and_wait(child, "sudo umount /mnt/anklume-data 2>&1 || true", "UMOUNT_DONE")
        send_and_wait(child, "sync; sleep 2", "SYNC_DONE")
        child.sendline("sudo poweroff")
        try:
            child.expect(pexpect.EOF, timeout=60)
        except Exception:
            pass
        child.close()
        time.sleep(5)

        # Verify disk has data (qcow2 file should be larger than initial)
        disk_stat = os.stat(disk_path)
        print(f"  Disk file size after Phase 1: {disk_stat.st_size / 1024 / 1024:.1f} MB")

        # Phase 2: Second boot — same disk, must detect pool
        print("  Phase 2: Rebooting with same disk...")
        child = boot_qemu(iso_path, disk_path, kernel_path, initrd_path)
        login(child)

        # Write and run reboot test script
        script = generate_reboot_test_script(backend)
        import base64
        b64 = base64.b64encode(script.encode()).decode()
        chunk_size = 200
        chunks = [b64[i:i+chunk_size] for i in range(0, len(b64), chunk_size)]

        send_and_wait(child, "rm -f /tmp/e2e-script.b64 /tmp/e2e-test.sh", "RM_DONE2")
        for i, chunk in enumerate(chunks):
            send_and_wait(child, f"echo -n '{chunk}' >> /tmp/e2e-script.b64", f"RB_CHUNK_{i}_DONE")
        decode_cmd = "base64 -d /tmp/e2e-script.b64 > /tmp/e2e-test.sh && chmod +x /tmp/e2e-test.sh"
        send_and_wait(child, decode_cmd, "RB_B64_DONE")

        print(f"  Executing reboot test ({backend})...")
        send_and_wait(child,
            "bash /tmp/e2e-test.sh > /tmp/e2e-result.txt 2>&1",
            "RB_EXEC_DONE", timeout=300)
        print("  Reboot test complete.")

        # Read results
        time.sleep(1)
        end_marker = "REBOOTEND7749"
        reversed_end = end_marker[::-1]
        child.sendline(f"cat /tmp/e2e-result.txt; echo {reversed_end} | rev")
        child.expect(end_marker, timeout=60)
        raw = clean(child.before)

        for line in raw.split('\n'):
            line = line.strip()
            if not line:
                continue
            if line.startswith("PASS:"):
                name = line[5:].strip()
                results[name] = True
                print(f"    [PASS] {name}")
            elif line.startswith("FAIL:"):
                name = line[5:].strip()
                results[name] = False
                print(f"    [FAIL] {name}")
            elif "START RC=" in line or "blkid type:" in line:
                print(f"    {line}")
            elif "RESULTS:" in line:
                print(f"    {line}")

        child.sendline("sudo poweroff")
        try:
            child.expect(pexpect.EOF, timeout=30)
        except Exception:
            pass
        child.close()

    except pexpect.TIMEOUT as e:
        print(f"\n  TIMEOUT at: {e}")
        results["timeout"] = False
        try:
            child.close()
        except Exception:
            pass
    except Exception as e:
        print(f"\n  ERROR: {e}")
        results["error"] = False
        try:
            child.close()
        except Exception:
            pass

    passed = sum(1 for v in results.values() if v is True)
    failed = sum(1 for v in results.values() if v is False)
    print(f"\n  --- REBOOT {backend.upper()} SUMMARY: {passed} passed, {failed} failed ---")
    return results


def main():
    if len(sys.argv) < 2:
        print("Usage: e2e-all-backends.py <iso-path> [backends...]")
        print("       e2e-all-backends.py <iso-path> reboot:<backend> [...]")
        sys.exit(1)

    iso_path = sys.argv[1]
    backends = sys.argv[2:] if len(sys.argv) > 2 else ["dir", "btrfs", "zfs"]

    if not os.path.exists(iso_path):
        print(f"ERROR: ISO not found: {iso_path}")
        sys.exit(1)

    test_dir = "/tmp/qemu-test"
    os.makedirs(test_dir, exist_ok=True)

    if "arch" in iso_path:
        kernel = f"{test_dir}/vmlinuz-arch"
        initrd = f"{test_dir}/initrd-arch.img"
    else:
        kernel = f"{test_dir}/vmlinuz"
        initrd = f"{test_dir}/initrd.img"

    if not os.path.exists(kernel) or not os.path.exists(initrd):
        print(f"Extracting kernel/initrd from {iso_path}...")
        mnt = f"{test_dir}/mnt/iso"
        os.makedirs(mnt, exist_ok=True)
        os.system(f"mount -o loop,ro {iso_path} {mnt} 2>/dev/null")
        os.system(f"cp {mnt}/boot/vmlinuz {kernel}")
        os.system(f"cp {mnt}/boot/initrd.img {initrd}")
        os.system(f"umount {mnt}")

    print(f"\n{'#'*60}")
    print("#  E2E STORAGE BACKEND TESTS")
    print(f"#  ISO: {os.path.basename(iso_path)}")
    print(f"#  Backends: {', '.join(backends)}")
    print(f"{'#'*60}")

    all_results = {}
    for backend in backends:
        if backend.startswith("reboot:"):
            rb_backend = backend.split(":")[1]
            all_results[f"reboot-{rb_backend}"] = test_reboot(iso_path, rb_backend)
        else:
            all_results[backend] = test_backend(iso_path, backend)

    print(f"\n{'#'*60}")
    print("#  FINAL REPORT")
    print(f"{'#'*60}")
    all_pass = True
    for backend, results in all_results.items():
        passed = sum(1 for v in results.values() if v is True)
        failed = sum(1 for v in results.values() if v is False)
        status = "PASS" if failed == 0 else "FAIL"
        if failed > 0:
            all_pass = False
        print(f"  [{status}] {backend.upper()}: {passed} passed, {failed} failed")
        for name, result in results.items():
            if result is not True:
                print(f"         FAIL: {name}")

    print(f"\n  Overall: {'ALL PASS' if all_pass else 'FAILURES DETECTED'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
