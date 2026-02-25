"""Nesting and security context readers for the PSOT generator."""

import sys
from pathlib import Path


def _resolve(name):
    """Look up a patchable function on the ``generate`` module.

    See psot.validation._resolve for rationale.
    """
    gen = sys.modules.get("generate")
    if gen and hasattr(gen, name):
        return getattr(gen, name)
    # Fallback: return from this module itself
    return globals()[name]


def _read_absolute_level():
    """Read /etc/anklume/absolute_level context file. Returns int or None."""
    try:
        return int(Path("/etc/anklume/absolute_level").read_text().strip())
    except (FileNotFoundError, ValueError):
        return None


def _get_nesting_prefix(infra):
    """Compute nesting prefix string from infra config.

    Returns a prefix like "001-" if nesting_prefix is enabled (default),
    or "" if explicitly disabled.
    """
    g = infra.get("global", {})
    if not g.get("nesting_prefix", True):
        return ""
    level = _resolve("_read_absolute_level")()
    if level is None:
        return ""  # No context file = physical host, no prefix
    return f"{level:03d}-"


def _read_vm_nested():
    """Read /etc/anklume/vm_nested context file. Returns True/False/None."""
    try:
        return (
            Path("/etc/anklume/vm_nested").read_text().strip().lower()
            == "true"
        )
    except FileNotFoundError:
        return None


def _read_yolo():
    """Read /etc/anklume/yolo context file. Returns True if YOLO mode active."""
    try:
        return (
            Path("/etc/anklume/yolo").read_text().strip().lower() == "true"
        )
    except FileNotFoundError:
        return False
