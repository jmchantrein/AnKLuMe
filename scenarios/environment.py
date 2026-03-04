"""Behave environment hooks for anklume E2E scenario tests.

Replaces the pytest fixtures from the former conftest.py with behave
lifecycle hooks. Manages session-level backup/restore and per-scenario
sandbox creation.

Gate/blocking mechanism:
    Tag a critical scenario with @gate.NAME to register it as a gate.
    Tag dependent scenarios with @requires.NAME to skip them if the
    gate failed or was never reached. Multiple @requires tags are ANDed.
    Example:
        @gate.web_imports
        Scenario: Web module imports successfully
            ...

        @requires.web_imports
        Scenario: Platform server landing page returns 200
            ...

Usage:
    python3 -m behave scenarios/ --no-capture -v
    python3 -m behave scenarios/best_practices/ --no-capture -v
    python3 -m behave scenarios/bad_practices/ --no-capture -v
"""

import logging
import os
import pty as pty_module
import shutil

from scenarios.support import (
    PROJECT_DIR,
    SESSION_BACKUP_DIR,
    Sandbox,
    _backup_state,
    _restore_state,
)

logger = logging.getLogger("anklume.scenarios")

# -- Gate tracking ---------------------------------------------------------
# Stores gate pass/fail results across the session.  Key = gate name,
# value = True (passed) or False (failed/errored).
_gate_results: dict[str, bool] = {}

_GATE_PREFIX = "gate."
_REQUIRES_PREFIX = "requires."


def _extract_gate_names(tags: list[str], prefix: str) -> list[str]:
    """Return the gate names from tags matching the given prefix."""
    return [t[len(prefix):] for t in tags if t.startswith(prefix)]


def before_all(context):
    """Session-level setup: environment variables and crash-safe backup.

    Sets environment variables to skip host subnet conflict detection
    and network safety checks (scenario tests may run in sandboxes
    without internet connectivity). Restores from a previous crash
    backup if one exists, then creates a fresh session backup.
    Clears gate results for a fresh session.
    """
    _gate_results.clear()

    # Skip host subnet conflict detection — examples use 10.100 which
    # may conflict with host interfaces.
    os.environ["ANKLUME_SKIP_HOST_SUBNET_CHECK"] = "1"

    # Skip network safety checks — scenario tests may run in sandboxes
    # without internet connectivity.
    os.environ["ANKLUME_SKIP_NETWORK_CHECK"] = "1"

    # Restore from a previous crash if a stale backup exists.
    if SESSION_BACKUP_DIR.exists():
        logger.warning("Restoring from previous scenario session crash backup")
        _restore_state(SESSION_BACKUP_DIR, PROJECT_DIR)
        shutil.rmtree(SESSION_BACKUP_DIR)

    # Create a fresh session backup.
    _backup_state(PROJECT_DIR, SESSION_BACKUP_DIR)


def after_all(context):
    """Session-level teardown: restore project state from session backup."""
    if SESSION_BACKUP_DIR.exists():
        _restore_state(SESSION_BACKUP_DIR, PROJECT_DIR)
        shutil.rmtree(SESSION_BACKUP_DIR)


def _pty_available():
    """Check if PTY devices are available."""
    try:
        m, s = pty_module.openpty()
        os.close(m)
        os.close(s)
        return True
    except OSError:
        return False


def before_feature(context, feature):
    """Skip features tagged @pty_required when PTY devices are unavailable."""
    if "pty_required" in feature.tags and not _pty_available():
        feature.skip("PTY devices not available")


def before_scenario(context, scenario):
    """Per-scenario setup: create Sandbox and check gate dependencies.

    If the scenario has @requires.NAME tags, each named gate must have
    passed.  If any required gate failed or was never reached, the
    scenario is skipped automatically.

    A scenario that defines @gate.NAME is exempt from @requires.NAME
    on itself (a gate cannot require itself). This allows feature-level
    @requires tags to coexist with a @gate tag on the defining scenario.
    """
    context.sandbox = Sandbox(project_dir=PROJECT_DIR)

    # Combine feature-level and scenario-level tags.
    all_tags = list(scenario.tags) + list(scenario.feature.tags)
    required = set(_extract_gate_names(all_tags, _REQUIRES_PREFIX))
    defined = set(_extract_gate_names(all_tags, _GATE_PREFIX))
    # A gate scenario is exempt from requiring itself.
    required -= defined
    for gate_name in sorted(required):
        result = _gate_results.get(gate_name)
        if result is None:
            scenario.skip(f"Gate '{gate_name}' has not run yet")
            return
        if not result:
            scenario.skip(f"Gate '{gate_name}' failed — skipping dependent scenario")
            return


def after_scenario(context, scenario):
    """Per-scenario teardown: record gate results and restore state.

    If the scenario is tagged @gate.NAME, its pass/fail status is
    recorded for downstream @requires.NAME scenarios.  A scenario is
    considered passed if its status is 'passed' (not 'failed',
    'undefined', or 'skipped').

    Cleans up any temporary stash directories, vision temp dirs, and
    restores protected files/dirs to their pre-scenario state.
    """
    # Record gate results.
    all_tags = list(scenario.tags) + list(scenario.feature.tags)
    gates = _extract_gate_names(all_tags, _GATE_PREFIX)
    for gate_name in gates:
        passed = scenario.status == "passed"
        _gate_results[gate_name] = passed
        if passed:
            logger.info("Gate '%s' PASSED", gate_name)
        else:
            logger.warning("Gate '%s' FAILED (status=%s)", gate_name, scenario.status)

    stash = PROJECT_DIR / ".scenario-stash-inventory"
    if stash.exists():
        shutil.rmtree(stash)
    # Clean up legacy vision temp dirs if any step left one behind
    vision_tmpdir = getattr(context, "vision_tmpdir", None)
    if vision_tmpdir and os.path.isdir(vision_tmpdir):
        shutil.rmtree(vision_tmpdir, ignore_errors=True)
    if SESSION_BACKUP_DIR.exists():
        _restore_state(SESSION_BACKUP_DIR, PROJECT_DIR)
