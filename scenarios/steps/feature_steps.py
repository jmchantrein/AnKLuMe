"""Step definitions for the 4 new features (Phase 48).

Covers: git push protection, sanitizer dry-run, STT diagnostics,
host resource monitoring. Uses only existing common steps where
possible; adds specific steps for file attribute checks.
"""

from behave import given, then


@given('the file "{path}" exists')
def file_exists_given(context, path):
    """Assert that a file exists relative to project root."""
    full = context.sandbox.project_dir / path
    assert full.is_file(), f"File not found: {full}"
    context.current_file = full


@then("it is executable")
def file_is_executable(context):
    """Assert that the current file is executable."""
    assert hasattr(context, "current_file"), "No file set in context"
    assert context.current_file.stat().st_mode & 0o111, (
        f"File is not executable: {context.current_file}"
    )


@then('the file starts with "{line}"')
def file_starts_with(context, line):
    """Assert the first line of the current file matches."""
    assert hasattr(context, "current_file"), "No file set in context"
    first_line = context.current_file.read_text().splitlines()[0]
    assert first_line == line, (
        f"Expected first line '{line}', got '{first_line}'"
    )
