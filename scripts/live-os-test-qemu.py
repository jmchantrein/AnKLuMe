#!/usr/bin/env python3
"""Automated ISO boot test via QEMU serial console.

Boots the ISO in QEMU with -nographic, interacts via serial console
using pexpect, runs validation commands, and reports results.

Usage:
    python3 scripts/live-os-test-qemu.py [ISO_PATH]
    python3 scripts/live-os-test-qemu.py images/anklume-arch.iso
"""

import json
import os
import socket
import subprocess
import sys
import time

import pexpect

# ── Configuration ──
DEFAULT_ISO = "images/anklume-arch.iso"
QMP_SOCK = "/tmp/anklume-test-qmp.sock"
MEMORY = "4096"
CPUS = "2"
BOOT_TIMEOUT = 300  # 5 min max for full boot with toram
LOGIN_TIMEOUT = 30
CMD_TIMEOUT = 15
ROOT_PASSWORD = "anklume"


def qmp_shutdown():
    """Gracefully shut down the VM via QMP."""
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect(QMP_SOCK)
        f = sock.makefile("rw")
        f.readline()  # greeting
        sock.sendall(b'{"execute": "qmp_capabilities"}\n')
        f.readline()
        sock.sendall(b'{"execute": "system_powerdown"}\n')
        f.readline()
        sock.close()
    except Exception:
        pass


_cmd_seq = 0

def run_cmd(child, cmd):
    """Send command, wait for unique end marker, return output."""
    global _cmd_seq
    _cmd_seq += 1
    marker = f"ENDMARK{_cmd_seq:04d}"
    full_cmd = f"{cmd}; echo {marker}"
    child.sendline(full_cmd)
    child.expect(marker.encode(), timeout=CMD_TIMEOUT)
    raw = child.before.decode("utf-8", errors="replace")
    lines = raw.split("\n")
    # Strip echoed command (if echo is on)
    if lines and cmd[:20] in lines[0]:
        lines = lines[1:]
    # Filter out marker, prompt lines, and empty lines
    lines = [l for l in lines
             if marker not in l
             and not l.strip().startswith("root@")
             and l.strip()]
    return "\n".join(lines).strip()


def main():
    iso = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ISO
    if not os.path.isfile(iso):
        print(f"[FAIL] ISO not found: {iso}")
        sys.exit(1)

    iso = os.path.abspath(iso)

    # Clean up stale socket
    if os.path.exists(QMP_SOCK):
        os.unlink(QMP_SOCK)

    # OVMF firmware for UEFI boot (same as Incus VMs)
    ovmf_code = "/usr/share/edk2/x64/OVMF_CODE.4m.fd"
    ovmf_vars = "/tmp/anklume-test-ovmf-vars.fd"
    ovmf_vars_src = "/usr/share/edk2/x64/OVMF_VARS.4m.fd"
    if not os.path.isfile(ovmf_code):
        print(f"[FAIL] OVMF firmware not found: {ovmf_code}")
        sys.exit(1)
    # Copy VARS file (QEMU needs a writable copy)
    subprocess.run(["cp", ovmf_vars_src, ovmf_vars], check=True)

    qemu_cmd = (
        f"qemu-system-x86_64"
        f" -m {MEMORY} -smp {CPUS} -enable-kvm"
        f" -drive if=pflash,format=raw,readonly=on,file={ovmf_code}"
        f" -drive if=pflash,format=raw,file={ovmf_vars}"
        f" -cdrom {iso}"
        f" -boot d"
        f" -nographic"
        f" -serial mon:stdio"
        f" -qmp unix:{QMP_SOCK},server,nowait"
        f" -no-reboot"
    )

    print(f"[INFO] Booting {os.path.basename(iso)} in QEMU...")
    print(f"[INFO] Timeout: {BOOT_TIMEOUT}s")

    child = pexpect.spawn(
        "/bin/bash", ["-c", qemu_cmd],
        timeout=BOOT_TIMEOUT,
        encoding=None,
        maxread=8192,
    )

    results = []

    try:
        # ── Wait for login prompt ──
        print("[....] Waiting for login prompt...")
        idx = child.expect(
            [b"login:", pexpect.TIMEOUT, pexpect.EOF],
            timeout=BOOT_TIMEOUT,
        )
        if idx != 0:
            print("[FAIL] Boot timed out — no login prompt")
            # Dump what we got
            print("--- Last output ---")
            print(child.before.decode("utf-8", errors="replace")[-2000:])
            child.terminate(force=True)
            sys.exit(1)

        print("[ OK ] Login prompt detected")
        results.append(("Boot to login prompt", "PASS", ""))

        # ── Login ──
        time.sleep(0.5)
        child.sendline(b"root")
        child.expect(b"assword:", timeout=LOGIN_TIMEOUT)
        time.sleep(0.3)
        child.sendline(ROOT_PASSWORD.encode())
        child.expect([b"#", b"\\$"], timeout=LOGIN_TIMEOUT)
        time.sleep(0.5)
        print("[ OK ] Logged in as root")
        results.append(("Root login", "PASS", ""))

        # Disable bracketed paste mode (Debian bash enables it, garbles output)
        child.sendline(b"bind 'set enable-bracketed-paste off' 2>/dev/null; stty -echo 2>/dev/null; export TERM=dumb")
        child.expect([b"#", b"\\$"], timeout=CMD_TIMEOUT)
        time.sleep(0.3)

        # Wait for systemd to finish booting before running tests
        child.sendline(b"systemctl is-system-running --wait 2>/dev/null; sleep 1; echo READY")
        child.expect(b"READY", timeout=60)
        time.sleep(0.5)

        # ── Validation tests ──
        tests = [
            ("Kernel running",       "uname -r"),
            ("Systemd PID 1",        "ps -p 1 -o comm= | grep -q systemd && echo PASS || echo FAIL"),
            ("Root is overlay",       "mount | grep 'on / ' | grep -q overlay && echo PASS || echo FAIL"),
            ("/etc/anklume exists",   "test -d /etc/anklume && echo PASS || echo FAIL"),
            ("Anklume repo present",  "test -f /opt/anklume/Makefile && echo PASS || echo FAIL"),
            ("Incus available",       "command -v incus >/dev/null && echo PASS || echo FAIL"),
            ("Ansible available",     "command -v ansible >/dev/null && echo PASS || echo FAIL"),
            ("Git available",         "command -v git >/dev/null && echo PASS || echo FAIL"),
            ("Make available",        "command -v make >/dev/null && echo PASS || echo FAIL"),
            ("Keyboard is fr",        "grep -q fr /etc/vconsole.conf && echo PASS || echo FAIL"),
            ("No incus-agent spam",   "! systemctl is-enabled incus-agent.service 2>/dev/null && echo PASS || echo FAIL"),
            ("Writable /tmp",         "touch /tmp/test-write && rm /tmp/test-write && echo PASS || echo FAIL"),
            ("Writable /root",        "touch /root/test-write && rm /root/test-write && echo PASS || echo FAIL"),
        ]

        for name, cmd in tests:
            try:
                output = run_cmd(child, cmd)
                if "PASS" in output:
                    status = "PASS"
                elif "FAIL" in output:
                    status = "FAIL"
                else:
                    # For info-only commands (like uname)
                    status = "INFO"
                results.append((name, status, output.split("\n")[-1]))
                tag = " OK " if status in ("PASS", "INFO") else "FAIL"
                print(f"[{tag}] {name}: {output.split(chr(10))[-1][:60]}")
            except pexpect.TIMEOUT:
                results.append((name, "TIMEOUT", ""))
                print(f"[FAIL] {name}: TIMEOUT")

        # ── Shutdown ──
        print("[INFO] Shutting down VM...")
        qmp_shutdown()
        try:
            child.expect(pexpect.EOF, timeout=30)
        except pexpect.TIMEOUT:
            child.terminate(force=True)

    except Exception as e:
        print(f"[FAIL] Unexpected error: {e}")
        child.terminate(force=True)
        sys.exit(1)
    finally:
        if os.path.exists(QMP_SOCK):
            os.unlink(QMP_SOCK)
        if os.path.exists(ovmf_vars):
            os.unlink(ovmf_vars)

    # ── Summary ──
    print()
    passed = sum(1 for _, s, _ in results if s in ("PASS", "INFO"))
    failed = sum(1 for _, s, _ in results if s in ("FAIL", "TIMEOUT"))
    total = len(results)
    print(f"{'='*50}")
    print(f"Results: {passed}/{total} passed, {failed} failed")
    print(f"{'='*50}")

    if failed:
        print("\nFailed tests:")
        for name, status, out in results:
            if status in ("FAIL", "TIMEOUT"):
                print(f"  - {name}: {status} {out}")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
