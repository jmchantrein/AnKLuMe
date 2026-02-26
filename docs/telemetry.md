# Local Telemetry

anklume includes opt-in, local-only telemetry to help you understand
your usage patterns. Data never leaves your machine.

## Privacy Guarantees

- **Default: DISABLED** (opt-in model)
- **Local-only**: data stored in `~/.anklume/telemetry/`, no network calls
- **Inspectable**: you can `cat ~/.anklume/telemetry/usage.jsonl` at any time
- **Deletable**: `anklume telemetry clear` removes everything
- **Minimal**: only target name, domain, duration, and exit code are logged
- **No PII**: no usernames, hostnames, IPs, secrets, or file contents

## Quick Start

```bash
anklume telemetry on       # Enable telemetry
anklume sync               # Normal workflow — events are logged automatically
anklume domain apply
anklume telemetry report   # View usage charts
```

## Makefile Targets

| Target | Description |
|--------|-------------|
| `anklume telemetry on` | Enable telemetry collection |
| `anklume telemetry off` | Disable telemetry (data preserved) |
| `anklume telemetry status` | Show state, event count, file size |
| `anklume telemetry clear` | Delete all telemetry data and state |
| `anklume telemetry report` | Terminal charts of usage patterns |

## What Is Logged

Each event is a single JSON line in `~/.anklume/telemetry/usage.jsonl`:

```json
{
  "timestamp": "2026-02-14T10:30:00+00:00",
  "target": "apply",
  "domain": null,
  "duration_seconds": 45.0,
  "exit_code": 0
}
```

| Field | Description |
|-------|-------------|
| `timestamp` | UTC ISO 8601 timestamp |
| `target` | Make target name (e.g., `sync`, `apply`, `lint`) |
| `domain` | Domain argument if `G=<group>` was passed, else `null` |
| `duration_seconds` | Wall-clock duration in seconds |
| `exit_code` | Command exit code (0 = success) |

## Tracked Targets

The following Make targets are wrapped with telemetry logging when
enabled:

- `sync` — PSOT generation
- `apply` — Full infrastructure deployment
- `apply-infra` — Infrastructure only
- `apply-provision` — Provisioning only
- `apply-limit` — Single domain deployment (includes domain in log)
- `test-generator` — pytest tests

Other targets run without telemetry overhead.

## Report

`anklume telemetry report` produces terminal charts showing:

1. **Target invocations** — which targets you use most
2. **Success vs failure** — overall success rate
3. **Average duration** — how long each target takes on average

Requires `plotext` for graphical output:

```bash
pip install plotext
```

Without `plotext`, a text-only fallback is displayed.

## Data Location

```
~/.anklume/
└── telemetry/
    ├── enabled        # Marker file (presence = enabled)
    └── usage.jsonl    # Event log (JSON Lines format)
```

## Script Usage

The telemetry script can also be used directly:

```bash
python3 scripts/telemetry.py on
python3 scripts/telemetry.py off
python3 scripts/telemetry.py status
python3 scripts/telemetry.py clear
python3 scripts/telemetry.py report
python3 scripts/telemetry.py log --target sync --duration 1.5 --exit-code 0
```
