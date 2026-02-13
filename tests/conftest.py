"""Make scripts/ importable for tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


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
