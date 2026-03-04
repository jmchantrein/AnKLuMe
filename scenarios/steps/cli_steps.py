"""Step definitions for CLI and live/welcome BDD scenarios.

Covers timeout assertions, non-interactive execution checks,
summary parsing, mode-aware runs, and output negation.
"""

import re

from behave import given, then, when


@then("the command completed within {seconds:d} seconds")
def command_completed_within(context, seconds):
    """Assert the last command finished (did not get killed by timeout).

    The scenario runs the command wrapped in `timeout N`. If the process
    was killed by timeout, its exit code is 124 (GNU coreutils) or 137
    (SIGKILL). We check that the command ran to completion regardless of
    its actual exit code — the point is that it did not hang.
    """
    rc = context.sandbox.last_result.returncode
    duration = context.sandbox.last_result.duration
    # timeout returns 124 on SIGTERM, 137 on SIGKILL
    assert rc not in (124, 137), (
        f"Command was killed by timeout after {duration:.1f}s "
        f"(exit code {rc}). It likely hung waiting for input."
    )


@then("summary shows {count:d} errors")
def summary_shows_errors(context, count):
    """Assert the doctor summary line shows exactly N errors."""
    combined = context.sandbox.last_result.stdout + context.sandbox.last_result.stderr
    match = re.search(r"(\d+)\s+error", combined)
    assert match, f"No error count found in output:\n{combined[:500]}"
    actual = int(match.group(1))
    assert actual == count, (
        f"Expected {count} errors, found {actual}\nOutput: {combined[:500]}"
    )


@then("summary shows {count:d} warnings")
def summary_shows_warnings(context, count):
    """Assert the doctor summary line shows exactly N warnings."""
    combined = context.sandbox.last_result.stdout + context.sandbox.last_result.stderr
    match = re.search(r"(\d+)\s+warning", combined)
    assert match, f"No warning count found in output:\n{combined[:500]}"
    actual = int(match.group(1))
    assert actual == count, (
        f"Expected {count} warnings, found {actual}\nOutput: {combined[:500]}"
    )


@then('output does not contain "{text}"')
def check_output_does_not_contain(context, text):
    """Assert the combined output does NOT contain a string."""
    combined = context.sandbox.last_result.stdout + context.sandbox.last_result.stderr
    assert text not in combined, (
        f"Did not expect '{text}' in output, but found it.\n"
        f"Output: {combined[:500]}"
    )


@then("exit code is exactly {code:d}")
def check_exit_code_numeric(context, code):
    """Assert a specific numeric exit code (for codes other than 0)."""
    actual = context.sandbox.last_result.returncode
    assert actual == code, (
        f"Expected exit code {code}, got {actual}\n"
        f"stdout: {context.sandbox.last_result.stdout[:500]}\n"
        f"stderr: {context.sandbox.last_result.stderr[:500]}"
    )


@given('ANKLUME_MODE is set to "{mode}"')
def set_anklume_mode(context, mode):
    """Store ANKLUME_MODE for use in subsequent when steps."""
    context.anklume_mode = mode


@when('I run "{command}" with ANKLUME_MODE="{mode}"')
def run_with_mode(context, command, mode):
    """Execute a command with ANKLUME_MODE env var prepended."""
    context.sandbox.run(f"ANKLUME_MODE={mode} {command}", timeout=600)


@then('output line matching "{pattern}" exists')
def output_line_matching(context, pattern):
    """Assert at least one output line matches a regex pattern."""
    combined = context.sandbox.last_result.stdout + context.sandbox.last_result.stderr
    for line in combined.splitlines():
        if re.search(pattern, line):
            return
    msg = (
        f"No output line matches pattern '{pattern}'\n"
        f"Output: {combined[:500]}"
    )
    raise AssertionError(msg)
