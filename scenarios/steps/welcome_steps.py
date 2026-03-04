"""Step definitions for welcome wizard UX BDD scenarios.

Covers AST-based checks on welcome.py structure (clear screens, Panel usage,
box-drawing detection) and welcome_strings key completeness.
"""

import ast
import re

from behave import given, then


def _find_func(tree: ast.AST, func_name: str) -> ast.FunctionDef:
    """Find a FunctionDef node by name in the AST."""
    for node in ast.walk(tree):
        if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == func_name):
            return node
    msg = f"Function '{func_name}' not found in AST"
    raise AssertionError(msg)


def _func_source(source: str, tree: ast.AST, func_name: str) -> str:
    """Extract the source code of a function from the full source."""
    func_node = _find_func(tree, func_name)
    lines = source.splitlines()
    start = func_node.lineno - 1
    end = len(lines)
    for node in ast.walk(tree):
        if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.lineno > func_node.lineno
                and node.col_offset <= func_node.col_offset):
            end = min(end, node.lineno - 1)
            break
    return "\n".join(lines[start:end])


@given("the welcome.py AST is loaded")
def load_welcome_ast(context):
    """Parse welcome.py into an AST and store it on context."""
    src = context.sandbox.project_dir / "scripts" / "welcome.py"
    assert src.exists(), f"welcome.py not found at {src}"
    context.welcome_source = src.read_text()
    context.welcome_ast = ast.parse(context.welcome_source)


@then('function "{func_name}" contains at least {count:d} calls to "{method}"')
def function_contains_calls(context, func_name, count, method):
    """Assert a function in welcome.py has >= N calls to a given method.

    Supports dotted methods like 'c.clear' (matches attr calls) and
    plain function names.
    """
    func_node = _find_func(context.welcome_ast, func_name)
    found = 0
    parts = method.split(".")
    for node in ast.walk(func_node):
        if not isinstance(node, ast.Call):
            continue
        if len(parts) == 2:
            if (isinstance(node.func, ast.Attribute)
                    and node.func.attr == parts[1]
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == parts[0]):
                found += 1
        elif (len(parts) == 1
              and isinstance(node.func, ast.Name)
              and node.func.id == parts[0]):
            found += 1
    assert found >= count, (
        f"Expected >= {count} calls to '{method}' in '{func_name}', found {found}"
    )


@then('function "{func_name}" contains at least {count:d} ANSI clear sequences')
def function_contains_ansi_clears(context, func_name, count):
    r"""Count occurrences of ANSI clear (\033[2J) in a function's source."""
    func_source = _func_source(
        context.welcome_source, context.welcome_ast, func_name,
    )
    found = func_source.count("\\033[2J")
    assert found >= count, (
        f"Expected >= {count} ANSI clear sequences in '{func_name}', found {found}"
    )


@then('function "{func_name}" uses Panel from rich')
def function_uses_panel(context, func_name):
    """Check that a function uses rich Panel for action prompts."""
    func_node = _find_func(context.welcome_ast, func_name)
    found = False
    for node in ast.walk(func_node):
        if not isinstance(node, ast.Call):
            continue
        # Check for Panel(...) call
        if isinstance(node.func, ast.Name) and node.func.id == "Panel":
            found = True
            break
        # Check for c.print(Panel(...)) pattern
        if isinstance(node.func, ast.Attribute) and node.func.attr == "print":
            for arg in node.args:
                if (isinstance(arg, ast.Call)
                        and isinstance(arg.func, ast.Name)
                        and arg.func.id == "Panel"):
                    found = True
                    break
    assert found, f"Function '{func_name}' does not use Panel from rich"


@then('function "{func_name}" uses box-drawing characters')
def function_uses_box_drawing(context, func_name):
    """Check that a function uses Unicode box-drawing chars for prompts."""
    func_source = _func_source(
        context.welcome_source, context.welcome_ast, func_name,
    )
    box_chars = re.findall(r"[┌┐└┘│─]", func_source)
    assert len(box_chars) >= 4, (
        f"Expected box-drawing characters in '{func_name}', found {len(box_chars)}"
    )


@then('welcome_strings contains key "{key}" in both languages')
def strings_contain_key(context, key):
    """Assert that a key exists in both FR and EN welcome_strings."""
    combined = context.sandbox.last_result.stdout + context.sandbox.last_result.stderr
    assert "True" in combined or "ok" in combined.lower(), (
        f"Key '{key}' check failed: {combined[:300]}"
    )
