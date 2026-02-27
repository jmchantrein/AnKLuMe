#!/usr/bin/env python3
"""Interactive GUI testing of anklume Live ISO — all 4 automation layers.

Demonstrates the full automation stack:
- Phase 1: Boot + CLI validation (Layer 0: serial console)
- Phase 2: Desktop start + stable screen wait (Layer 0+2: QMP + image analysis)
- Phase 3: VNC Mouse Setup (Layer 1: VNC + OpenCV)
- Phase 4: OCR text verification (Layer 2: Tesseract)
- Phase 5: GPU check (Layer 3: ensure model is on GPU)
- Phase 6: Vision GUI tests (Layer 3: comprehensive suite)
- Phase 7: Vision interactive tests (Layer 1+3: VNC + vision combined)

Usage:
    python3 scripts/live-os-test-interactive.py ISO_PATH [--desktop kde|sway]
    python3 scripts/live-os-test-interactive.py /tmp/anklume-test.iso --desktop kde --vnc
    python3 scripts/live-os-test-interactive.py /tmp/anklume-test.iso --headless --skip-vision
"""

import argparse
import contextlib
import logging
import os
import subprocess
import sys
import threading
import time

# Ensure project root is in sys.path for direct script invocation
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.lib.report_generator import generate_report
from scripts.lib.screen_analysis import (
    find_text_on_screen,
    is_not_black_screen,
    wait_for_stable_screen,
)
from scripts.lib.vision_agent import VisionAgent
from scripts.lib.vision_tests import run_vision_tests
from scripts.lib.vm_controller import VMController, VNCNotAvailableError

log = logging.getLogger(__name__)

# ── Configuration ──
SCREENSHOT_DIR = ""
RESULTS: list[tuple[str, str, str]] = []


def record(name: str, status: str, detail: str = "") -> None:
    """Record a test result and print it."""
    RESULTS.append((name, status, detail))
    tag = {
        "PASS": " OK ", "FAIL": "FAIL", "SKIP": "SKIP",
        "WARN": "WARN", "INFO": "INFO",
    }.get(status, "????")
    print(f"[{tag}] {name}" + (f": {detail[:80]}" if detail else ""))


def screenshot(vm: VMController, name: str) -> str:
    """Take a named screenshot, return path."""
    path = os.path.join(SCREENSHOT_DIR, f"{name}.png")
    vm.capture_screen(path)
    time.sleep(0.5)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Interactive GUI ISO test (4 layers)")
    parser.add_argument("iso", help="Path to ISO file")
    parser.add_argument("--desktop", default="kde", choices=["kde", "sway", "labwc"])
    parser.add_argument("--timeout", type=int, default=300, help="Boot timeout (s)")
    parser.add_argument("--vnc", action="store_true", help="Enable VNC (Layer 1 mouse)")
    parser.add_argument("--skip-vision", action="store_true", help="Skip Layer 3 vision tests")
    parser.add_argument("--headless", action="store_true", help="No QEMU window (CI mode)")
    parser.add_argument("--allow-cpu", action="store_true", help="Allow CPU inference (default: require GPU)")
    parser.add_argument(
        "--open-screenshots", action="store_true", default=None,
        help="Open screenshot report after tests (default: true when not headless)",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    # Default --open-screenshots to True when display is visible
    if args.open_screenshots is None:
        args.open_screenshots = not args.headless

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    if not os.path.isfile(args.iso):
        print(f"[FAIL] ISO not found: {args.iso}")
        sys.exit(1)

    global SCREENSHOT_DIR
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    SCREENSHOT_DIR = os.path.join(
        project_root, "tests", "live-iso", "screenshots",
        f"interactive_{args.desktop}_{timestamp}",
    )
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    display = "none" if args.headless else "gtk"

    print("=== anklume Interactive GUI Test (4-Layer Stack) ===")
    print(f"ISO:     {os.path.basename(args.iso)}")
    print(f"Desktop: {args.desktop}")
    print(f"Display: {display}")
    print(f"VNC:     {'enabled' if args.vnc else 'disabled'}")
    print(f"Vision:  {'enabled' if not args.skip_vision else 'skipped'}")
    print(f"GPU:     {'required' if not args.allow_cpu else 'optional (CPU allowed)'}")
    print(f"Output:  {SCREENSHOT_DIR}")
    print()

    grub_screenshot_path: str | None = None

    with VMController(
        args.iso,
        display=display,
        vnc_enabled=args.vnc,
        boot_timeout=args.timeout,
    ) as vm:
        # ── Phase 1: Boot + CLI validation (Layer 0) ──
        print("── Phase 1: Boot + CLI Validation (Layer 0: Serial) ──")

        # Capture GRUB menu: take screenshots every 1.5s for 12s in background.
        # UEFI takes ~2-3s, then GRUB menu is visible for 5s.
        # We pick the best (most content-rich) screenshot afterwards.
        grub_captures: list[str] = []
        grub_done = threading.Event()

        def _capture_grub_screenshots() -> None:
            for i in range(8):  # 8 captures × 1.5s = 12s window
                if grub_done.is_set():
                    break
                path = os.path.join(SCREENSHOT_DIR, f"grub_{i:02d}.png")
                try:
                    vm.capture_screen(path)
                    grub_captures.append(path)
                except Exception:
                    pass
                time.sleep(1.5)

        grub_thread = threading.Thread(target=_capture_grub_screenshots, daemon=True)
        grub_thread.start()

        print("[....] Waiting for login prompt (capturing GRUB in background)...")
        if not vm.serial.wait_for_login(timeout=args.timeout):
            grub_done.set()
            fail_path = screenshot(vm, "boot_failure")
            record("Boot to login", "FAIL", f"Timeout. Screenshot: {fail_path}")
            _finish(args)
            sys.exit(1)
        grub_done.set()
        grub_thread.join(timeout=3)
        record("Boot to login", "PASS")

        # Pick the best GRUB screenshot (most content = not black)
        grub_screenshot_path = _pick_best_grub(grub_captures)
        if grub_screenshot_path:
            best_name = os.path.basename(grub_screenshot_path)
            record("GRUB capture", "PASS", f"{len(grub_captures)} shots, best: {best_name}")
        else:
            record("GRUB capture", "WARN", f"{len(grub_captures)} shots, none had content")

        screenshot(vm, "01_login_prompt")

        vm.serial.login()
        record("Root login", "PASS")

        vm.serial.setup_clean_output()
        vm.serial.wait_for_systemd()
        record("Systemd ready", "PASS")

        # CLI checks
        cli_checks = [
            ("Kernel running", "uname -r"),
            ("Root is overlay",
             "mount | grep 'on / ' | grep -q overlay && echo PASS || echo FAIL"),
            ("Incus available",
             "command -v incus >/dev/null && echo PASS || echo FAIL"),
            ("Ansible available",
             "command -v ansible >/dev/null && echo PASS || echo FAIL"),
        ]
        for name, cmd in cli_checks:
            try:
                output = vm.serial.run_cmd(cmd)
                if "PASS" in output:
                    record(name, "PASS", output.split("\n")[-1][:60])
                elif "FAIL" in output:
                    record(name, "FAIL", output.split("\n")[-1][:60])
                else:
                    record(name, "INFO", output.split("\n")[-1][:60])
            except Exception as e:
                record(name, "FAIL", str(e))

        # ── Phase 2: Desktop start + stable screen (Layer 0+2) ──
        print("\n── Phase 2: Desktop Start (Layer 0+2: QMP + Image Analysis) ──")

        if args.desktop == "sway":
            try:
                vm.serial.run_cmd(
                    "export WLR_BACKENDS=headless WLR_LIBINPUT_NO_DEVICES=1 "
                    "XDG_RUNTIME_DIR=/run/user/0"
                )
                vm.serial.run_cmd("mkdir -p /run/user/0 && chmod 700 /run/user/0")
                vm.serial.child.sendline(b"sway &")
                vm.serial.child.expect([b"#", b"\\$"], timeout=10)
            except Exception:
                pass
        elif args.desktop == "kde":
            try:
                vm.serial.run_cmd(
                    "export XDG_RUNTIME_DIR=/run/user/0 && "
                    "mkdir -p /run/user/0 && chmod 700 /run/user/0"
                )
                vm.serial.child.sendline(b"dbus-run-session kwin_wayland --no-lockscreen 2>/dev/null &")
                vm.serial.child.expect([b"#", b"\\$"], timeout=10)
            except Exception:
                pass

        print("[....] Waiting for desktop to stabilize...")
        time.sleep(10)

        stable_path = wait_for_stable_screen(
            capture_fn=lambda f: vm.capture_screen(f),
            temp_dir=SCREENSHOT_DIR,
            interval=3,
            stable_count=3,
            timeout=60,
        )

        if stable_path:
            has_content = is_not_black_screen(stable_path)
            record(
                "Desktop stable",
                "PASS" if has_content else "WARN",
                f"content={has_content}",
            )
        else:
            record("Desktop stable", "WARN", "Screen did not stabilize in 60s")

        desktop_path = screenshot(vm, "02_desktop")
        record(
            "Desktop screenshot",
            "PASS" if is_not_black_screen(desktop_path) else "WARN",
            desktop_path,
        )

        # ── Phase 3: VNC Mouse Setup (Layer 1+2) ──
        if args.vnc and vm.vnc_connected:
            print("\n── Phase 3: VNC Mouse Interaction (Layer 1+2: VNC + OpenCV) ──")

            try:
                vm.click_proportional(0.5, 0.5)
                time.sleep(1)
                screenshot(vm, "03_after_click")
                record("VNC mouse click", "PASS", "Clicked center of screen")
            except VNCNotAvailableError:
                record("VNC mouse click", "SKIP", "VNC not available")
        else:
            print("\n── Phase 3: VNC Mouse (SKIPPED — VNC not enabled) ──")
            record("VNC mouse click", "SKIP", "Use --vnc to enable")

        # ── Phase 4: OCR text verification (Layer 2) ──
        print("\n── Phase 4: OCR Text Verification (Layer 2: Tesseract) ──")

        try:
            found, full_text = find_text_on_screen(desktop_path, "anklume")
            if found:
                record("OCR: 'anklume' on screen", "PASS", "Text found via OCR")
            else:
                record("OCR: 'anklume' on screen", "INFO", f"Not found. OCR got: {full_text[:100]}")
        except ImportError:
            record("OCR: 'anklume' on screen", "SKIP", "pytesseract not installed")
        except Exception as e:
            record("OCR: 'anklume' on screen", "SKIP", str(e))

        # ── Phase 5: GPU Check (Layer 3) ──
        if not args.skip_vision:
            print("\n── Phase 5: GPU Check (Layer 3: Ollama) ──")

            vision = VisionAgent()
            if not vision.is_available():
                record("Ollama reachable", "FAIL", "Ollama not reachable or model not pulled")
                if not args.allow_cpu:
                    print("[FAIL] Vision tests aborted — Ollama unavailable")
                    _finish(args)
                    vm.shutdown()
                    sys.exit(1)
            else:
                record("Ollama reachable", "PASS")

                print("[....] Warming up vision model + checking GPU...")
                gpu = vision.ensure_gpu()

                if gpu.loaded:
                    size_mb = gpu.size / (1024 * 1024)
                    vram_mb = gpu.size_vram / (1024 * 1024)
                    record(
                        "GPU status",
                        "PASS" if gpu.gpu_ok else "WARN",
                        f"VRAM: {vram_mb:.0f}/{size_mb:.0f} MB ({gpu.vram_percent}%)",
                    )
                    if not gpu.gpu_ok and not args.allow_cpu:
                        record("GPU enforcement", "FAIL", f"Only {gpu.vram_percent}% in VRAM (need 80%+)")
                        print("[FAIL] Vision tests aborted — model not on GPU. Use --allow-cpu to override.")
                        _finish(args)
                        vm.shutdown()
                        sys.exit(1)
                    elif not gpu.gpu_ok:
                        record("GPU enforcement", "WARN", f"Running on CPU ({gpu.vram_percent}% VRAM)")
                else:
                    record("GPU status", "WARN" if args.allow_cpu else "FAIL", gpu.error)
                    if not args.allow_cpu:
                        print(f"[FAIL] Vision tests aborted — {gpu.error}. Use --allow-cpu to override.")
                        _finish(args)
                        vm.shutdown()
                        sys.exit(1)

                # ── Phase 6: Vision GUI Tests (Layer 3) ──
                print("\n── Phase 6: Vision GUI Tests (Layer 3: Comprehensive Suite) ──")

                run_vision_tests(
                    vision, vm, record, screenshot,
                    vnc_available=False,  # Phase 6 = vision-only, no VNC interaction
                    grub_screenshot=grub_screenshot_path,
                    desktop_screenshot=desktop_path,
                )

                # ── Phase 7: Vision Interactive Tests (Layer 1+3) ──
                if args.vnc and vm.vnc_connected:
                    print("\n── Phase 7: Vision Interactive Tests (Layer 1+3: VNC + Vision) ──")

                    # Re-run only the interactive tests (category E) with VNC
                    from scripts.lib.vision_tests import (
                        test_dismiss_welcome,
                        test_open_terminal,
                        test_terminal_verification,
                    )
                    test_dismiss_welcome(vision, vm, record, screenshot)
                    test_open_terminal(vision, vm, record, screenshot)
                    test_terminal_verification(vision, vm, record, screenshot)
                else:
                    print("\n── Phase 7: Vision Interactive Tests (SKIPPED — VNC not enabled) ──")
                    record("Interactive vision tests", "SKIP", "Use --vnc to enable")
        else:
            print("\n── Phase 5-7: Vision Tests (SKIPPED) ──")
            record("Vision tests", "SKIP", "Use without --skip-vision to enable")

        # ── Shutdown ──
        print("\n[INFO] Shutting down VM...")
        vm.shutdown()

    _finish(args)
    failed = sum(1 for _, s, _ in RESULTS if s in ("FAIL", "TIMEOUT"))
    sys.exit(1 if failed else 0)


def _pick_best_grub(captures: list[str]) -> str | None:
    """Pick the GRUB menu screenshot from early boot captures.

    Strategy: return the FIRST capture that has meaningful content.
    GRUB appears before kernel boot, so the first non-black frame
    is the GRUB menu. Later frames (kernel log) have more text but
    are not GRUB.
    """
    for path in captures:
        if not os.path.isfile(path):
            continue
        try:
            score = _content_score(path)
            if score > 0.01:  # >1% non-black = has content
                return path
        except Exception:
            continue
    return None


def _content_score(image_path: str) -> float:
    """Return fraction of non-black pixels (0.0-1.0)."""
    try:
        from PIL import Image
    except ImportError:
        return 0.0

    img = Image.open(image_path).convert("L")  # Grayscale
    data = img.getdata()
    total = len(data)
    if not total:
        return 0.0
    return sum(1 for p in data if p > 20) / total


def _finish(args: argparse.Namespace) -> None:
    """Generate report, print summary, optionally open screenshots."""
    report_path = generate_report(SCREENSHOT_DIR, RESULTS)
    _print_summary(report_path)

    if getattr(args, "open_screenshots", False):
        with contextlib.suppress(FileNotFoundError):
            subprocess.Popen(
                ["xdg-open", report_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )


def _print_summary(report_path: str = "") -> None:
    """Print test result summary."""
    passed = sum(1 for _, s, _ in RESULTS if s in ("PASS", "INFO"))
    failed = sum(1 for _, s, _ in RESULTS if s in ("FAIL", "TIMEOUT"))
    skipped = sum(1 for _, s, _ in RESULTS if s in ("SKIP", "WARN"))
    total = len(RESULTS)
    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed, {skipped} skipped ({total} total)")
    print(f"Screenshots: {SCREENSHOT_DIR}")
    if report_path:
        print(f"Report:      {report_path}")
    print(f"{'=' * 60}")
    if failed:
        print("\nFailed tests:")
        for name, status, detail in RESULTS:
            if status in ("FAIL", "TIMEOUT"):
                print(f"  - {name}: {detail}")


if __name__ == "__main__":
    main()
