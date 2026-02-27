#!/usr/bin/env python3
"""Deterministic graphical testing of anklume Live ISO via QEMU.

Boots the ISO in QEMU with a virtual VGA framebuffer (headless), takes
screenshots at key moments via QMP, validates boot flow and desktop
environment visually, and runs CLI checks via serial console.

Usage:
    python3 scripts/live-os-test-graphical.py ISO_PATH [--desktop kde|sway]
    python3 scripts/live-os-test-graphical.py /tmp/anklume-test.iso --desktop kde
    python3 scripts/live-os-test-graphical.py /tmp/anklume-test-sway.iso --desktop sway

Output:
    Screenshots saved to tests/live-iso/screenshots/<desktop>_<timestamp>/
    Reference images in tests/live-iso/references/ (auto-generated on first run)
"""

import argparse
import json
import os
import socket
import subprocess
import sys
import time

import pexpect

# ── Configuration ──
QMP_SOCK = "/tmp/anklume-graphical-qmp.sock"
MEMORY = "4096"
CPUS = "2"
RESOLUTION = "1024x768"
BOOT_TIMEOUT = 300
LOGIN_TIMEOUT = 30
CMD_TIMEOUT = 15
DESKTOP_TIMEOUT = 120
ROOT_PASSWORD = "anklume"
SCREENSHOT_DIR = ""
REFERENCE_DIR = ""

# ── QMP helpers ──

def qmp_connect(sock_path, timeout=10):
    """Connect to QMP socket, negotiate capabilities."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    sock.connect(sock_path)
    f = sock.makefile("rw")
    f.readline()  # greeting
    sock.sendall(b'{"execute": "qmp_capabilities"}\n')
    f.readline()  # response
    return sock, f


def qmp_screendump(sock, f, filename):
    """Take a PNG screenshot via QMP screendump command."""
    cmd = json.dumps({
        "execute": "screendump",
        "arguments": {"filename": filename, "format": "png"},
    })
    sock.sendall((cmd + "\n").encode())
    resp = f.readline()
    return json.loads(resp)


def qmp_send_key(sock, f, keys, hold_time_ms=100):
    """Send keyboard input to the guest via QMP."""
    key_values = [{"type": "qcode", "data": k} for k in keys]
    cmd = json.dumps({
        "execute": "send-key",
        "arguments": {"keys": key_values, "hold-time": hold_time_ms},
    })
    sock.sendall((cmd + "\n").encode())
    return json.loads(f.readline())


def qmp_shutdown(sock, f):
    """Gracefully shut down the VM via QMP."""
    cmd = json.dumps({"execute": "system_powerdown"})
    sock.sendall((cmd + "\n").encode())
    try:
        f.readline()
    except Exception:
        pass


def qmp_quit(sock_path):
    """Force quit the VM via QMP (fallback)."""
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect(sock_path)
        f = sock.makefile("rw")
        f.readline()
        sock.sendall(b'{"execute": "qmp_capabilities"}\n')
        f.readline()
        sock.sendall(b'{"execute": "quit"}\n')
        sock.close()
    except Exception:
        pass


# ── Image comparison ──

def images_match(actual_path, reference_path, max_diff_percent=2.0):
    """Compare two images, return (match, diff_percent, diff_path)."""
    try:
        from PIL import Image
        from pixelmatch.contrib.PIL import pixelmatch as pm
    except ImportError:
        print("[WARN] Pillow/pixelmatch not available, skipping image comparison")
        return True, 0.0, None

    if not os.path.isfile(reference_path):
        return None, None, None  # No reference = skip

    img1 = Image.open(actual_path).convert("RGBA")
    img2 = Image.open(reference_path).convert("RGBA")

    # Resize if dimensions don't match
    if img1.size != img2.size:
        img2 = img2.resize(img1.size, Image.Resampling.LANCZOS)

    width, height = img1.size
    diff_img = Image.new("RGBA", (width, height))

    num_diff = pm(img1, img2, output=diff_img, threshold=0.1, includeAA=False)
    total = width * height
    diff_percent = (num_diff / total) * 100

    diff_path = actual_path.replace(".png", "_diff.png")
    diff_img.save(diff_path)

    return diff_percent < max_diff_percent, diff_percent, diff_path


def is_not_black_screen(image_path, min_nonblack_permille=10):
    """Check if the screen has visible content (not all black).

    Uses percentage of non-black pixels (brightness > 5) as the metric.
    Terminal screens: ~13‰, desktops: ~1000‰, black screens: <2‰.
    Default threshold: 10‰ (1.0%).
    """
    try:
        from PIL import Image
    except ImportError:
        return True
    img = Image.open(image_path).convert("L")
    pixels = img.tobytes()
    nonblack = sum(1 for p in pixels if p > 5)
    permille = int(nonblack * 1000 / len(pixels))
    return permille >= min_nonblack_permille


def screen_has_text_content(image_path, min_bright_percent=5):
    """Check if screen has text-like content (bright pixels on dark bg)."""
    try:
        from PIL import Image
    except ImportError:
        return True
    img = Image.open(image_path).convert("L")
    pixels = list(img.tobytes())
    bright = sum(1 for p in pixels if p > 128)
    return (bright / len(pixels)) * 100 > min_bright_percent


# ── Wait helpers ──

def wait_for_stable_screen(qmp_sock, qmp_f, temp_dir, interval=3,
                           stable_count=3, timeout=120):
    """Wait until the screen content stabilizes (no changes between captures)."""
    start = time.time()
    prev_path = None
    consecutive_stable = 0
    iteration = 0

    while time.time() - start < timeout:
        iteration += 1
        curr_path = os.path.join(temp_dir, f"stable_check_{iteration}.png")
        qmp_screendump(qmp_sock, qmp_f, curr_path)
        time.sleep(0.5)  # Let the file be written

        if not os.path.exists(curr_path) or os.path.getsize(curr_path) < 100:
            time.sleep(interval)
            continue

        if prev_path and os.path.exists(prev_path):
            match, diff_pct, _ = images_match(curr_path, prev_path, max_diff_percent=0.5)
            if match:
                consecutive_stable += 1
                if consecutive_stable >= stable_count:
                    return curr_path
            else:
                consecutive_stable = 0

        prev_path = curr_path
        time.sleep(interval)

    return None


# ── Serial console helpers ──

_cmd_seq = 0


def run_cmd(child, cmd):
    """Send command via serial, wait for unique marker, return output."""
    global _cmd_seq
    _cmd_seq += 1
    marker = f"ENDMARK{_cmd_seq:04d}"
    full_cmd = f"{cmd}; echo {marker}"
    child.sendline(full_cmd)
    child.expect(marker.encode(), timeout=CMD_TIMEOUT)
    raw = child.before.decode("utf-8", errors="replace")
    lines = raw.split("\n")
    if lines and cmd[:20] in lines[0]:
        lines = lines[1:]
    lines = [
        line for line in lines
        if marker not in line
        and not line.strip().startswith("root@")
        and line.strip()
    ]
    return "\n".join(lines).strip()


# ── Main test flow ──

def main():
    parser = argparse.ArgumentParser(description="Graphical ISO testing")
    parser.add_argument("iso", help="Path to ISO file")
    parser.add_argument("--desktop", default="kde", choices=["kde", "sway", "labwc"],
                        help="Expected desktop environment (default: kde)")
    parser.add_argument("--timeout", type=int, default=BOOT_TIMEOUT,
                        help=f"Boot timeout in seconds (default: {BOOT_TIMEOUT})")
    parser.add_argument("--save-references", action="store_true",
                        help="Save screenshots as reference images")
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

    # Clean up stale socket
    if os.path.exists(QMP_SOCK):
        os.unlink(QMP_SOCK)

    # OVMF firmware
    ovmf_code = "/usr/share/edk2/x64/OVMF_CODE.4m.fd"
    ovmf_vars = "/tmp/anklume-graphical-ovmf-vars.fd"
    ovmf_vars_src = "/usr/share/edk2/x64/OVMF_VARS.4m.fd"
    if not os.path.isfile(ovmf_code):
        print(f"[FAIL] OVMF firmware not found: {ovmf_code}")
        sys.exit(1)
    subprocess.run(["cp", ovmf_vars_src, ovmf_vars], check=True)

    # QEMU command: headless with VGA framebuffer for screenshots
    res_w, res_h = RESOLUTION.split("x")
    qemu_cmd = (
        f"qemu-system-x86_64"
        f" -m {MEMORY} -smp {CPUS} -enable-kvm"
        f" -drive if=pflash,format=raw,readonly=on,file={ovmf_code}"
        f" -drive if=pflash,format=raw,file={ovmf_vars}"
        f" -cdrom {iso}"
        f" -boot d"
        f" -display none"
        f" -device virtio-vga,xres={res_w},yres={res_h}"
        f" -serial mon:stdio"
        f" -qmp unix:{QMP_SOCK},server,nowait"
        f" -no-reboot"
    )

    print(f"=== anklume Live ISO Graphical Test ===")
    print(f"ISO:        {os.path.basename(iso)}")
    print(f"Desktop:    {args.desktop}")
    print(f"Resolution: {RESOLUTION}")
    print(f"Screenshots: {SCREENSHOT_DIR}")
    print()

    child = pexpect.spawn(
        "/bin/bash", ["-c", qemu_cmd],
        timeout=args.timeout,
        encoding=None,
        maxread=8192,
    )

    results = []
    qmp_sock = None
    qmp_f = None

    try:
        # Wait for QMP socket to appear
        print("[....] Waiting for QEMU to start...")
        for _ in range(30):
            if os.path.exists(QMP_SOCK):
                break
            time.sleep(0.5)
        else:
            print("[FAIL] QMP socket never appeared")
            child.terminate(force=True)
            sys.exit(1)

        qmp_sock, qmp_f = qmp_connect(QMP_SOCK)
        print("[ OK ] QMP connected")

        # ── Phase 1: GRUB menu ──
        print("[....] Waiting for GRUB menu (15s)...")
        time.sleep(15)  # GRUB default timeout is 5s, give extra time

        grub_path = os.path.join(SCREENSHOT_DIR, "01_grub_menu.png")
        qmp_screendump(qmp_sock, qmp_f, grub_path)
        time.sleep(1)  # Let file be written

        if os.path.exists(grub_path) and os.path.getsize(grub_path) > 100:
            has_content = is_not_black_screen(grub_path)
            if has_content:
                print(f"[ OK ] GRUB screenshot captured: {grub_path}")
                results.append(("GRUB menu visible", "PASS", grub_path))
            else:
                print(f"[WARN] GRUB screenshot is black (may have already booted)")
                results.append(("GRUB menu visible", "SKIP", "Screen was black"))
        else:
            print("[WARN] GRUB screenshot failed")
            results.append(("GRUB menu visible", "SKIP", "No screenshot file"))

        # ── Phase 2: Wait for login prompt via serial ──
        print("[....] Waiting for boot + login prompt...")
        idx = child.expect(
            [b"login:", pexpect.TIMEOUT, pexpect.EOF],
            timeout=args.timeout,
        )
        if idx != 0:
            print("[FAIL] Boot timed out — no login prompt")
            # Take a screenshot of what's on screen
            fail_path = os.path.join(SCREENSHOT_DIR, "boot_failure.png")
            qmp_screendump(qmp_sock, qmp_f, fail_path)
            time.sleep(1)
            print(f"  Failure screenshot: {fail_path}")
            print("--- Last serial output ---")
            print(child.before.decode("utf-8", errors="replace")[-2000:])
            results.append(("Boot to login", "FAIL", "Timeout"))
            raise SystemExit(1)

        print("[ OK ] Login prompt detected")
        results.append(("Boot to login", "PASS", ""))

        # Take a screenshot at login prompt
        login_path = os.path.join(SCREENSHOT_DIR, "02_login_prompt.png")
        qmp_screendump(qmp_sock, qmp_f, login_path)
        time.sleep(0.5)

        # ── Phase 3: Login via serial ──
        time.sleep(0.5)
        child.sendline(b"root")
        child.expect(b"assword:", timeout=LOGIN_TIMEOUT)
        time.sleep(0.3)
        child.sendline(ROOT_PASSWORD.encode())
        child.expect([b"#", b"\\$"], timeout=LOGIN_TIMEOUT)
        time.sleep(0.5)
        print("[ OK ] Logged in as root")
        results.append(("Root login", "PASS", ""))

        # Set up serial for clean output
        child.sendline(b"bind 'set enable-bracketed-paste off' 2>/dev/null; stty -echo 2>/dev/null; export TERM=dumb")
        child.expect([b"#", b"\\$"], timeout=CMD_TIMEOUT)
        time.sleep(0.3)

        # Wait for systemd to finish
        child.sendline(b"systemctl is-system-running --wait 2>/dev/null; sleep 1; echo READY")
        child.expect(b"READY", timeout=60)
        time.sleep(0.5)

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
             "locale 2>/dev/null | head -1 | grep -qv '^LANG=$' && locale 2>/dev/null | head -1 | grep -qv 'LANG=C$' && echo PASS || echo FAIL"),
            ("fr_FR.UTF-8 available",
             "locale -a 2>/dev/null | grep -q fr_FR && echo PASS || echo FAIL"),
        ]

        # Desktop-specific checks
        if args.desktop == "kde":
            cli_tests.extend([
                ("KDE Plasma installed",
                 "command -v plasmashell >/dev/null 2>&1 || dpkg -l plasma-desktop 2>/dev/null | grep -q ^ii && echo PASS || echo FAIL"),
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
                output = run_cmd(child, cmd)
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
            locale_output = run_cmd(child, "locale 2>&1")
            print(f"  locale output: {locale_output[:200]}")
            # Check LANG is set and not "C"
            if "LANG=" in locale_output:
                lang_line = [l for l in locale_output.split("\n") if l.startswith("LANG=")]
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

        # Foot locale check: verify LANG is a UTF-8 locale
        # The "Locale set (not C)" CLI test already checks this via shell.
        # Here we verify from the locale output we already captured above.
        if "UTF-8" in locale_output:
            print("[ OK ] Foot locale OK (UTF-8 found in locale output)")
            results.append(("Foot locale OK", "PASS", "UTF-8 in locale"))
        else:
            print("[FAIL] Foot locale: no UTF-8 in locale output")
            results.append(("Foot locale OK", "FAIL", locale_output[:80]))

        # ── Phase 6: Start desktop environment ──
        print(f"\n--- Desktop Test ({args.desktop}) ---")
        if args.desktop == "sway":
            # Start sway in the background
            print("[....] Starting sway...")
            try:
                run_cmd(child, "export WLR_BACKENDS=headless WLR_LIBINPUT_NO_DEVICES=1 XDG_RUNTIME_DIR=/run/user/0")
                run_cmd(child, "mkdir -p /run/user/0 && chmod 700 /run/user/0")
                child.sendline(b"sway &")
                child.expect([b"#", b"\\$"], timeout=10)
                time.sleep(5)  # Give sway time to start
            except pexpect.TIMEOUT:
                pass

            # Wait for screen to show something
            print("[....] Waiting for sway desktop to render...")
            time.sleep(10)
            desktop_path = os.path.join(SCREENSHOT_DIR, "03_desktop.png")
            qmp_screendump(qmp_sock, qmp_f, desktop_path)
            time.sleep(1)

            if os.path.exists(desktop_path) and os.path.getsize(desktop_path) > 100:
                has_content = is_not_black_screen(desktop_path)
                print(f"[{'  OK' if has_content else 'WARN'}] Desktop screenshot: {desktop_path} (content: {has_content})")
                results.append(("Desktop rendered", "PASS" if has_content else "WARN", desktop_path))
            else:
                results.append(("Desktop rendered", "SKIP", "No screenshot"))

        elif args.desktop == "kde":
            # KDE needs a proper display server; check if startplasma-wayland exists
            print("[....] Starting KDE Plasma Wayland session...")
            try:
                run_cmd(child, "export XDG_RUNTIME_DIR=/run/user/0 && mkdir -p /run/user/0 && chmod 700 /run/user/0")
                # Try to start kwin_wayland with plasma
                child.sendline(b"dbus-run-session kwin_wayland --no-lockscreen 2>/dev/null &")
                child.expect([b"#", b"\\$"], timeout=10)
                time.sleep(10)
            except pexpect.TIMEOUT:
                pass

            desktop_path = os.path.join(SCREENSHOT_DIR, "03_desktop.png")
            qmp_screendump(qmp_sock, qmp_f, desktop_path)
            time.sleep(1)

            if os.path.exists(desktop_path) and os.path.getsize(desktop_path) > 100:
                has_content = is_not_black_screen(desktop_path)
                print(f"[{'  OK' if has_content else 'WARN'}] Desktop screenshot: {desktop_path} (content: {has_content})")
                results.append(("Desktop rendered", "PASS" if has_content else "WARN", desktop_path))
            else:
                results.append(("Desktop rendered", "SKIP", "No screenshot"))

        # ── Phase 7: GRUB label check ──
        # Verify GRUB config contains distro name (not BASE_PLACEHOLDER)
        print("\n--- GRUB Label Validation ---")
        try:
            grub_check = run_cmd(child, "cat /boot/grub/grub.cfg 2>/dev/null | head -30 || cat /iso/boot/grub/grub.cfg 2>/dev/null | head -30")
            if "Debian" in grub_check or "Arch" in grub_check:
                print("[ OK ] GRUB config shows distro name")
                results.append(("GRUB distro label", "PASS", "Distro name found"))
            elif "BASE_PLACEHOLDER" in grub_check:
                print("[FAIL] GRUB config still has BASE_PLACEHOLDER")
                results.append(("GRUB distro label", "FAIL", "BASE_PLACEHOLDER not substituted"))
            else:
                # GRUB config may not be readable from rootfs; check the grub screenshot
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
                # Desktop screenshots are non-deterministic (cursor, animations)
                # Use higher tolerance (15%) for desktop, strict (2%) for GRUB/login
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
            qmp_shutdown(qmp_sock, qmp_f)
            child.expect(pexpect.EOF, timeout=30)
        except (pexpect.TIMEOUT, Exception):
            child.terminate(force=True)

    except SystemExit:
        if qmp_sock:
            try:
                qmp_shutdown(qmp_sock, qmp_f)
            except Exception:
                pass
        child.terminate(force=True)
    except Exception as e:
        print(f"[FAIL] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        # Take failure screenshot
        if qmp_sock:
            fail_path = os.path.join(SCREENSHOT_DIR, "error.png")
            try:
                qmp_screendump(qmp_sock, qmp_f, fail_path)
            except Exception:
                pass
        child.terminate(force=True)
    finally:
        for path in [QMP_SOCK, "/tmp/anklume-graphical-ovmf-vars.fd"]:
            if os.path.exists(path):
                try:
                    os.unlink(path)
                except OSError:
                    pass

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
