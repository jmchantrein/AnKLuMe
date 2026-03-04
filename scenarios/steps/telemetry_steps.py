"""Step definitions for telemetry BDD scenarios.

Covers telemetry state management (enable/disable), event logging,
and event field validation. Telemetry state is isolated per scenario
via cleanup in the 'Given telemetry state is clean' step.
"""

import json
from pathlib import Path

from behave import given, then

TELEMETRY_DIR = Path.home() / ".anklume" / "telemetry"
ENABLED_FILE = TELEMETRY_DIR / "enabled"
USAGE_FILE = TELEMETRY_DIR / "usage.jsonl"


@given("telemetry state is clean")
def telemetry_clean(context):
    """Remove all telemetry state files for a clean test.

    Stores the previous state so after_scenario can restore it if needed.
    """
    context.telemetry_backup = {
        "enabled_existed": ENABLED_FILE.exists(),
        "usage_existed": USAGE_FILE.exists(),
        "usage_content": USAGE_FILE.read_bytes() if USAGE_FILE.exists() else None,
    }
    if USAGE_FILE.exists():
        USAGE_FILE.unlink()
    if ENABLED_FILE.exists():
        ENABLED_FILE.unlink()


@then("telemetry enabled file exists")
def telemetry_enabled_exists(context):
    assert ENABLED_FILE.exists(), (
        f"Expected {ENABLED_FILE} to exist, but it does not"
    )


@then("telemetry enabled file does not exist")
def telemetry_enabled_not_exists(context):
    assert not ENABLED_FILE.exists(), (
        f"Expected {ENABLED_FILE} to not exist, but it does"
    )


@then("telemetry usage file does not exist")
def telemetry_usage_not_exists(context):
    assert not USAGE_FILE.exists(), (
        f"Expected {USAGE_FILE} to not exist, but it does"
    )


@then("telemetry usage file has at least {count:d} event")
@then("telemetry usage file has at least {count:d} events")
def telemetry_usage_has_events(context, count):
    assert USAGE_FILE.exists(), (
        f"Expected {USAGE_FILE} to exist, but it does not"
    )
    lines = [
        line.strip() for line in USAGE_FILE.read_text().splitlines()
        if line.strip()
    ]
    assert len(lines) >= count, (
        f"Expected at least {count} events, found {len(lines)}"
    )


@then('telemetry last event has field "{field}" with value "{value}"')
def telemetry_last_event_field(context, field, value):
    assert USAGE_FILE.exists(), (
        f"Expected {USAGE_FILE} to exist"
    )
    lines = [
        line.strip() for line in USAGE_FILE.read_text().splitlines()
        if line.strip()
    ]
    assert lines, "No events in usage file"
    last_event = json.loads(lines[-1])
    assert field in last_event, (
        f"Field '{field}' not found in event: {last_event}"
    )
    actual = str(last_event[field])
    assert actual == value, (
        f"Expected field '{field}' = '{value}', got '{actual}'"
    )
