"""Comprehensive vision GUI tests inspired by openQA/os-autoinst.

Each test is a scenario with assertion, screenshot capture, and clear
PASS/FAIL criteria. Tests are organized by category:

A. Boot verification (GRUB menu)
B. Desktop identification (DE type, layout, wallpaper)
C. Desktop components (tray, launcher, welcome)
D. Text readability (dialog text, clock)
E. Application interaction (VNC required — dismiss, open, verify)
F. Accessibility (font rendering, icon clarity)
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from scripts.lib.vision_agent import VisionAgent
    from scripts.lib.vm_controller import VMController

log = logging.getLogger(__name__)

RecordFn = Callable[[str, str, str], None]
ScreenshotFn = Callable[[Any, str], str]


def _assert_vision(
    vision: VisionAgent,
    image_path: str,
    prompt: str,
    keywords: list[str],
    record: RecordFn,
    test_name: str,
    *,
    case_sensitive: bool = False,
) -> bool:
    """Run a vision assertion: ask prompt, check keywords in response.

    Returns True if at least one keyword is found.
    """
    result = vision.ask(image_path, prompt)
    if not result.available:
        record(test_name, "FAIL", f"Vision unavailable: {result.error}")
        return False

    response = result.response if case_sensitive else result.response.lower()
    check = [k if case_sensitive else k.lower() for k in keywords]
    found = any(k in response for k in check)
    record(
        test_name,
        "PASS" if found else "FAIL",
        result.response[:120],
    )
    return found


# ── Category A: Boot Verification ──


def test_grub_menu_readable(
    vision: VisionAgent,
    grub_screenshot: str,
    record: RecordFn,
) -> bool:
    """Vision reads GRUB menu entries, finds 'anklume'."""
    return _assert_vision(
        vision, grub_screenshot,
        "Read the text on this boot menu screen. "
        "List all visible menu entries exactly as written.",
        ["anklume"],
        record, "A1: GRUB menu readable",
    )


def test_grub_distro_label(
    vision: VisionAgent,
    grub_screenshot: str,
    record: RecordFn,
) -> bool:
    """GRUB shows 'anklume', not just 'Debian' or 'Arch' alone."""
    result = vision.ask(
        grub_screenshot,
        "What is the name of the operating system shown in this boot menu? "
        "Reply with ONLY the OS name as it appears on screen.",
    )
    if not result.available:
        record("A2: GRUB distro label", "FAIL", f"Vision unavailable: {result.error}")
        return False

    resp_lower = result.response.lower()
    has_anklume = "anklume" in resp_lower
    only_debian = "debian" in resp_lower and not has_anklume
    only_arch = "arch" in resp_lower and not has_anklume

    if has_anklume:
        record("A2: GRUB distro label", "PASS", result.response[:80])
        return True
    if only_debian or only_arch:
        record("A2: GRUB distro label", "FAIL", f"Shows '{result.response[:60]}' without anklume branding")
        return False
    record("A2: GRUB distro label", "WARN", result.response[:80])
    return False


# ── Category B: Desktop Identification ──


def test_desktop_environment_type(
    vision: VisionAgent,
    desktop_screenshot: str,
    record: RecordFn,
) -> bool:
    """Vision identifies the desktop environment (KDE Plasma, Sway, etc.)."""
    return _assert_vision(
        vision, desktop_screenshot,
        "What desktop environment is shown in this screenshot? "
        "Name the specific desktop environment (e.g., KDE Plasma, GNOME, Sway, XFCE).",
        ["kde", "plasma", "sway", "gnome", "xfce", "labwc", "wlroots"],
        record, "B1: Desktop environment type",
    )


def test_desktop_layout(
    vision: VisionAgent,
    desktop_screenshot: str,
    record: RecordFn,
) -> bool:
    """Panel/taskbar detected at bottom or top."""
    return _assert_vision(
        vision, desktop_screenshot,
        "Describe the layout of this desktop. Is there a panel, taskbar, "
        "or dock? Where is it positioned (top, bottom, left, right)?",
        ["panel", "taskbar", "bar", "dock", "bottom", "top"],
        record, "B2: Desktop layout",
    )


def test_wallpaper_rendering(
    vision: VisionAgent,
    desktop_screenshot: str,
    record: RecordFn,
) -> bool:
    """Background is not black — has color, gradient, or image."""
    return _assert_vision(
        vision, desktop_screenshot,
        "Describe the desktop wallpaper or background. "
        "Is it a solid color, gradient, image, or is the screen black/empty?",
        ["color", "gradient", "image", "wallpaper", "blue", "green",
         "pattern", "photo", "background"],
        record, "B3: Wallpaper rendering",
    )


# ── Category C: Desktop Components ──


def test_system_tray(
    vision: VisionAgent,
    desktop_screenshot: str,
    record: RecordFn,
) -> bool:
    """System tray has clock, network, or volume icon."""
    return _assert_vision(
        vision, desktop_screenshot,
        "Look at the system tray area (usually bottom-right or top-right). "
        "What icons and indicators do you see? List them.",
        ["clock", "time", "network", "wifi", "volume", "sound",
         "battery", "tray", "notification"],
        record, "C1: System tray elements",
    )


def test_application_launcher(
    vision: VisionAgent,
    desktop_screenshot: str,
    record: RecordFn,
) -> bool:
    """Application launcher button/icon detected."""
    return _assert_vision(
        vision, desktop_screenshot,
        "Is there an application launcher, start menu button, or app menu "
        "visible on the screen? Describe its location and appearance.",
        ["launcher", "menu", "start", "application", "activities",
         "app", "kickoff", "button"],
        record, "C2: Application launcher",
    )


def test_welcome_center(
    vision: VisionAgent,
    desktop_screenshot: str,
    record: RecordFn,
) -> bool:
    """Welcome dialog/window with greeting text visible."""
    return _assert_vision(
        vision, desktop_screenshot,
        "Is there a welcome dialog, welcome center, or greeting window "
        "visible on screen? What does it say?",
        ["welcome", "bienvenue", "getting started", "guide",
         "anklume", "hello"],
        record, "C3: Welcome Center present",
    )


# ── Category D: Text Readability ──


def test_dialog_text_readable(
    vision: VisionAgent,
    desktop_screenshot: str,
    record: RecordFn,
) -> bool:
    """Vision can read specific text from a dialog or window."""
    result = vision.ask(
        desktop_screenshot,
        "Read ALL text visible on this screen. Include text from any "
        "dialogs, windows, panels, and menus. Be thorough.",
    )
    if not result.available:
        record("D1: Dialog text readable", "FAIL", f"Vision unavailable: {result.error}")
        return False

    # If vision can read any coherent text (>20 chars), it passes
    text = result.response.strip()
    readable = len(text) > 20
    record(
        "D1: Dialog text readable",
        "PASS" if readable else "FAIL",
        text[:120],
    )
    return readable


def test_panel_clock_readable(
    vision: VisionAgent,
    desktop_screenshot: str,
    record: RecordFn,
) -> bool:
    """Vision can read time/date from the system tray."""
    return _assert_vision(
        vision, desktop_screenshot,
        "What time is shown on the clock in the panel/taskbar? "
        "Read the exact time displayed.",
        [":", "am", "pm", "00", "01", "02", "03", "04", "05", "06",
         "07", "08", "09", "10", "11", "12", "13", "14", "15", "16",
         "17", "18", "19", "20", "21", "22", "23"],
        record, "D2: Panel clock readable",
    )


# ── Category E: Application Interaction (VNC required) ──


def test_dismiss_welcome(
    vision: VisionAgent,
    vm: VMController,
    record_fn: RecordFn,
    screenshot_fn: ScreenshotFn,
) -> bool:
    """Find close/skip button on welcome dialog, click it, verify gone."""
    pre = screenshot_fn(vm, "E1_pre_dismiss")
    element = vision.find_element(pre, "a close button, X button, or Skip button on a dialog window")
    if not element.available:
        record_fn("E1: Dismiss Welcome Center", "FAIL", f"Vision unavailable: {element.error}")
        return False

    import json as _json
    try:
        resp = element.response
        if "{" in resp:
            data = _json.loads(resp[resp.index("{"):resp.rindex("}") + 1])
        else:
            record_fn("E1: Dismiss Welcome Center", "SKIP", "No dialog found to dismiss")
            return False
    except (ValueError, _json.JSONDecodeError):
        record_fn("E1: Dismiss Welcome Center", "SKIP", "Could not parse element location")
        return False

    if not data.get("found", False):
        record_fn("E1: Dismiss Welcome Center", "SKIP", "No close button found")
        return False

    try:
        vm.mouse_click(int(data["x"]), int(data["y"]))
    except Exception as e:
        record_fn("E1: Dismiss Welcome Center", "FAIL", f"Click failed: {e}")
        return False

    time.sleep(2)
    post = screenshot_fn(vm, "E1_post_dismiss")
    verify = vision.ask(post, "Is there still a welcome dialog or popup window visible? Answer YES or NO.")
    if verify.available and "no" in verify.response.lower():
        record_fn("E1: Dismiss Welcome Center", "PASS", "Dialog dismissed successfully")
        return True
    record_fn("E1: Dismiss Welcome Center", "WARN", f"Dialog may still be present: {verify.response[:60]}")
    return False


def test_open_terminal(
    vision: VisionAgent,
    vm: VMController,
    record_fn: RecordFn,
    screenshot_fn: ScreenshotFn,
) -> bool:
    """Find terminal icon in taskbar, click to open."""
    pre = screenshot_fn(vm, "E2_pre_terminal")
    element = vision.find_element(
        pre,
        "a terminal emulator icon (like Konsole, xterm, or a command prompt icon) "
        "in the taskbar, panel, or desktop",
    )
    if not element.available:
        record_fn("E2: Open terminal", "FAIL", f"Vision unavailable: {element.error}")
        return False

    import json as _json
    try:
        resp = element.response
        if "{" in resp:
            data = _json.loads(resp[resp.index("{"):resp.rindex("}") + 1])
        else:
            record_fn("E2: Open terminal", "SKIP", "Terminal icon not found")
            return False
    except (ValueError, _json.JSONDecodeError):
        record_fn("E2: Open terminal", "SKIP", "Could not parse element location")
        return False

    if not data.get("found", False):
        record_fn("E2: Open terminal", "SKIP", data.get("description", "not found")[:60])
        return False

    try:
        vm.mouse_click(int(data["x"]), int(data["y"]))
    except Exception as e:
        record_fn("E2: Open terminal", "FAIL", f"Click failed: {e}")
        return False

    time.sleep(3)
    record_fn("E2: Open terminal", "PASS", "Clicked terminal icon")
    return True


def test_terminal_verification(
    vision: VisionAgent,
    vm: VMController,
    record_fn: RecordFn,
    screenshot_fn: ScreenshotFn,
) -> bool:
    """Verify terminal window appeared (dark background, prompt)."""
    img = screenshot_fn(vm, "E3_terminal_verify")
    return _assert_vision(
        vision, img,
        "Is there a terminal emulator window visible on screen? "
        "Look for a window with a dark background, command prompt, "
        "or text cursor. Describe what you see.",
        ["terminal", "console", "command", "prompt", "shell", "$", "#",
         "bash", "zsh", "konsole", "xterm"],
        record_fn, "E3: Terminal verification",
    )


# ── Category F: Accessibility Quick Check ──


def test_font_rendering(
    vision: VisionAgent,
    desktop_screenshot: str,
    record: RecordFn,
) -> bool:
    """Text is sharp and readable, no corruption."""
    return _assert_vision(
        vision, desktop_screenshot,
        "Evaluate the text rendering quality on this screen. "
        "Is the text sharp, clear, and readable? Are there any "
        "rendering artifacts, garbled characters, or blurry text?",
        ["sharp", "clear", "readable", "clean", "good", "fine",
         "legible", "crisp"],
        record, "F1: Font rendering quality",
    )


def test_icon_distinguishability(
    vision: VisionAgent,
    desktop_screenshot: str,
    record: RecordFn,
) -> bool:
    """UI icons are clear and recognizable."""
    return _assert_vision(
        vision, desktop_screenshot,
        "Look at the icons visible on screen (in taskbar, desktop, or windows). "
        "Are they clear, distinguishable, and properly rendered? "
        "Can you identify what each icon represents?",
        ["clear", "recognizable", "icon", "identif", "distinct",
         "visible", "proper"],
        record, "F2: Icon distinguishability",
    )


# ── Test Runner ──


def run_vision_tests(
    vision: VisionAgent,
    vm: VMController,
    record: RecordFn,
    screenshot_fn: ScreenshotFn,
    vnc_available: bool,
    *,
    grub_screenshot: str | None = None,
    desktop_screenshot: str | None = None,
) -> int:
    """Run all vision GUI tests. Returns count of failures.

    Args:
        vision: Initialized VisionAgent.
        vm: Running VMController.
        record: Function to record test results.
        screenshot_fn: Function to take screenshots.
        vnc_available: Whether VNC mouse interaction is available.
        grub_screenshot: Path to GRUB screenshot (skips A tests if None).
        desktop_screenshot: Path to desktop screenshot (taken if None).

    Returns:
        Number of failed tests.
    """
    failures = 0

    if desktop_screenshot is None:
        desktop_screenshot = screenshot_fn(vm, "vision_desktop")

    # Category A: Boot verification
    print("\n  ── A: Boot Verification ──")
    if grub_screenshot:
        if not test_grub_menu_readable(vision, grub_screenshot, record):
            failures += 1
        if not test_grub_distro_label(vision, grub_screenshot, record):
            failures += 1
    else:
        record("A1: GRUB menu readable", "SKIP", "No GRUB screenshot available")
        record("A2: GRUB distro label", "SKIP", "No GRUB screenshot available")

    # Category B: Desktop identification
    print("  ── B: Desktop Identification ──")
    if not test_desktop_environment_type(vision, desktop_screenshot, record):
        failures += 1
    if not test_desktop_layout(vision, desktop_screenshot, record):
        failures += 1
    if not test_wallpaper_rendering(vision, desktop_screenshot, record):
        failures += 1

    # Category C: Desktop components
    print("  ── C: Desktop Components ──")
    if not test_system_tray(vision, desktop_screenshot, record):
        failures += 1
    if not test_application_launcher(vision, desktop_screenshot, record):
        failures += 1
    if not test_welcome_center(vision, desktop_screenshot, record):
        failures += 1

    # Category D: Text readability
    print("  ── D: Text Readability ──")
    if not test_dialog_text_readable(vision, desktop_screenshot, record):
        failures += 1
    if not test_panel_clock_readable(vision, desktop_screenshot, record):
        failures += 1

    # Category E: Application interaction (VNC required)
    print("  ── E: Application Interaction ──")
    if vnc_available:
        if not test_dismiss_welcome(vision, vm, record, screenshot_fn):
            failures += 1
        if not test_open_terminal(vision, vm, record, screenshot_fn):
            failures += 1
        if not test_terminal_verification(vision, vm, record, screenshot_fn):
            failures += 1
    else:
        record("E1: Dismiss Welcome Center", "SKIP", "VNC required")
        record("E2: Open terminal", "SKIP", "VNC required")
        record("E3: Terminal verification", "SKIP", "VNC required")

    # Category F: Accessibility
    print("  ── F: Accessibility ──")
    if not test_font_rendering(vision, desktop_screenshot, record):
        failures += 1
    if not test_icon_distinguishability(vision, desktop_screenshot, record):
        failures += 1

    return failures
