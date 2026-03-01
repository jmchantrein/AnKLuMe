"""Vision CLI step definitions for anklume BDD tests.

Captures CLI output, renders to images, and verifies readability
via Ollama multimodal vision models. Screenshots are saved to
tests/screenshots/ for human review (gitignored).
"""

import logging
import re
import shutil
import subprocess
from pathlib import Path

from behave import given, then, when

log = logging.getLogger("anklume.scenarios.vision")

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
SCREENSHOTS_DIR = PROJECT_DIR / "tests" / "screenshots"

_vision_agent = None


def _get_vision_agent():
    """Lazy-load VisionAgent singleton."""
    global _vision_agent  # noqa: PLW0603
    if _vision_agent is None:
        import sys

        sys.path.insert(0, str(PROJECT_DIR))
        from scripts.lib.vision_agent import VisionAgent

        _vision_agent = VisionAgent()
    return _vision_agent


def _slugify(text: str) -> str:
    """Convert text to a filename-safe slug."""
    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")[:80]


def _screenshot_path(scenario_name: str, suffix: str = "") -> Path:
    """Build a descriptive screenshot path under tests/screenshots/."""
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    name = _slugify(scenario_name)
    if suffix:
        name = f"{name}--{_slugify(suffix)}"
    return SCREENSHOTS_DIR / f"{name}.png"


def _render_text_to_image(text: str, output_path: str) -> bool:
    """Render plain text to a PNG image for vision analysis.

    Uses Pillow if available, falls back to ImageMagick convert.
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
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", font_size
            )
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
                    "convert", "-size", "800x600", "xc:#1e1e1e",
                    "-font", "DejaVu-Sans-Mono", "-pointsize", "14",
                    "-fill", "#dcdcdc", "-annotate", "+20+20",
                    text[:2000], output_path,
                ],
                capture_output=True, timeout=10,
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
        host = agent.base_url.split("://")[-1].split(":")[0]
        port = int(agent.base_url.split(":")[-1].rstrip("/"))
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        try:
            sock.connect((host, port))
            sock.close()
        except (OSError, TimeoutError):
            context.scenario.skip(
                f"Vision agent not reachable (TCP {host}:{port} timeout)"
            )
            return
        if not agent.is_available():
            context.scenario.skip(
                "Vision agent not available (Ollama unreachable or model missing)"
            )
    except Exception as e:
        context.scenario.skip(f"Vision agent import failed: {e}")


# -- When steps --


@when('I capture CLI output of "{command}"')
def capture_cli_output(context, command):
    """Run a command, capture output, render to image for vision analysis."""
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
        log.warning("Could not render CLI output to image")


# -- Then steps --


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
    """Verify text is present in captured output."""
    assert hasattr(context, "captured_text"), "No captured output"
    combined = context.captured_text
    assert text.lower() in combined.lower(), (
        f"Expected '{text}' in output, not found.\nOutput: {combined[:500]}"
    )
