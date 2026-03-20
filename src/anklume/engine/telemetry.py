"""Telemetry — métriques d'usage opt-in (§33)."""

from __future__ import annotations

import contextlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "anklume"
CONFIG_PATH = CONFIG_DIR / "telemetry.json"
EVENTS_PATH = CONFIG_DIR / "telemetry-events.jsonl"


@dataclass
class TelemetryEvent:
    """Événement de télémétrie."""

    command: str
    timestamp: str
    duration_ms: int
    success: bool
    error: str | None = None


@dataclass
class TelemetryStats:
    """Résumé agrégé des métriques."""

    total_events: int
    commands: dict[str, int]
    success_rate: float
    last_event: str | None


def is_enabled() -> bool:
    """Vérifie si la télémétrie est activée."""
    try:
        data = json.loads(CONFIG_PATH.read_text())
        return bool(data.get("enabled", False))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return False


def _ensure_dir() -> None:
    """Crée le répertoire de configuration si nécessaire."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def enable() -> None:
    """Active la télémétrie."""
    _ensure_dir()
    CONFIG_PATH.write_text(json.dumps({"enabled": True}))


def disable() -> None:
    """Désactive la télémétrie."""
    _ensure_dir()
    CONFIG_PATH.write_text(json.dumps({"enabled": False}))


def record_event(event: TelemetryEvent) -> None:
    """Enregistre un événement. Silencieux si désactivé ou erreur I/O."""
    try:
        if not is_enabled():
            return
        _ensure_dir()
        with EVENTS_PATH.open("a") as f:
            f.write(json.dumps(asdict(event)) + "\n")
    except OSError:
        pass


def get_stats() -> TelemetryStats:
    """Agrège les événements enregistrés."""
    try:
        lines = EVENTS_PATH.read_text().strip().split("\n")
        lines = [line for line in lines if line]
    except (FileNotFoundError, OSError):
        return TelemetryStats(
            total_events=0,
            commands={},
            success_rate=0.0,
            last_event=None,
        )

    if not lines:
        return TelemetryStats(
            total_events=0,
            commands={},
            success_rate=0.0,
            last_event=None,
        )

    events = []
    for line in lines:
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    commands: dict[str, int] = {}
    success_count = 0
    last_ts = None

    for ev in events:
        cmd = ev.get("command", "unknown")
        commands[cmd] = commands.get(cmd, 0) + 1
        if ev.get("success"):
            success_count += 1
        last_ts = ev.get("timestamp")

    total = len(events)
    return TelemetryStats(
        total_events=total,
        commands=commands,
        success_rate=success_count / total if total else 0.0,
        last_event=last_ts,
    )


def clear_events() -> None:
    """Supprime le fichier d'événements."""
    with contextlib.suppress(OSError):
        EVENTS_PATH.unlink(missing_ok=True)
