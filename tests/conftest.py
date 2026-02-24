"""Make scripts/ importable for tests. Shared fixtures and helpers."""

import os
import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


# ---------------------------------------------------------------------------
# Shared helpers (importable by test files)
# ---------------------------------------------------------------------------


def read_log(log_file):
    """Return list of commands from a log file.

    Used by shell script tests that create mock binaries which log their
    invocations to a file.  Shared here to avoid duplication across 10+
    test files (ADR-009).
    """
    if log_file.exists():
        return [line.strip() for line in log_file.read_text().splitlines() if line.strip()]
    return []


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_bin_env(tmp_path):
    """Create a mock bin directory and environment with PATH pointing to it.

    Returns (mock_bin, env) where mock_bin is a Path to the bin directory
    and env is a copy of os.environ with mock_bin prepended to PATH.
    Used as a base for per-file mock_env fixtures (ADR-009).
    """
    mock_bin = tmp_path / "bin"
    mock_bin.mkdir()
    env = os.environ.copy()
    env["PATH"] = f"{mock_bin}:{env['PATH']}"
    return mock_bin, env


def make_mock_script(path, content="#!/usr/bin/env bash\nexit 0\n"):
    """Write an executable shell script to path."""
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def pytest_configure(config):
    """Disable host subnet conflict detection in tests.

    The host subnet conflict detection is a runtime safety feature that
    depends on the specific host's network interfaces. Tests use synthetic
    infra data (typically base_subnet 10.100) which may conflict with the
    test host. Disabling this check ensures tests are portable across hosts.
    """
    import os

    import generate

    # Monkeypatch for in-process calls
    generate._detect_host_subnets_orig = generate._detect_host_subnets
    generate._detect_host_subnets = lambda: []

    # Environment variable for subprocess calls (test_generate_cli.py)
    os.environ["ANKLUME_SKIP_HOST_SUBNET_CHECK"] = "1"


def pytest_collection_modifyitems(items):
    """Allow classes with ``pytestmark = []`` to bypass the module-level skip.

    test_integration.py has a module-level pytestmark that skips all tests
    when Incus is unavailable.  New test classes that don't need Incus
    declare ``pytestmark = []`` to opt out.

    Strategy: move the Incus skipif from the Module node down to individual
    Class nodes (only for classes that did NOT opt out).  This way the
    Module-level marker no longer applies globally, and each class controls
    its own skip behavior.
    """
    processed_modules = set()

    for item in items:
        # Find the Module node
        module_node = item.parent
        while module_node is not None and type(module_node).__name__ != "Module":
            module_node = module_node.parent
        if module_node is None or id(module_node) in processed_modules:
            continue
        processed_modules.add(id(module_node))

        # Extract Incus-related skipif markers from the Module
        incus_markers = [
            m for m in module_node.own_markers
            if m.name == "skipif" and "Incus" in str(m.kwargs.get("reason", ""))
        ]
        if not incus_markers:
            continue

        # Remove them from the Module
        module_node.own_markers = [
            m for m in module_node.own_markers
            if not (m.name == "skipif" and "Incus" in str(m.kwargs.get("reason", "")))
        ]

        # Add them to Class/Function nodes that didn't opt out
        seen_parents = set()
        for child in items:
            # Only process items from this module
            child_module = child.parent
            while child_module is not None and type(child_module).__name__ != "Module":
                child_module = child_module.parent
            if child_module is not module_node:
                continue

            # Find the immediate Class parent (if any)
            cls = child.cls
            if cls is not None and cls.__dict__.get("pytestmark") == []:
                continue  # Class opted out of Incus skip

            # Add skips to the item's immediate parent (Class or directly)
            target = child.parent
            if id(target) not in seen_parents:
                seen_parents.add(id(target))
                target.own_markers.extend(incus_markers)
