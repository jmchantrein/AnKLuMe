"""Step definitions for static analysis of bash scripts.

Provides reusable steps that inspect bash script source code via grep/regex
without executing the scripts. Used by live_persistence.feature and similar
features that verify script structure and logic.
"""

import re

from behave import given, then

# Cache of loaded script sources keyed by path.
_script_cache: dict[str, str] = {}


def _load_script(context, path: str) -> str:
    """Load and cache a script's source code."""
    if path not in _script_cache:
        full = context.sandbox.project_dir / path
        _script_cache[path] = full.read_text()
    return _script_cache[path]


def _extract_function(source: str, func_name: str) -> str | None:
    """Extract the body of a bash function from source.

    Uses a line-based approach: finds the function definition line,
    then scans forward to find the closing `}` at the same indentation
    level (column 0 for top-level functions). This avoids the
    complexity of brace-counting through ${var}, heredocs, etc.
    """
    lines = source.split("\n")
    # Find the function definition line
    func_pattern = re.compile(
        rf'^\s*(?:function\s+)?{re.escape(func_name)}\s*\(\)'
    )
    start_idx = None
    for i, line in enumerate(lines):
        if func_pattern.match(line):
            start_idx = i
            break
    if start_idx is None:
        return None

    # Determine indentation of the function definition
    func_indent = len(lines[start_idx]) - len(lines[start_idx].lstrip())

    # Find the opening brace (may be on same line or next)
    found_open = False
    for i in range(start_idx, min(start_idx + 3, len(lines))):
        if "{" in lines[i]:
            found_open = True
            break
    if not found_open:
        return None

    # Find the closing brace at the same indentation level
    for i in range(start_idx + 1, len(lines)):
        stripped = lines[i].strip()
        if stripped == "}":
            line_indent = len(lines[i]) - len(lines[i].lstrip())
            if line_indent <= func_indent:
                return "\n".join(lines[start_idx : i + 1])

    # Fallback: return from start to end of file
    return "\n".join(lines[start_idx:])


@given('the script "{path}" source is loaded')
def load_script_source(context, path):
    """Load a script's source code into context for subsequent assertions."""
    context.script_path = path
    context.script_source = _load_script(context, path)


@then('function "{func}" is defined in the script')
def function_is_defined(context, func):
    """Assert a function is defined in the loaded script."""
    source = context.script_source
    # Match both `funcname() {` and `function funcname() {`
    pattern = rf'(?:^|\n)\s*(?:function\s+)?{re.escape(func)}\s*\(\)'
    assert re.search(pattern, source), (
        f"Function '{func}' not found in {context.script_path}"
    )


@then('function "{func}" contains pattern "{pattern}"')
def function_contains_pattern(context, func, pattern):
    """Assert a function body contains a regex/literal pattern.

    Uses re.DOTALL so .* matches across newlines within the function.
    """
    source = context.script_source
    body = _extract_function(source, func)
    assert body is not None, (
        f"Function '{func}' not found in {context.script_path}"
    )
    assert re.search(pattern, body, re.DOTALL), (
        f"Pattern '{pattern}' not found in function '{func}'\n"
        f"Function body (first 500 chars): {body[:500]}"
    )


@then('function "{func}" does not contain pattern "{pattern}"')
def function_does_not_contain_pattern(context, func, pattern):
    """Assert a function body does NOT contain a pattern."""
    source = context.script_source
    body = _extract_function(source, func)
    assert body is not None, (
        f"Function '{func}' not found in {context.script_path}"
    )
    assert not re.search(pattern, body, re.DOTALL), (
        f"Pattern '{pattern}' unexpectedly found in function '{func}'"
    )


@then('the script contains pattern "{pattern}"')
def script_contains_pattern(context, pattern):
    """Assert the loaded script source contains a regex pattern."""
    assert re.search(pattern, context.script_source, re.DOTALL), (
        f"Pattern '{pattern}' not found in {context.script_path}"
    )


@then('the script does not contain pattern "{pattern}"')
def script_does_not_contain_pattern(context, pattern):
    """Assert the loaded script source does NOT contain a pattern."""
    assert not re.search(pattern, context.script_source, re.DOTALL), (
        f"Pattern '{pattern}' unexpectedly found in {context.script_path}"
    )


@then('the script defines variable "{varname}"')
def script_defines_variable(context, varname):
    """Assert a variable is defined (assigned) in the script."""
    pattern = rf'(?:^|\n)\s*(?:declare\s+[^ ]+\s+)?{re.escape(varname)}='
    assert re.search(pattern, context.script_source), (
        f"Variable '{varname}' not defined in {context.script_path}"
    )


@then('the script sets "{varname}" to "{value}"')
def script_defines_variable_with_value(context, varname, value):
    """Assert a variable is defined with a specific literal value."""
    # Handles both quoted and unquoted values
    patterns = [
        rf'{re.escape(varname)}="{re.escape(value)}"',
        rf"{re.escape(varname)}='{re.escape(value)}'",
        rf'{re.escape(varname)}={re.escape(value)}(?:\s|$)',
    ]
    source = context.script_source
    found = any(re.search(p, source) for p in patterns)
    assert found, (
        f"Variable '{varname}' not set to '{value}' in {context.script_path}"
    )
