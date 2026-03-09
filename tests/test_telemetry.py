"""Tests telemetry — métriques d'usage opt-in (§33)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from anklume.engine.telemetry import (
    TelemetryEvent,
    TelemetryStats,
    clear_events,
    disable,
    enable,
    get_stats,
    is_enabled,
    record_event,
)


@pytest.fixture()
def telemetry_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirige le stockage telemetry vers un répertoire temporaire."""
    import anklume.engine.telemetry as mod

    monkeypatch.setattr(mod, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(mod, "CONFIG_PATH", tmp_path / "telemetry.json")
    monkeypatch.setattr(mod, "EVENTS_PATH", tmp_path / "telemetry-events.jsonl")
    return tmp_path


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


class TestTelemetryEvent:
    """Dataclass TelemetryEvent."""

    def test_create_event(self) -> None:
        event = TelemetryEvent(
            command="apply all",
            timestamp="2026-03-09T14:00:00",
            duration_ms=1500,
            success=True,
        )
        assert event.command == "apply all"
        assert event.success is True
        assert event.error is None

    def test_event_with_error(self) -> None:
        event = TelemetryEvent(
            command="status",
            timestamp="2026-03-09T14:00:00",
            duration_ms=200,
            success=False,
            error="FileNotFoundError",
        )
        assert event.success is False
        assert event.error == "FileNotFoundError"


class TestTelemetryStats:
    """Dataclass TelemetryStats."""

    def test_create_stats(self) -> None:
        stats = TelemetryStats(
            total_events=10,
            commands={"apply all": 5, "status": 3, "destroy": 2},
            success_rate=0.9,
            last_event="2026-03-09T14:00:00",
        )
        assert stats.total_events == 10
        assert stats.success_rate == 0.9


# ---------------------------------------------------------------------------
# Enable / Disable / is_enabled
# ---------------------------------------------------------------------------


class TestEnableDisable:
    """Activation et désactivation."""

    def test_enable_creates_config(self, telemetry_dir: Path) -> None:
        enable()
        config = json.loads((telemetry_dir / "telemetry.json").read_text())
        assert config["enabled"] is True

    def test_disable_writes_false(self, telemetry_dir: Path) -> None:
        enable()
        disable()
        config = json.loads((telemetry_dir / "telemetry.json").read_text())
        assert config["enabled"] is False

    def test_is_enabled_true(self, telemetry_dir: Path) -> None:
        enable()
        assert is_enabled() is True

    def test_is_enabled_false_after_disable(self, telemetry_dir: Path) -> None:
        enable()
        disable()
        assert is_enabled() is False

    def test_is_enabled_false_no_file(self, telemetry_dir: Path) -> None:
        assert is_enabled() is False

    def test_enable_creates_parent_dirs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import anklume.engine.telemetry as mod

        nested = tmp_path / "a" / "b" / "c"
        monkeypatch.setattr(mod, "CONFIG_DIR", nested)
        monkeypatch.setattr(mod, "CONFIG_PATH", nested / "telemetry.json")
        monkeypatch.setattr(mod, "EVENTS_PATH", nested / "events.jsonl")
        enable()
        assert (nested / "telemetry.json").is_file()


# ---------------------------------------------------------------------------
# record_event
# ---------------------------------------------------------------------------


class TestRecordEvent:
    """Enregistrement d'événements."""

    def _make_event(self, cmd: str = "status", success: bool = True) -> TelemetryEvent:
        return TelemetryEvent(
            command=cmd,
            timestamp="2026-03-09T14:00:00",
            duration_ms=100,
            success=success,
        )

    def test_record_writes_jsonl(self, telemetry_dir: Path) -> None:
        enable()
        record_event(self._make_event())
        events_file = telemetry_dir / "telemetry-events.jsonl"
        assert events_file.is_file()
        lines = events_file.read_text().strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["command"] == "status"

    def test_record_appends(self, telemetry_dir: Path) -> None:
        enable()
        record_event(self._make_event("cmd1"))
        record_event(self._make_event("cmd2"))
        lines = (telemetry_dir / "telemetry-events.jsonl").read_text().strip().split("\n")
        assert len(lines) == 2

    def test_record_silent_when_disabled(self, telemetry_dir: Path) -> None:
        # Pas d'enable()
        record_event(self._make_event())
        events_file = telemetry_dir / "telemetry-events.jsonl"
        assert not events_file.exists()

    def test_record_silent_on_io_error(
        self, telemetry_dir: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import anklume.engine.telemetry as mod

        enable()
        # Pointer vers un chemin impossible
        monkeypatch.setattr(mod, "EVENTS_PATH", Path("/nonexistent/dir/events.jsonl"))
        # Ne doit pas lever d'exception
        record_event(self._make_event())

    def test_record_with_error_field(self, telemetry_dir: Path) -> None:
        enable()
        event = TelemetryEvent(
            command="apply all",
            timestamp="2026-03-09T14:00:00",
            duration_ms=500,
            success=False,
            error="ValueError",
        )
        record_event(event)
        data = json.loads((telemetry_dir / "telemetry-events.jsonl").read_text().strip())
        assert data["error"] == "ValueError"
        assert data["success"] is False


# ---------------------------------------------------------------------------
# get_stats
# ---------------------------------------------------------------------------


class TestGetStats:
    """Agrégation des métriques."""

    def test_stats_empty(self, telemetry_dir: Path) -> None:
        stats = get_stats()
        assert stats.total_events == 0
        assert stats.commands == {}
        assert stats.success_rate == 0.0
        assert stats.last_event is None

    def test_stats_with_events(self, telemetry_dir: Path) -> None:
        enable()
        record_event(TelemetryEvent("apply all", "2026-03-09T14:00:00", 100, True))
        record_event(TelemetryEvent("apply all", "2026-03-09T14:01:00", 200, True))
        record_event(TelemetryEvent("status", "2026-03-09T14:02:00", 50, False, "err"))
        stats = get_stats()
        assert stats.total_events == 3
        assert stats.commands["apply all"] == 2
        assert stats.commands["status"] == 1
        assert abs(stats.success_rate - 2 / 3) < 0.01
        assert stats.last_event == "2026-03-09T14:02:00"

    def test_stats_all_success(self, telemetry_dir: Path) -> None:
        enable()
        record_event(TelemetryEvent("status", "2026-03-09T14:00:00", 50, True))
        stats = get_stats()
        assert stats.success_rate == 1.0


# ---------------------------------------------------------------------------
# clear_events
# ---------------------------------------------------------------------------


class TestClearEvents:
    """Nettoyage des événements."""

    def test_clear_removes_file(self, telemetry_dir: Path) -> None:
        enable()
        record_event(TelemetryEvent("status", "2026-03-09T14:00:00", 50, True))
        events_file = telemetry_dir / "telemetry-events.jsonl"
        assert events_file.is_file()
        clear_events()
        assert not events_file.exists()

    def test_clear_no_file_no_error(self, telemetry_dir: Path) -> None:
        # Pas de fichier → pas d'erreur
        clear_events()
