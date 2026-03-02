"""Monkeypatch-compatible function resolution for the PSOT generator.

When tests monkeypatch ``generate.py`` functions, the PSOT sub-modules
need to resolve those patched versions at call time (not import time).
This module provides a single ``resolve()`` helper used across all PSOT
sub-modules that need late-binding.
"""

import sys


def resolve(name, *, fallback_globals=None):
    """Late-bind a function via the ``generate`` module for monkeypatch compat.

    Lookup order:
    1. ``sys.modules["generate"].<name>`` (monkeypatched version)
    2. ``fallback_globals[name]`` if provided (for context.py's local functions)
    3. ``psot.<name>`` via the psot package's re-exports
    """
    gen = sys.modules.get("generate")
    if gen and hasattr(gen, name):
        return getattr(gen, name)
    if fallback_globals is not None and name in fallback_globals:
        return fallback_globals[name]
    import psot  # noqa: PLC0415

    return getattr(psot, name)
