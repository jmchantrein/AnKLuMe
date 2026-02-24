# DECISIONS.md

Autonomous decisions made during implementation. These are
documented here for human review. Validated decisions may be
promoted to ADRs in `docs/ARCHITECTURE.md`.

---

## D-041: Lab framework split into runner + library

**Problem**: The lab-runner.sh script exceeded the 200-line limit
when implemented as a single file.

**Choice**: Split into `scripts/lab-runner.sh` (commands, main
dispatch) and `scripts/lab-lib.sh` (shared helpers: YAML parsing,
progress tracking, ANSI colors). The runner sources the library.

**Alternatives considered**:
- Single file with shellcheck disable for line count (violates KISS)
- Python implementation (would require new test patterns, heavier)

**Rationale**: Follows the existing project pattern (e.g., `snap.sh`
is standalone, `live-os-lib.sh` is sourced). Shell is appropriate
because the runner is a thin wrapper around `find`, `cat`, and
inline Python for YAML parsing.

---

## D-042: Three labs instead of five for initial framework

**Problem**: The roadmap lists five example labs. Implementing all
five would delay the framework delivery without adding structural
value.

**Choice**: Implement labs 01 (first deploy), 02 (network isolation),
and 03 (snapshots) as framework examples. Labs 04 (GPU) and 05
(security audit) deferred — they require running infrastructure.

**Rationale**: Three labs fully exercise the framework (schema
validation, step progression, solution display). Additional labs
can be added later without framework changes.

---

## D-043: Progress tracking via YAML in ~/.anklume/labs/

**Problem**: Lab progress needs to persist across sessions. Options:
SQLite database, JSON files, YAML files, environment variables.

**Choice**: YAML files in `~/.anklume/labs/<lab-id>/progress.yml`.

**Rationale**: Consistent with the project's YAML-first approach.
Human-readable, trivially parseable with the already-required PyYAML
dependency. No new dependencies. The `~/.anklume/` directory is
already used by telemetry and other features.

---

## D-044: Inline Python for YAML parsing in shell scripts

**Problem**: The lab runner needs to read `lab.yml` fields from
bash. Options: yq, Python inline, awk/grep hacks.

**Choice**: Inline Python via heredoc (`python3 - "$arg" <<'PYEOF'`),
consistent with the existing project pattern (disp.sh, console.sh,
ai-switch.sh all use this pattern).

**Rationale**: PyYAML is already a project dependency. No additional
binary (yq) required. Heredoc + sys.argv prevents command injection
(per D-036).
