"""Behave environment hooks for anklume E2E scenario tests.

Replaces the pytest fixtures from the former conftest.py with behave
lifecycle hooks. Manages session-level backup/restore and per-scenario
sandbox creation.

Usage:
    python3 -m behave scenarios/ --no-capture -v
    python3 -m behave scenarios/best_practices/ --no-capture -v
    python3 -m behave scenarios/bad_practices/ --no-capture -v
"""

import logging
import os
import shutil

from scenarios.support import (
    PROJECT_DIR,
    SESSION_BACKUP_DIR,
    Sandbox,
    _backup_state,
    _restore_state,
)

logger = logging.getLogger("anklume.scenarios")


def before_all(context):
    """Session-level setup: environment variables and crash-safe backup.

    Sets environment variables to skip host subnet conflict detection
    and network safety checks (scenario tests may run in sandboxes
    without internet connectivity). Restores from a previous crash
    backup if one exists, then creates a fresh session backup.
    """
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


def before_scenario(context, scenario):
    """Per-scenario setup: create a fresh Sandbox instance."""
    context.sandbox = Sandbox(project_dir=PROJECT_DIR)


def after_scenario(context, scenario):
    """Per-scenario teardown: restore project state from session backup.

    Cleans up any temporary stash directories, vision temp dirs, and
    restores protected files/dirs to their pre-scenario state.
    """
    stash = PROJECT_DIR / ".scenario-stash-inventory"
    if stash.exists():
        shutil.rmtree(stash)
    # Clean up legacy vision temp dirs if any step left one behind
    vision_tmpdir = getattr(context, "vision_tmpdir", None)
    if vision_tmpdir and os.path.isdir(vision_tmpdir):
        shutil.rmtree(vision_tmpdir, ignore_errors=True)
    if SESSION_BACKUP_DIR.exists():
        _restore_state(SESSION_BACKUP_DIR, PROJECT_DIR)
