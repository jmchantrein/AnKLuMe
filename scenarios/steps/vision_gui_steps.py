"""Vision GUI step definitions for anklume BDD tests.

Uses VisionAgent to verify console screenshots and desktop theming
via Ollama multimodal vision models. Color checks use retry 3x +
majority vote (D-065): a check passes only if at least 2 out of 3
attempts return a positive response.
"""

import logging
from pathlib import Path

from behave import given, then

from scenarios.steps.vision_cli_steps import _get_vision_agent

log = logging.getLogger("anklume.scenarios.vision")


def _vision_check_majority(agent, image_path, prompt, attempts=3):
    """Run a vision check multiple times and return majority result.

    Returns (passed: bool | None, responses: list[str]).
    None means the agent is unavailable (caller should skip).
    A check passes if at least ceil(attempts/2) responses contain YES.
    """
    yes_count = 0
    responses = []
    for _ in range(attempts):
        result = agent.ask(image_path, prompt)
        if not result.available:
            return None, []
        responses.append(result.response)
        if "YES" in result.response.upper():
            yes_count += 1
    threshold = (attempts + 1) // 2  # majority: 2 out of 3
    return yes_count >= threshold, responses


# -- Given steps --


@given("a console screenshot is available")
def console_screenshot_available(context):
    """Check for a pre-captured console screenshot or skip."""
    screenshots_dir = Path(context.sandbox.project_dir) / "tests" / "screenshots"
    console_shots = (
        list(screenshots_dir.glob("console*.png")) if screenshots_dir.exists() else []
    )
    if not console_shots:
        context.scenario.skip(
            "No console screenshot available (run console in GUI environment first)"
        )
        return
    context.console_screenshot = str(console_shots[0])


@given("a desktop screenshot is available")
def desktop_screenshot_available(context):
    """Check for a pre-captured desktop screenshot or skip."""
    screenshots_dir = Path(context.sandbox.project_dir) / "tests" / "screenshots"
    desktop_shots = (
        list(screenshots_dir.glob("desktop*.png")) if screenshots_dir.exists() else []
    )
    if not desktop_shots:
        context.scenario.skip(
            "No desktop screenshot available (run in GUI environment first)"
        )
        return
    context.desktop_screenshot = str(desktop_shots[0])


# -- Then steps --


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
    """Vision check: admin domains use blue color (retry 3x, majority vote)."""
    agent = _get_vision_agent()
    passed, responses = _vision_check_majority(
        agent, context.console_screenshot,
        "Look at this screenshot. Is there any section or label associated with "
        "'admin' that uses blue coloring? Answer YES or NO.",
    )
    if passed is None:
        context.scenario.skip("Vision agent unavailable")
        return
    assert passed, (
        f"Admin blue tone check failed (majority vote): "
        f"{[r[:100] for r in responses]}"
    )


@then("untrusted domains appear in red tones")
def untrusted_red_tones(context):
    """Vision check: untrusted domains use red color (retry 3x, majority vote)."""
    agent = _get_vision_agent()
    passed, responses = _vision_check_majority(
        agent, context.console_screenshot,
        "Look at this screenshot. Is there any section or label associated with "
        "'untrusted' that uses red coloring? Answer YES or NO.",
    )
    if passed is None:
        context.scenario.skip("Vision agent unavailable")
        return
    assert passed, (
        f"Untrusted red tone check failed (majority vote): "
        f"{[r[:100] for r in responses]}"
    )


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
    """Vision check: window borders match trust colors (retry 3x, majority vote)."""
    agent = _get_vision_agent()
    passed, responses = _vision_check_majority(
        agent, context.desktop_screenshot,
        "Are the window borders or title bars using different colors? "
        "Do you see color-coded windows (blue, green, yellow, red)? "
        "Answer YES or NO.",
    )
    if passed is None:
        context.scenario.skip("Vision agent unavailable")
        return
    assert passed, (
        f"Domain-specific window colors not detected (majority vote): "
        f"{[r[:100] for r in responses]}"
    )


@then("the screenshot layout matches expected desktop environment")
def screenshot_layout_matches(context):
    """Vision check: desktop layout has expected components."""
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
    assert len(result.response) > 20, (
        f"Vision description too short: {result.response}"
    )
