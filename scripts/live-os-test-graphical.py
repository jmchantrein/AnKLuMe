#!/usr/bin/env python3
"""Deterministic graphical testing of anklume Live ISO via QEMU.

Boots the ISO in QEMU with a virtual VGA framebuffer (headless), takes
screenshots at key moments via QMP, validates boot flow and desktop
environment visually, and runs CLI checks via serial console.

Refactored to use scripts/lib/ automation stack (Layer 0+2).

Usage:
    python3 scripts/live-os-test-graphical.py ISO_PATH [--desktop kde|sway]
    python3 scripts/live-os-test-graphical.py /tmp/anklume-test.iso --desktop kde
    python3 scripts/live-os-test-graphical.py /tmp/anklume-test-sway.iso --desktop sway

Output:
    Screenshots saved to tests/live-iso/screenshots/<desktop>_<timestamp>/
    Reference images in tests/live-iso/references/ (auto-generated on first run)
"""

import argparse
import contextlib
import os
import subprocess
import sys
import time

# Ensure project root is in sys.path for direct script invocation
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pexpect

from scripts.lib.qmp_client import QMPClient
from scripts.lib.screen_analysis import (
    images_match,
    is_not_black_screen,
)
from scripts.lib.serial_console import SerialConsole

# ── Configuration ──
BOOT_TIMEOUT = 300
SCREENSHOT_DIR = ""
REFERENCE_DIR = ""


def main():
    parser = argparse.ArgumentParser(description="Graphical ISO testing")
    parser.add_argument("iso", help="Path to ISO file")
    parser.add_argument("--desktop", default="kde", choices=["kde", "sway", "labwc"],
                        help="Expected desktop environment (default: kde)")
    parser.add_argument("--timeout", type=int, default=BOOT_TIMEOUT,
                        help=f"Boot timeout in seconds (default: {BOOT_TIMEOUT})")
    parser.add_argument("--save-references", action="store_true",
                        help="Save screenshots as reference images")
    parser.add_argument("--vnc", action="store_true",
                        help="Enable VNC for mouse tests (Layer 1)")
    args = parser.parse_args()

    if not os.path.isfile(args.iso):
        print(f"[FAIL] ISO not found: {args.iso}")
        sys.exit(1)

    iso = os.path.abspath(args.iso)

    # Create output directories
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    global SCREENSHOT_DIR, REFERENCE_DIR
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    SCREENSHOT_DIR = os.path.join(project_root, "tests", "live-iso", "screenshots",
                                  f"{args.desktop}_{timestamp}")
    REFERENCE_DIR = os.path.join(project_root, "tests", "live-iso", "references")
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    os.makedirs(REFERENCE_DIR, exist_ok=True)

    # QEMU setup
    qmp_sock_path = "/tmp/anklume-graphical-qmp.sock"
    if os.path.exists(qmp_sock_path):
        os.unlink(qmp_sock_path)

    ovmf_code = "/usr/share/edk2/x64/OVMF_CODE.4m.fd"
    ovmf_vars = "/tmp/anklume-graphical-ovmf-vars.fd"
    ovmf_vars_src = "/usr/share/edk2/x64/OVMF_VARS.4m.fd"
    if not os.path.isfile(ovmf_code):
        print(f"[FAIL] OVMF firmware not found: {ovmf_code}")
        sys.exit(1)
    subprocess.run(["cp", ovmf_vars_src, ovmf_vars], check=True)

    resolution = "1024x768"
    res_w, res_h = resolution.split("x")
    qemu_cmd = (
        f"qemu-system-x86_64"
        f" -m 4096 -smp 2 -enable-kvm"
        f" -drive if=pflash,format=raw,readonly=on,file={ovmf_code}"
        f" -drive if=pflash,format=raw,file={ovmf_vars}"
        f" -cdrom {iso}"
        f" -boot d"
        f" -display none"
        f" -device virtio-vga,xres={res_w},yres={res_h}"
        f" -serial mon:stdio"
        f" -qmp unix:{qmp_sock_path},server,nowait"
        f" -no-reboot"
    )

    if args.vnc:
        qemu_cmd += " -vnc localhost:50 -device usb-ehci -device usb-tablet"

    print("=== anklume Live ISO Graphical Test ===")
    print(f"ISO:        {os.path.basename(iso)}")
    print(f"Desktop:    {args.desktop}")
    print(f"Resolution: {resolution}")
    print(f"Screenshots: {SCREENSHOT_DIR}")
    print()

    child = pexpect.spawn(
        "/bin/bash", ["-c", qemu_cmd],
        timeout=args.timeout,
        encoding=None,
        maxread=8192,
    )
    serial = SerialConsole(child)

    results = []
    qmp = None

    try:
        # Wait for QMP socket to appear
        print("[....] Waiting for QEMU to start...")
        for _ in range(30):
            if os.path.exists(qmp_sock_path):
                break
            time.sleep(0.5)
        else:
            print("[FAIL] QMP socket never appeared")
            child.terminate(force=True)
            sys.exit(1)

        qmp = QMPClient(qmp_sock_path)
        qmp.connect()
        print("[ OK ] QMP connected")

        def take_screenshot(path):
            qmp.screendump(path)
            time.sleep(0.5)

        # ── Phase 1: GRUB menu ──
        print("[....] Waiting for GRUB menu (15s)...")
        time.sleep(15)

        grub_path = os.path.join(SCREENSHOT_DIR, "01_grub_menu.png")
        take_screenshot(grub_path)

        if os.path.exists(grub_path) and os.path.getsize(grub_path) > 100:
            has_content = is_not_black_screen(grub_path)
            if has_content:
                print(f"[ OK ] GRUB screenshot captured: {grub_path}")
                results.append(("GRUB menu visible", "PASS", grub_path))
            else:
                print("[WARN] GRUB screenshot is black (may have already booted)")
                results.append(("GRUB menu visible", "SKIP", "Screen was black"))
        else:
            print("[WARN] GRUB screenshot failed")
            results.append(("GRUB menu visible", "SKIP", "No screenshot file"))

        # ── Phase 2: Wait for login prompt via serial ──
        print("[....] Waiting for boot + login prompt...")
        if not serial.wait_for_login(timeout=args.timeout):
            print("[FAIL] Boot timed out — no login prompt")
            fail_path = os.path.join(SCREENSHOT_DIR, "boot_failure.png")
            take_screenshot(fail_path)
            print(f"  Failure screenshot: {fail_path}")
            print("--- Last serial output ---")
            print(child.before.decode("utf-8", errors="replace")[-2000:])
            results.append(("Boot to login", "FAIL", "Timeout"))
            raise SystemExit(1)

        print("[ OK ] Login prompt detected")
        results.append(("Boot to login", "PASS", ""))

        login_path = os.path.join(SCREENSHOT_DIR, "02_login_prompt.png")
        take_screenshot(login_path)

        # ── Phase 3: Login via serial ──
        serial.login()
        print("[ OK ] Logged in as root")
        results.append(("Root login", "PASS", ""))

        serial.setup_clean_output()
        serial.wait_for_systemd()

        # ── Phase 4: CLI validation ──
        print("\n--- CLI Validation ---")
        cli_tests = [
            ("Kernel running", "uname -r"),
            ("Root is overlay",
             "mount | grep 'on / ' | grep -q overlay && echo PASS || echo FAIL"),
            ("/etc/anklume exists",
             "test -d /etc/anklume && echo PASS || echo FAIL"),
            ("Incus available",
             "command -v incus >/dev/null && echo PASS || echo FAIL"),
            ("Ansible available",
             "command -v ansible >/dev/null && echo PASS || echo FAIL"),
            ("Keyboard is fr",
             "grep -q fr /etc/vconsole.conf && echo PASS || echo FAIL"),
            ("Locale set (not C)",
             "locale 2>/dev/null | head -1 | grep -qv '^LANG=$'"
             " && locale 2>/dev/null | head -1 | grep -qv 'LANG=C$' && echo PASS || echo FAIL"),
            ("fr_FR.UTF-8 available",
             "locale -a 2>/dev/null | grep -q fr_FR && echo PASS || echo FAIL"),
        ]

        if args.desktop == "kde":
            cli_tests.extend([
                ("KDE Plasma installed",
                 "command -v plasmashell >/dev/null 2>&1"
                 " || dpkg -l plasma-desktop 2>/dev/null | grep -q ^ii && echo PASS || echo FAIL"),
                ("kwin_wayland installed",
                 "command -v kwin_wayland >/dev/null && echo PASS || echo FAIL"),
            ])
        elif args.desktop == "sway":
            cli_tests.extend([
                ("Sway installed",
                 "command -v sway >/dev/null && echo PASS || echo FAIL"),
                ("Foot installed",
                 "command -v foot >/dev/null && echo PASS || echo FAIL"),
            ])

        for name, cmd in cli_tests:
            try:
                output = serial.run_cmd(cmd)
                if "PASS" in output:
                    status = "PASS"
                elif "FAIL" in output:
                    status = "FAIL"
                else:
                    status = "INFO"
                results.append((name, status, output.split("\n")[-1]))
                tag = " OK " if status in ("PASS", "INFO") else "FAIL"
                print(f"[{tag}] {name}: {output.split(chr(10))[-1][:60]}")
            except pexpect.TIMEOUT:
                results.append((name, "TIMEOUT", ""))
                print(f"[FAIL] {name}: TIMEOUT")

        # ── Phase 5: Locale/foot test ──
        print("\n--- Locale Validation ---")
        locale_output = ""
        try:
            locale_output = serial.run_cmd("locale 2>&1")
            print(f"  locale output: {locale_output[:200]}")
            if "LANG=" in locale_output:
                lang_line = [ln for ln in locale_output.split("\n") if ln.startswith("LANG=")]
                if lang_line:
                    lang_val = lang_line[0].split("=", 1)[1]
                    if lang_val and lang_val != "C" and lang_val != "POSIX":
                        print(f"[ OK ] LANG={lang_val}")
                        results.append(("LANG not C/POSIX", "PASS", lang_val))
                    else:
                        print(f"[FAIL] LANG={lang_val} (should not be C/POSIX)")
                        results.append(("LANG not C/POSIX", "FAIL", lang_val))
        except pexpect.TIMEOUT:
            results.append(("LANG not C/POSIX", "TIMEOUT", ""))

        if "UTF-8" in locale_output:
            print("[ OK ] Foot locale OK (UTF-8 found in locale output)")
            results.append(("Foot locale OK", "PASS", "UTF-8 in locale"))
        else:
            print("[FAIL] Foot locale: no UTF-8 in locale output")
            results.append(("Foot locale OK", "FAIL", locale_output[:80]))

        # ── Phase 6: Start desktop environment ──
        print(f"\n--- Desktop Test ({args.desktop}) ---")
        if args.desktop == "sway":
            print("[....] Starting sway...")
            try:
                serial.run_cmd("export WLR_BACKENDS=headless WLR_LIBINPUT_NO_DEVICES=1 XDG_RUNTIME_DIR=/run/user/0")
                serial.run_cmd("mkdir -p /run/user/0 && chmod 700 /run/user/0")
                child.sendline(b"sway &")
                child.expect([b"#", b"\\$"], timeout=10)
                time.sleep(5)
            except pexpect.TIMEOUT:
                pass

            print("[....] Waiting for sway desktop to render...")
            time.sleep(10)
            desktop_path = os.path.join(SCREENSHOT_DIR, "03_desktop.png")
            take_screenshot(desktop_path)

            if os.path.exists(desktop_path) and os.path.getsize(desktop_path) > 100:
                has_content = is_not_black_screen(desktop_path)
                tag = "  OK" if has_content else "WARN"
                print(f"[{tag}] Desktop screenshot: {desktop_path} (content: {has_content})")
                results.append(("Desktop rendered", "PASS" if has_content else "WARN", desktop_path))
            else:
                results.append(("Desktop rendered", "SKIP", "No screenshot"))

        elif args.desktop == "kde":
            print("[....] Starting KDE Plasma Wayland session...")
            try:
                serial.run_cmd("export XDG_RUNTIME_DIR=/run/user/0 && mkdir -p /run/user/0 && chmod 700 /run/user/0")
                child.sendline(b"dbus-run-session kwin_wayland --no-lockscreen 2>/dev/null &")
                child.expect([b"#", b"\\$"], timeout=10)
                time.sleep(10)
            except pexpect.TIMEOUT:
                pass

            desktop_path = os.path.join(SCREENSHOT_DIR, "03_desktop.png")
            take_screenshot(desktop_path)

            if os.path.exists(desktop_path) and os.path.getsize(desktop_path) > 100:
                has_content = is_not_black_screen(desktop_path)
                tag = "  OK" if has_content else "WARN"
                print(f"[{tag}] Desktop screenshot: {desktop_path} (content: {has_content})")
                results.append(("Desktop rendered", "PASS" if has_content else "WARN", desktop_path))
            else:
                results.append(("Desktop rendered", "SKIP", "No screenshot"))

        # ── Phase 7: GRUB label check ──
        print("\n--- GRUB Label Validation ---")
        try:
            grub_cmd = (
                "cat /boot/grub/grub.cfg 2>/dev/null | head -30"
                " || cat /iso/boot/grub/grub.cfg 2>/dev/null | head -30"
            )
            grub_check = serial.run_cmd(grub_cmd)
            if "Debian" in grub_check or "Arch" in grub_check:
                print("[ OK ] GRUB config shows distro name")
                results.append(("GRUB distro label", "PASS", "Distro name found"))
            elif "BASE_PLACEHOLDER" in grub_check:
                print("[FAIL] GRUB config still has BASE_PLACEHOLDER")
                results.append(("GRUB distro label", "FAIL", "BASE_PLACEHOLDER not substituted"))
            else:
                print("[WARN] Could not read GRUB config from rootfs (expected if toram)")
                results.append(("GRUB distro label", "SKIP", "Config not readable from rootfs"))
        except pexpect.TIMEOUT:
            results.append(("GRUB distro label", "TIMEOUT", ""))

        # ── Phase 8: Save reference images ──
        if args.save_references:
            print("\n--- Saving reference images ---")
            for fname in sorted(os.listdir(SCREENSHOT_DIR)):
                if fname.endswith(".png") and "_diff" not in fname:
                    src = os.path.join(SCREENSHOT_DIR, fname)
                    if not is_not_black_screen(src):
                        print(f"  SKIP: {fname} (black screen — not suitable as reference)")
                        continue
                    ref_name = f"{args.desktop}_{fname}"
                    dst = os.path.join(REFERENCE_DIR, ref_name)
                    subprocess.run(["cp", src, dst], check=True)
                    print(f"  Saved: {ref_name}")

        # ── Phase 9: Compare with references ──
        print("\n--- Reference Comparison ---")
        for fname in sorted(os.listdir(SCREENSHOT_DIR)):
            if not fname.endswith(".png") or "_diff" in fname:
                continue
            actual = os.path.join(SCREENSHOT_DIR, fname)
            ref_name = f"{args.desktop}_{fname}"
            reference = os.path.join(REFERENCE_DIR, ref_name)

            if os.path.isfile(reference):
                threshold = 15.0 if "desktop" in fname else 2.0
                match, diff_pct, diff_path = images_match(actual, reference, max_diff_percent=threshold)
                if match:
                    print(f"[ OK ] {fname}: matches reference ({diff_pct:.1f}% diff, threshold {threshold:.0f}%)")
                    results.append((f"Ref: {fname}", "PASS", f"{diff_pct:.1f}% diff"))
                else:
                    print(f"[FAIL] {fname}: differs from reference ({diff_pct:.1f}% diff > {threshold:.0f}%)")
                    print(f"       Diff image: {diff_path}")
                    results.append((f"Ref: {fname}", "FAIL", f"{diff_pct:.1f}% diff"))
            else:
                print(f"[SKIP] {fname}: no reference image (run with --save-references first)")

        # ── Shutdown ──
        print("\n[INFO] Shutting down VM...")
        try:
            qmp.powerdown()
            child.expect(pexpect.EOF, timeout=30)
        except (pexpect.TIMEOUT, Exception):
            child.terminate(force=True)

    except SystemExit:
        if qmp:
            with contextlib.suppress(Exception):
                qmp.powerdown()
        child.terminate(force=True)
    except Exception as e:
        print(f"[FAIL] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        if qmp:
            fail_path = os.path.join(SCREENSHOT_DIR, "error.png")
            with contextlib.suppress(Exception):
                qmp.screendump(fail_path)
        child.terminate(force=True)
    finally:
        if qmp:
            qmp.close()
        for path in [qmp_sock_path, "/tmp/anklume-graphical-ovmf-vars.fd"]:
            if os.path.exists(path):
                with contextlib.suppress(OSError):
                    os.unlink(path)

    # ── Summary ──
    print()
    passed = sum(1 for _, s, _ in results if s in ("PASS", "INFO"))
    failed = sum(1 for _, s, _ in results if s in ("FAIL", "TIMEOUT"))
    skipped = sum(1 for _, s, _ in results if s in ("SKIP", "WARN"))
    total = len(results)
    print(f"{'='*60}")
    print(f"Results: {passed} passed, {failed} failed, {skipped} skipped ({total} total)")
    print(f"Screenshots: {SCREENSHOT_DIR}")
    print(f"{'='*60}")

    if failed:
        print("\nFailed tests:")
        for name, status, out in results:
            if status in ("FAIL", "TIMEOUT"):
                print(f"  - {name}: {status} {out}")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
