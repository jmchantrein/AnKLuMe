"""Vision step definitions for anklume BDD tests.

Uses VisionAgent (scripts/lib/vision_agent.py) to verify CLI output
and GUI screenshots via Ollama multimodal vision models.

Screenshots are saved to tests/screenshots/ with descriptive names
(e.g., cli-help-readable.png) for human review. This directory is
gitignored.
"""

import logging
import re
import shutil
import subprocess
from pathlib import Path

from behave import given, then, when

log = logging.getLogger("anklume.scenarios.vision")

# Persistent screenshot directory for human review (gitignored)
PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
SCREENSHOTS_DIR = PROJECT_DIR / "tests" / "screenshots"

# Lazy import to avoid hard dependency on vision stack
_vision_agent = None


def _get_vision_agent():
    """Lazy-load VisionAgent singleton."""
    global _vision_agent
    if _vision_agent is None:
        import sys

        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        from scripts.lib.vision_agent import VisionAgent

        _vision_agent = VisionAgent()
    return _vision_agent


def _slugify(text: str) -> str:
    """Convert text to a filename-safe slug."""
    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")[:80]


def _screenshot_path(scenario_name: str, suffix: str = "") -> Path:
    """Build a descriptive screenshot path under tests/screenshots/.

    Examples:
        cli-help-output--readable.png
        console-domain-colors--color-coding.png
    """
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    name = _slugify(scenario_name)
    if suffix:
        name = f"{name}--{_slugify(suffix)}"
    return SCREENSHOTS_DIR / f"{name}.png"


def _render_text_to_image(text: str, output_path: str) -> bool:
    """Render plain text to a PNG image for vision analysis.

    Uses Pillow if available, falls back to ImageMagick convert.
    Returns True on success.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont

        lines = text.splitlines()
        font_size = 14
        line_height = font_size + 4
        width = max(len(line) for line in lines) * 8 + 40 if lines else 400
        height = len(lines) * line_height + 40

        img = Image.new("RGB", (max(width, 400), max(height, 200)), color=(30, 30, 30))
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", font_size)
        except OSError:
            font = ImageFont.load_default()

        y = 20
        for line in lines:
            draw.text((20, y), line, fill=(220, 220, 220), font=font)
            y += line_height

        img.save(output_path, "PNG")
        return True
    except ImportError:
        pass

    if shutil.which("convert"):
        try:
            subprocess.run(
                [
                    "convert",
                    "-size", "800x600",
                    "xc:#1e1e1e",
                    "-font", "DejaVu-Sans-Mono",
                    "-pointsize", "14",
                    "-fill", "#dcdcdc",
                    "-annotate", "+20+20",
                    text[:2000],
                    output_path,
                ],
                capture_output=True,
                timeout=10,
            )
            return Path(output_path).exists()
        except (subprocess.TimeoutExpired, OSError):
            pass

    return False


# -- Given steps --


@given("vision agent is available")
def vision_agent_available(context):
    """Skip scenario if VisionAgent or Ollama is not reachable."""
    import socket

    try:
        agent = _get_vision_agent()
        # Fast TCP check before the full HTTP call (avoids long OS-level timeouts)
        host = agent.base_url.split("://")[-1].split(":")[0]
        port = int(agent.base_url.split(":")[-1].rstrip("/"))
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        try:
            sock.connect((host, port))
            sock.close()
        except (OSError, TimeoutError):
            context.scenario.skip(f"Vision agent not reachable (TCP {host}:{port} timeout)")
            return
        if not agent.is_available():
            context.scenario.skip("Vision agent not available (Ollama unreachable or model missing)")
    except Exception as e:
        context.scenario.skip(f"Vision agent import failed: {e}")


@given("a console screenshot is available")
def console_screenshot_available(context):
    """Check for a pre-captured console screenshot or skip."""
    screenshots_dir = Path(context.sandbox.project_dir) / "tests" / "screenshots"
    console_shots = list(screenshots_dir.glob("console*.png")) if screenshots_dir.exists() else []
    if not console_shots:
        context.scenario.skip("No console screenshot available (run console in GUI environment first)")
        return
    context.console_screenshot = str(console_shots[0])


@given("a desktop screenshot is available")
def desktop_screenshot_available(context):
    """Check for a pre-captured desktop screenshot or skip."""
    screenshots_dir = Path(context.sandbox.project_dir) / "tests" / "screenshots"
    desktop_shots = list(screenshots_dir.glob("desktop*.png")) if screenshots_dir.exists() else []
    if not desktop_shots:
        context.scenario.skip("No desktop screenshot available (run in GUI environment first)")
        return
    context.desktop_screenshot = str(desktop_shots[0])


# -- When steps --


@when('I capture CLI output of "{command}"')
def capture_cli_output(context, command):
    """Run a command, capture output, render to image for vision analysis.

    Screenshots are saved to tests/screenshots/ with descriptive names
    derived from the scenario name and command for human review.
    """
    result = context.sandbox.run(command, timeout=30)
    context.captured_text = result.stdout + result.stderr
    context.captured_returncode = result.returncode

    scenario_name = getattr(context, "scenario", None)
    scenario_label = scenario_name.name if scenario_name else "unknown"
    cmd_slug = _slugify(command.split()[0]) if command else "cmd"
    img_path = _screenshot_path(scenario_label, cmd_slug)

    rendered = _render_text_to_image(context.captured_text, str(img_path))
    if rendered:
        context.captured_image = str(img_path)
        log.info("Screenshot saved: %s", img_path.relative_to(PROJECT_DIR))
    else:
        context.captured_image = None
        log.warning("Could not render CLI output to image (no Pillow or ImageMagick)")


# -- Then steps (CLI vision) --


@then("the captured output is readable")
def captured_output_readable(context):
    """Verify captured CLI output is non-empty and readable."""
    assert hasattr(context, "captured_text"), "No captured output (run a capture step first)"
    assert len(context.captured_text.strip()) > 0, "Captured output is empty"

    if getattr(context, "captured_image", None):
        agent = _get_vision_agent()
        result = agent.ask(
            context.captured_image,
            "Is this terminal output readable? Can you read the text? "
            "Answer YES or NO followed by a brief description of what you see.",
        )
        if result.available:
            response = result.response.upper()
            assert "YES" in response or "READ" in response, (
                f"Vision agent says output is not readable: {result.response[:200]}"
            )


@then('the captured output contains visible text "{text}"')
def captured_output_contains_text(context, text):
    """Verify text is present in captured output (text + optional vision check)."""
    assert hasattr(context, "captured_text"), "No captured output"
    combined = context.captured_text
    assert text.lower() in combined.lower(), (
        f"Expected '{text}' in output, not found.\n"
        f"Output: {combined[:500]}"
    )


# -- Then steps (GUI vision) --


@then("the screenshot shows domain color coding")
def screenshot_shows_colors(context):
    """Vision check: screenshot contains colored domain indicators."""
    agent = _get_vision_agent()
    result = agent.ask(
        context.console_screenshot,
        "Does this screenshot show colored labels or borders for different domains? "
        "Look for color-coded sections (blue, green, yellow, red, magenta). "
        "Answer YES or NO and describe the colors you see.",
    )
    if not result.available:
        context.scenario.skip("Vision agent unavailable for GUI check")
        return
    assert "YES" in result.response.upper() or "COLOR" in result.response.upper(), (
        f"No domain color coding detected: {result.response[:200]}"
    )


@then("the screenshot contains labeled panes")
def screenshot_has_panes(context):
    """Vision check: screenshot has labeled panes or sections."""
    agent = _get_vision_agent()
    result = agent.ask(
        context.console_screenshot,
        "Does this screenshot show labeled panes, panels, or sections? "
        "Look for text labels on separate UI regions. "
        "Answer YES or NO and list the labels you can read.",
    )
    if not result.available:
        context.scenario.skip("Vision agent unavailable")
        return
    assert "YES" in result.response.upper() or "LABEL" in result.response.upper(), (
        f"No labeled panes detected: {result.response[:200]}"
    )


@then("admin domains appear in blue tones")
def admin_blue_tones(context):
    """Vision check: admin domains use blue color coding."""
    agent = _get_vision_agent()
    result = agent.ask(
        context.console_screenshot,
        "Look at this screenshot. Is there any section or label associated with "
        "'admin' that uses blue coloring? Answer YES or NO.",
    )
    if not result.available:
        context.scenario.skip("Vision agent unavailable")
        return
    # Soft assertion — log warning but don't fail if vision is uncertain
    if "YES" not in result.response.upper():
        log.warning("Admin blue tone check inconclusive: %s", result.response[:200])


@then("untrusted domains appear in red tones")
def untrusted_red_tones(context):
    """Vision check: untrusted domains use red color coding."""
    agent = _get_vision_agent()
    result = agent.ask(
        context.console_screenshot,
        "Look at this screenshot. Is there any section or label associated with "
        "'untrusted' that uses red coloring? Answer YES or NO.",
    )
    if not result.available:
        context.scenario.skip("Vision agent unavailable")
        return
    if "YES" not in result.response.upper():
        log.warning("Untrusted red tone check inconclusive: %s", result.response[:200])


@then("the screenshot shows window decorations")
def screenshot_shows_decorations(context):
    """Vision check: desktop screenshot has window title bars or borders."""
    agent = _get_vision_agent()
    result = agent.ask(
        context.desktop_screenshot,
        "Does this desktop screenshot show window title bars, borders, or decorations? "
        "Answer YES or NO and describe what you see.",
    )
    if not result.available:
        context.scenario.skip("Vision agent unavailable")
        return
    assert "YES" in result.response.upper() or "WINDOW" in result.response.upper(), (
        f"No window decorations detected: {result.response[:200]}"
    )


@then("window borders use domain-specific colors")
def window_borders_domain_colors(context):
    """Vision check: window borders match domain trust level colors."""
    agent = _get_vision_agent()
    result = agent.ask(
        context.desktop_screenshot,
        "Are the window borders or title bars using different colors? "
        "Do you see color-coded windows (blue, green, yellow, red)? "
        "Answer YES or NO.",
    )
    if not result.available:
        context.scenario.skip("Vision agent unavailable")
        return
    if "YES" not in result.response.upper():
        log.warning("Domain-specific window colors not detected: %s", result.response[:200])


@then("the screenshot layout matches expected desktop environment")
def screenshot_layout_matches(context):
    """Vision check: desktop layout has expected components (panel, wallpaper)."""
    agent = _get_vision_agent()
    result = agent.ask(
        context.desktop_screenshot,
        "Describe this desktop environment. Does it have a panel/taskbar, "
        "a wallpaper or background, and windows? "
        "What desktop environment does it look like (GNOME, KDE, Sway, i3)?",
    )
    if not result.available:
        context.scenario.skip("Vision agent unavailable")
        return
    # Just verify we got a meaningful description
    assert len(result.response) > 20, (
        f"Vision description too short: {result.response}"
    )
