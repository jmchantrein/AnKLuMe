"""Common step definitions used across all anklume BDD scenarios.

Generic givens (tool checks, sandbox), when (run commands), and
then (exit codes, output assertions) that are domain-independent.
"""

import shutil

from behave import given, then, when


@given('"{tool}" is available')
def tool_is_available(context, tool):
    """Skip the scenario if an external tool is not installed."""
    if not shutil.which(tool):
        context.scenario.skip(f"'{tool}' not found in PATH")


@given("a clean sandbox environment")
def clean_sandbox(context):
    """Verify we're in a working anklume directory."""
    assert (context.sandbox.project_dir / "scripts" / "generate.py").exists(), (
        "Not in an anklume project directory"
    )


@given("Incus daemon is available")
def incus_available(context):
    """Skip if no Incus daemon is accessible."""
    if not context.sandbox.has_incus():
        context.scenario.skip("No Incus daemon available")


@when('I run "{command}"')
def run_command(context, command):
    """Execute a command in the project directory."""
    context.sandbox.run(command, timeout=600)


@when('I run "{command}" and it may fail')
def run_command_may_fail(context, command):
    """Execute a command that is expected to potentially fail."""
    context.sandbox.run(command, timeout=600)


@then("exit code is 0")
def check_exit_zero(context):
    assert context.sandbox.last_result.returncode == 0, (
        f"Expected exit 0, got {context.sandbox.last_result.returncode}\n"
        f"stdout: {context.sandbox.last_result.stdout[:500]}\n"
        f"stderr: {context.sandbox.last_result.stderr[:500]}"
    )


@then("exit code is non-zero")
def check_exit_nonzero(context):
    assert context.sandbox.last_result.returncode != 0, (
        f"Expected non-zero exit, got 0\n"
        f"stdout: {context.sandbox.last_result.stdout[:500]}"
    )


@then('output contains "{text}"')
def check_output_contains(context, text):
    combined = context.sandbox.last_result.stdout + context.sandbox.last_result.stderr
    assert text in combined, (
        f"Expected '{text}' in output, not found.\n"
        f"stdout: {context.sandbox.last_result.stdout[:500]}\n"
        f"stderr: {context.sandbox.last_result.stderr[:500]}"
    )


@then('stderr contains "{text}"')
def check_stderr_contains(context, text):
    assert text in context.sandbox.last_result.stderr, (
        f"Expected '{text}' in stderr, not found.\n"
        f"stderr: {context.sandbox.last_result.stderr[:500]}"
    )
