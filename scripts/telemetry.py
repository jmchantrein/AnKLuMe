#!/usr/bin/env python3
"""anklume local telemetry — opt-in, local-only usage analytics.

Data is stored in ~/.anklume/telemetry/ and never leaves the machine.
Default: DISABLED. Enable with `make telemetry-on`.

Subcommands:
    on      Enable telemetry
    off     Disable telemetry
    status  Show state and event count
    clear   Delete all telemetry data
    log     Log a single event (called by Makefile wrapper)
    report  Terminal charts of usage patterns (requires plotext)
"""

import argparse
import contextlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

TELEMETRY_DIR = Path.home() / ".anklume" / "telemetry"
ENABLED_FILE = TELEMETRY_DIR / "enabled"
USAGE_FILE = TELEMETRY_DIR / "usage.jsonl"


def is_enabled():
    """Return True if telemetry is enabled."""
    return ENABLED_FILE.exists()


def enable():
    """Enable telemetry collection."""
    TELEMETRY_DIR.mkdir(parents=True, exist_ok=True)
    ENABLED_FILE.touch()
    print("Telemetry enabled. Data stored in:", TELEMETRY_DIR)


def disable():
    """Disable telemetry collection."""
    if ENABLED_FILE.exists():
        ENABLED_FILE.unlink()
    print("Telemetry disabled. Existing data preserved.")
    print("Run 'make telemetry-clear' to delete all data.")


def status():
    """Show telemetry status and event count."""
    state = "enabled" if is_enabled() else "disabled"
    print(f"Telemetry: {state}")
    print(f"Data directory: {TELEMETRY_DIR}")

    if USAGE_FILE.exists():
        count = sum(1 for _ in USAGE_FILE.open())
        size = USAGE_FILE.stat().st_size
        print(f"Events: {count}")
        print(f"File size: {_human_size(size)}")
    else:
        print("Events: 0")
        print("No data file yet.")


def clear():
    """Delete all telemetry data."""
    removed = False
    if USAGE_FILE.exists():
        USAGE_FILE.unlink()
        removed = True
    if ENABLED_FILE.exists():
        ENABLED_FILE.unlink()
        removed = True
    if TELEMETRY_DIR.exists():
        # Remove directory only if empty
        with contextlib.suppress(OSError):
            TELEMETRY_DIR.rmdir()
        # Try removing parent too
        with contextlib.suppress(OSError):
            TELEMETRY_DIR.parent.rmdir()
    if removed:
        print("Telemetry data and state deleted.")
    else:
        print("No telemetry data to delete.")


def log_event(target, domain, duration, exit_code):
    """Log a single telemetry event to the JSONL file.

    Args:
        target: Make target name (e.g. "sync", "apply").
        domain: Domain argument if present, else None.
        duration: Duration in seconds (float).
        exit_code: Command exit code (int).
    """
    if not is_enabled():
        return

    TELEMETRY_DIR.mkdir(parents=True, exist_ok=True)

    event = {
        "timestamp": datetime.now(UTC).isoformat(),
        "target": target,
        "domain": domain if domain else None,
        "duration_seconds": round(float(duration), 2),
        "exit_code": int(exit_code),
    }

    with USAGE_FILE.open("a") as f:
        f.write(json.dumps(event) + "\n")


def load_events():
    """Load all events from the JSONL file. Returns a list of dicts."""
    if not USAGE_FILE.exists():
        return []
    events = []
    with USAGE_FILE.open() as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def report():
    """Generate terminal charts from telemetry data."""
    events = load_events()
    if not events:
        print("No telemetry data to report.")
        print("Enable telemetry with: make telemetry-on")
        return

    try:
        import plotext as plt
    except ImportError:
        print("plotext is required for terminal charts.")
        print("Install with: pip install plotext")
        _report_text_fallback(events)
        return

    _report_with_plotext(events, plt)


def _report_with_plotext(events, plt):
    """Generate terminal charts using plotext."""
    # Chart 1: Target frequency
    target_counts = {}
    for e in events:
        t = e["target"]
        target_counts[t] = target_counts.get(t, 0) + 1

    sorted_targets = sorted(target_counts.items(), key=lambda x: x[1], reverse=True)
    labels = [t[0] for t in sorted_targets[:15]]
    values = [t[1] for t in sorted_targets[:15]]

    plt.clear_figure()
    plt.bar(labels, values)
    plt.title("Target Invocations")
    plt.show()
    print()

    # Chart 2: Success vs failure
    success = sum(1 for e in events if e.get("exit_code", 0) == 0)
    failure = len(events) - success
    plt.clear_figure()
    plt.bar(["success", "failure"], [success, failure])
    plt.title("Success vs Failure")
    plt.show()
    print()

    # Chart 3: Average duration by target
    durations = {}
    for e in events:
        t = e["target"]
        d = e.get("duration_seconds", 0)
        if t not in durations:
            durations[t] = []
        durations[t].append(d)

    avg_labels = []
    avg_values = []
    for t, ds in sorted(durations.items(), key=lambda x: sum(x[1]) / len(x[1]), reverse=True)[:10]:
        avg_labels.append(t)
        avg_values.append(round(sum(ds) / len(ds), 1))

    plt.clear_figure()
    plt.bar(avg_labels, avg_values)
    plt.title("Average Duration (seconds)")
    plt.show()

    print(f"\nTotal events: {len(events)}")
    print(f"Unique targets: {len(target_counts)}")
    total_duration = sum(e.get("duration_seconds", 0) for e in events)
    print(f"Total time tracked: {_human_duration(total_duration)}")


def _report_text_fallback(events):
    """Simple text report when plotext is not available."""
    print("\n--- Telemetry Report (text fallback) ---")
    print(f"Total events: {len(events)}")

    target_counts = {}
    for e in events:
        t = e["target"]
        target_counts[t] = target_counts.get(t, 0) + 1

    success = sum(1 for e in events if e.get("exit_code", 0) == 0)
    failure = len(events) - success
    print(f"Success: {success}, Failure: {failure}")

    print("\nTarget invocations:")
    for t, c in sorted(target_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {t:<20s} {c}")

    total_duration = sum(e.get("duration_seconds", 0) for e in events)
    print(f"\nTotal time tracked: {_human_duration(total_duration)}")


def _human_size(size_bytes):
    """Convert bytes to human-readable size."""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def _human_duration(seconds):
    """Convert seconds to human-readable duration."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = seconds / 60
    if minutes < 60:
        return f"{minutes:.1f}m"
    hours = minutes / 60
    return f"{hours:.1f}h"


def main():
    parser = argparse.ArgumentParser(
        description="anklume local telemetry management",
        epilog="Data is stored locally in ~/.anklume/telemetry/ and never leaves the machine.",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("on", help="Enable telemetry")
    sub.add_parser("off", help="Disable telemetry")
    sub.add_parser("status", help="Show telemetry state and event count")
    sub.add_parser("clear", help="Delete all telemetry data")
    sub.add_parser("report", help="Terminal charts of usage patterns")

    log_parser = sub.add_parser("log", help="Log a telemetry event (used by Makefile)")
    log_parser.add_argument("--target", required=True, help="Make target name")
    log_parser.add_argument("--domain", default=None, help="Domain argument (if any)")
    log_parser.add_argument("--duration", required=True, type=float, help="Duration in seconds")
    log_parser.add_argument("--exit-code", required=True, type=int, help="Command exit code")

    args = parser.parse_args()

    if args.command == "on":
        enable()
    elif args.command == "off":
        disable()
    elif args.command == "status":
        status()
    elif args.command == "clear":
        clear()
    elif args.command == "report":
        report()
    elif args.command == "log":
        log_event(args.target, args.domain, args.duration, args.exit_code)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
