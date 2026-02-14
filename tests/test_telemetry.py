"""Tests for the telemetry script (scripts/telemetry.py)."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import pytest  # noqa: E402
import telemetry  # noqa: E402


@pytest.fixture()
def telemetry_dir(tmp_path):
    """Override telemetry paths to use a temp directory."""
    tdir = tmp_path / ".anklume" / "telemetry"
    with (
        patch.object(telemetry, "TELEMETRY_DIR", tdir),
        patch.object(telemetry, "ENABLED_FILE", tdir / "enabled"),
        patch.object(telemetry, "USAGE_FILE", tdir / "usage.jsonl"),
    ):
        yield tdir


class TestEnableDisable:
    """Tests for enable/disable toggle."""

    def test_default_disabled(self, telemetry_dir):
        """Telemetry is disabled by default."""
        assert not telemetry.is_enabled()

    def test_enable(self, telemetry_dir):
        """Enabling creates the enabled marker file."""
        telemetry.enable()
        assert telemetry.is_enabled()
        assert (telemetry_dir / "enabled").exists()

    def test_disable(self, telemetry_dir):
        """Disabling removes the enabled marker file."""
        telemetry.enable()
        assert telemetry.is_enabled()
        telemetry.disable()
        assert not telemetry.is_enabled()

    def test_disable_when_already_disabled(self, telemetry_dir):
        """Disabling when already disabled is a no-op."""
        telemetry.disable()
        assert not telemetry.is_enabled()

    def test_enable_disable_toggle(self, telemetry_dir):
        """Toggle enable/disable multiple times."""
        assert not telemetry.is_enabled()
        telemetry.enable()
        assert telemetry.is_enabled()
        telemetry.disable()
        assert not telemetry.is_enabled()
        telemetry.enable()
        assert telemetry.is_enabled()


class TestLogEvent:
    """Tests for event logging."""

    def test_log_event_creates_jsonl(self, telemetry_dir):
        """Logging an event creates the JSONL file."""
        telemetry.enable()
        telemetry.log_event("sync", None, 1.5, 0)

        usage_file = telemetry_dir / "usage.jsonl"
        assert usage_file.exists()

        lines = usage_file.read_text().strip().split("\n")
        assert len(lines) == 1

        event = json.loads(lines[0])
        assert event["target"] == "sync"
        assert event["domain"] is None
        assert event["duration_seconds"] == 1.5
        assert event["exit_code"] == 0
        assert "timestamp" in event

    def test_log_event_appends(self, telemetry_dir):
        """Multiple log events append to the same file."""
        telemetry.enable()
        telemetry.log_event("sync", None, 1.0, 0)
        telemetry.log_event("apply", "pro", 5.2, 0)
        telemetry.log_event("lint", None, 0.8, 1)

        usage_file = telemetry_dir / "usage.jsonl"
        lines = usage_file.read_text().strip().split("\n")
        assert len(lines) == 3

        events = [json.loads(line) for line in lines]
        assert events[0]["target"] == "sync"
        assert events[1]["target"] == "apply"
        assert events[1]["domain"] == "pro"
        assert events[2]["target"] == "lint"
        assert events[2]["exit_code"] == 1

    def test_log_event_disabled_noop(self, telemetry_dir):
        """Logging when disabled does nothing."""
        telemetry.log_event("sync", None, 1.0, 0)

        usage_file = telemetry_dir / "usage.jsonl"
        assert not usage_file.exists()

    def test_log_event_fields(self, telemetry_dir):
        """Event contains exactly the expected fields."""
        telemetry.enable()
        telemetry.log_event("apply-limit", "homelab", 12.34, 0)

        usage_file = telemetry_dir / "usage.jsonl"
        event = json.loads(usage_file.read_text().strip())

        expected_keys = {"timestamp", "target", "domain", "duration_seconds", "exit_code"}
        assert set(event.keys()) == expected_keys

    def test_log_event_empty_domain_is_null(self, telemetry_dir):
        """Empty string domain is stored as null."""
        telemetry.enable()
        telemetry.log_event("sync", "", 1.0, 0)

        usage_file = telemetry_dir / "usage.jsonl"
        event = json.loads(usage_file.read_text().strip())
        assert event["domain"] is None

    def test_log_event_timestamp_utc(self, telemetry_dir):
        """Timestamp is in UTC ISO format."""
        telemetry.enable()
        telemetry.log_event("sync", None, 1.0, 0)

        usage_file = telemetry_dir / "usage.jsonl"
        event = json.loads(usage_file.read_text().strip())
        # UTC timestamps contain +00:00
        assert "+00:00" in event["timestamp"]


class TestStatus:
    """Tests for the status subcommand."""

    def test_status_when_disabled(self, telemetry_dir, capsys):
        """Status shows disabled when telemetry is off."""
        telemetry.status()
        output = capsys.readouterr().out
        assert "disabled" in output
        assert "Events: 0" in output

    def test_status_when_enabled(self, telemetry_dir, capsys):
        """Status shows enabled and event count."""
        telemetry.enable()
        telemetry.log_event("sync", None, 1.0, 0)
        telemetry.log_event("apply", None, 2.0, 0)

        telemetry.status()
        output = capsys.readouterr().out
        assert "enabled" in output
        assert "Events: 2" in output

    def test_status_enabled_no_events(self, telemetry_dir, capsys):
        """Status shows enabled with 0 events when no data file."""
        telemetry.enable()
        telemetry.status()
        output = capsys.readouterr().out
        assert "enabled" in output
        assert "Events: 0" in output


class TestClear:
    """Tests for the clear subcommand."""

    def test_clear_removes_data(self, telemetry_dir):
        """Clear removes usage data and enabled flag."""
        telemetry.enable()
        telemetry.log_event("sync", None, 1.0, 0)

        assert (telemetry_dir / "usage.jsonl").exists()
        assert (telemetry_dir / "enabled").exists()

        telemetry.clear()

        assert not (telemetry_dir / "usage.jsonl").exists()
        assert not (telemetry_dir / "enabled").exists()

    def test_clear_when_empty(self, telemetry_dir, capsys):
        """Clear when no data is a safe no-op."""
        telemetry.clear()
        output = capsys.readouterr().out
        assert "No telemetry data" in output


class TestLoadEvents:
    """Tests for loading events."""

    def test_load_events_empty(self, telemetry_dir):
        """Load events from non-existent file returns empty list."""
        assert telemetry.load_events() == []

    def test_load_events(self, telemetry_dir):
        """Load events returns all logged events."""
        telemetry.enable()
        telemetry.log_event("sync", None, 1.0, 0)
        telemetry.log_event("apply", "pro", 5.0, 0)

        events = telemetry.load_events()
        assert len(events) == 2
        assert events[0]["target"] == "sync"
        assert events[1]["target"] == "apply"


class TestReport:
    """Tests for the report subcommand."""

    def test_report_no_data(self, telemetry_dir, capsys):
        """Report with no data prints a message."""
        telemetry.report()
        output = capsys.readouterr().out
        assert "No telemetry data" in output

    def test_report_text_fallback(self, telemetry_dir, capsys):
        """Report falls back to text when plotext is not available."""
        telemetry.enable()
        telemetry.log_event("sync", None, 1.0, 0)
        telemetry.log_event("apply", None, 5.0, 0)
        telemetry.log_event("sync", None, 0.5, 0)

        # Mock plotext import failure
        with patch.dict("sys.modules", {"plotext": None}):
            telemetry.report()

        output = capsys.readouterr().out
        assert "text fallback" in output or "Total events: 3" in output


class TestHumanFormatting:
    """Tests for human-readable formatting helpers."""

    def test_human_size_bytes(self):
        assert telemetry._human_size(500) == "500.0 B"

    def test_human_size_kb(self):
        assert telemetry._human_size(2048) == "2.0 KB"

    def test_human_size_mb(self):
        assert telemetry._human_size(1048576) == "1.0 MB"

    def test_human_duration_seconds(self):
        assert telemetry._human_duration(30) == "30.0s"

    def test_human_duration_minutes(self):
        assert telemetry._human_duration(120) == "2.0m"

    def test_human_duration_hours(self):
        assert telemetry._human_duration(7200) == "2.0h"
