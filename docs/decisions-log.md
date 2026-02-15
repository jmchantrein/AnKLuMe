# Decisions Log

Autonomous implementation decisions made during development.
This file tracks choices made **without human review** — decisions where
the AI agent had to make a judgment call during autonomous work.

Each decision documents:
- The problem encountered
- The choice made and alternatives considered
- The rationale

The human reviews these decisions and validates (y), rejects (n), or
comments (c) during interactive sessions. Validated decisions are
promoted to ADRs in [ARCHITECTURE.md](ARCHITECTURE.md) if architectural,
or documented in [SPEC.md](SPEC.md) / [ROADMAP.md](ROADMAP.md) if
implementation-level.

For architecture-level decisions, see [ARCHITECTURE.md](ARCHITECTURE.md)
(ADR-001 to ADR-031).

---

## D-036: Command injection fix — heredoc + sys.argv pattern

**Problem**: Multiple shell scripts (`ai-switch.sh`, `ai-config.sh`,
`ai-test-loop.sh`) interpolated shell variables directly into inline
Python code, enabling command injection via crafted `infra.yml` values.

**Choice**: Replace all `python3 -c "..."` with `python3 - "$arg" <<'PYEOF'`
heredocs + `sys.argv` for parameter passing. Alternatives considered:
(a) jq/yq instead of Python — not all operations expressible,
(b) dedicated Python scripts — excessive file proliferation.

**Rationale**: Heredocs with single-quoted delimiters prevent shell
expansion inside the Python code. `sys.argv` provides clean parameter
passing without any interpolation.

**Status**: validated

---

## D-037: Credential injection via stdin instead of echo

**Problem**: `agent-fix.sh` and `agent-develop.sh` used
`echo 'export ANTHROPIC_API_KEY=...'` which exposes the key in `ps aux`.

**Choice**: Replace with `printf ... | incus file push - <path>` to
pass the key via stdin (never appears in process list). Alternative:
write to temp file then push — adds cleanup complexity.

**Rationale**: stdin piping is the simplest secure pattern, no temp
files, no process list exposure.

**Status**: validated

---

## D-038: nftables content validation before deployment

**Problem**: `deploy-nftables.sh` pulled rules from the admin container
and applied them without checking content. A compromised admin container
could inject arbitrary nftables rules.

**Choice**: Add two checks before syntax validation: (1) verify all
`table` definitions are `inet anklume` only, (2) reject dangerous
patterns (`flush ruleset`, `delete table inet filter`, `drop input
policy`).

**Rationale**: Defense in depth — the deploy script runs on the host
and should not blindly trust container output.

**Status**: validated

---

## D-039: Post-enrichment re-validation in generate.py

**Problem**: `enrich_infra()` (auto-creates sys-firewall, network
policies) runs after `validate()`. Auto-created resources could
introduce IP collisions or invalid references not caught by the
initial validation pass.

**Choice**: Add a second `validate()` call after `enrich_infra()`.
Alternative: merge enrichment into validation — violates single
responsibility.

**Rationale**: Simple, defensive, catches any edge case where
enrichment introduces conflicts.

**Status**: validated

---

## D-040: MANAGED_RE.sub count=1

**Problem**: `re.sub()` without `count=1` replaces ALL occurrences of
the managed marker pattern. If a user's content (outside managed
sections) happens to contain `=== MANAGED ===` text, it gets corrupted.

**Choice**: Add `count=1` to replace only the first occurrence.

**Rationale**: Defensive — managed markers should appear exactly once
per file, but user content is unpredictable.

**Status**: validated

---

## D-041: YAML safe serialization in mine-experiences.py

**Problem**: `format_entries()` built YAML via f-string concatenation,
which could produce invalid YAML if commit messages contained special
characters (colons, quotes, newlines).

**Choice**: Replace with `yaml.dump()` for safe serialization.
Alternative: manual escaping — fragile and incomplete.

**Rationale**: `yaml.dump()` handles all edge cases correctly by design.

**Status**: validated

---

## D-042: dev_agent_runner CLAUDE.md — check existence instead of self-copy

**Problem**: The role had a `copy` task with `src` pointing to the same
path as `dest` inside the container — effectively a no-op that could
fail if the file didn't exist yet.

**Choice**: Replace with `stat` + `debug` warning. Alternative:
template the CLAUDE.md — but it's a user file, not a role responsibility.

**Rationale**: The role should verify prerequisites, not create user
content. The repo should be cloned first (which includes CLAUDE.md).

**Status**: validated

---

## D-043: SPEC.md role table cleanup

**Problem**: SPEC.md referenced a non-existent `incus_storage` role and
was missing 6 roles added in later phases (incus_nftables,
incus_firewall_vm, incus_images, incus_nesting, dev_test_runner,
dev_agent_runner).

**Choice**: Remove phantom role, add all missing roles to the
appropriate phase tables.

**Rationale**: SPEC.md must accurately reflect the actual codebase.

**Status**: validated

---

## D-044: PSOT coherence — consume instance_profiles and instance_storage_volumes

**Problem**: The PSOT generator writes `instance_profiles` (list of
profile names) and `instance_storage_volumes` (dict of volume configs)
to host_vars, but the `incus_instances` role never consumed them.
Profiles declared in infra.yml were silently ignored. Storage volumes
were declared but never created.

**Choice**: Extend `incus_instances` rather than creating new roles.
- Profiles: pass `--profile` flags at `incus launch` time + reconcile
  existing instances via `incus profile assign`
- Volumes: create with `incus storage volume create`, set size, attach
  as disk devices to instances
- Default pool configurable via `incus_instances_default_pool`

**Alternatives considered**:
- Separate `incus_storage` role: rejected (KISS — volumes are
  semantically tied to instances, same pattern as instance_devices)
- Separate `incus_profile_assign` role: rejected (profile assignment
  is part of instance lifecycle, not profile management)

**Rationale**: The PSOT model requires that every generated variable
has a consumer. Dead variables create false expectations for users.

**Status**: validated

---

## D-045: Local telemetry — plotext for charts, ~/.anklume/ for data

**Problem**: Phase 19b requires local-only usage analytics. Need to
choose a data location, chart library, and integration strategy.

**Choice**: Store data in `~/.anklume/telemetry/` (consistent with
user-specific state), use plotext for terminal charts (pure Python,
no browser needed), and use a Makefile `define` wrapper to instrument
key targets with minimal overhead. When telemetry is disabled (default),
the wrapper checks for a file's existence and runs the command directly
with zero overhead.

**Alternatives considered**:
(a) Store in project directory — rejected (user data should not be
committed to git, and different users on the same machine would collide).
(b) Use matplotlib — rejected (requires display backend, overkill for
terminal output).
(c) Separate shell script wrapper — rejected (Makefile `define` is
simpler and avoids an extra file).

**Rationale**: `~/.anklume/` is user-scoped and persistent across
projects. plotext renders directly in the terminal with no dependencies
beyond pip. The file-existence check for enabled state has negligible
overhead.

**Status**: validated

---

## D-046: AST-based call graph fallback for pyan3 incompatibility

**Problem**: pyan3 (the recommended call graph generator) crashes with
Python 3.13 due to a `CallGraphVisitor.__init__()` argument conflict.
The ROADMAP specifies pyan3 as the tool for `make call-graph`.

**Choice**: Implement a two-tier strategy: try pyan3 first (best output
quality), fall back to a custom AST-based call graph generator using
Python's built-in `ast` module. The fallback parses function definitions
and call expressions to build a DOT graph. Alternatives considered:
(a) wait for pyan3 fix — blocks delivery,
(b) use a different tool (code2flow, etc.) — adds another dependency,
(c) skip call-graph entirely — loses a spec deliverable.

**Rationale**: The AST fallback uses only the standard library, works
with any Python version, and produces a usable (if less detailed) call
graph. pyan3 is tried first so users with compatible versions get the
better output.

**Status**: validated

---

## D-047: little-timmy skipped for Ansible unused variable detection

**Problem**: The ROADMAP mentions little-timmy for Ansible unused
variable detection, but it is not readily available as a standard pip
package and has limited community adoption.

**Choice**: Skip little-timmy and focus on vulture (Python) and
shellcheck SC2034 (Shell) for dead code detection. Document the
decision. Ansible unused variables can be caught by ansible-lint
rules (which are already enforced in CI).

**Rationale**: Adding a niche, hard-to-install tool provides marginal
value when ansible-lint already covers Ansible variable validation.
KISS principle.

**Status**: validated

---

## D-048: Golden images use 'pristine' snapshot convention

**Problem**: Phase 20b requires golden image management. Need a
convention to identify which instances are golden images and a strategy
for the create/derive/publish workflow.

**Choice**: Use a fixed snapshot name `pristine` as the marker for
golden images. An instance is a golden image if and only if it has a
snapshot named `pristine`. The `create` command stops the instance and
creates/replaces this snapshot. `derive` uses `incus copy <name>/pristine`
for CoW cloning. `publish` uses `incus publish <name>/pristine`.

**Alternatives considered**:
(a) Use instance metadata/labels — requires Incus API calls, more
complex, not all Incus versions support labels well.
(b) Separate tracking file — adds state outside Incus, can get stale.
(c) Any snapshot name — no reliable way to identify golden images.

**Rationale**: The `pristine` snapshot convention is simple, discoverable
(list snapshots to find golden images), and works with all Incus storage
backends. No external state needed.

**Status**: validated

---

## D-049: File transfer via pipe — no intermediate disk write

**Problem**: Phase 20d requires file transfer between instances. The
implementation must choose how to move data between containers that
may be in different Incus projects.

**Choice**: Use `incus file pull SRC - | incus file push - DST` pipe
pattern. The file content streams through the admin container's stdout
without being written to disk. Alternatives considered:
(a) `incus file pull` to temp file then `incus file push` — wastes
disk space and requires cleanup,
(b) shared volume mount — requires instance restart and volume setup,
(c) network transfer via scp/rsync — requires network access between
domains which is blocked by nftables isolation.

**Rationale**: The pipe pattern is the simplest approach that works
within the Incus socket model (ADR-004). No temp files, no network
needed, no volume management. Works across projects since each side
specifies its own `--project` flag.

**Status**: validated

---

## D-050: Disposable instances — shell script with Incus --ephemeral

**Problem**: Phase 20a requires on-demand, auto-destroyed instances.
Need to decide whether to use an Ansible role, a Python script, or a
shell script for the implementation.

**Choice**: Implement as a standalone shell script (`scripts/disp.sh`)
wrapping `incus launch --ephemeral`. The script reads the default OS
image from `infra.yml` via a Python one-liner (heredoc + sys.argv
pattern for safety), generates timestamped names (`disp-YYYYMMDD-HHMMSS`),
and supports multiple modes: interactive shell, command execution,
console attach, and background launch.

**Alternatives considered**:
(a) Ansible role — rejected (disposable instances are imperative
one-shot operations, same rationale as ADR-013 for snapshots),
(b) Python script — rejected (shell is simpler for wrapping CLI
commands, matches snap.sh precedent),
(c) Incus alias — rejected (too limited for multi-mode behavior).

**Rationale**: Shell script follows the snap.sh precedent (ADR-013)
for imperative operations. The `--ephemeral` flag is a native Incus
feature that handles auto-destruction at the daemon level — no
external cleanup needed. Reading the default image from `infra.yml`
keeps the PSOT model consistent.

**Status**: validated

---

## D-051: MCP via official SDK (FastMCP) over stdio

**Problem**: Phase 20c requires MCP inter-container services. Need to
decide between the official `mcp` Python SDK and a custom JSON-RPC
implementation.

**Choice**: Use the official MCP Python SDK (`pip install mcp`) with
FastMCP for the server and ClientSession for the client. Transport is
stdio, mapping naturally to `incus exec` and Incus proxy devices.

**Alternatives considered**:
(a) Custom stdlib-only JSON-RPC — rejected (maintainability concern:
as MCP usage grows, a custom implementation becomes a liability; the
official SDK handles protocol evolution, capability negotiation, and
transport framing correctly).
(b) Custom Unix socket server — rejected (requires socket management,
daemon lifecycle; stdio is simpler).
(c) HTTP REST API — rejected (requires network access between domains,
conflicts with nftables isolation).

**Rationale**: The official SDK provides correct protocol implementation,
automatic capability discovery, type-safe tool definitions via decorators,
and future-proofing as MCP evolves. The `pip install mcp` dependency is
acceptable — AnKLuMe already requires pip packages (pyyaml, pytest,
libtmux). The stdio transport maps naturally to `incus exec` and Incus
proxy devices.

**Status**: pending review

---

## D-052: Tor + CUPS as shell scripts, not Ansible roles

**Problem**: Phase 20e requires Tor gateway and CUPS container setup.
Need to decide between Ansible roles and shell scripts.

**Choice**: Implement as standalone shell scripts (`scripts/tor-gateway.sh`,
`scripts/sys-print.sh`) wrapping `incus exec` commands. Same approach as
Phase 20a-d scripts (disp.sh, golden.sh, transfer.sh).

**Alternatives considered**:
(a) Ansible roles — rejected (these are one-shot setup operations, not
declarative reconciliation; same rationale as ADR-013).
(b) Python scripts — rejected (shell wrapping CLI commands is simpler,
matches existing precedent).

**Rationale**: Consistency with the Phase 20 pattern: imperative operations
as shell scripts, declarative infrastructure as Ansible roles. Config files
are pushed via `incus file push` from heredocs or printf, avoiding nested
quoting issues. The `find_project()` pattern with stdin-piped JSON ensures
safe parameter passing (heredoc + sys.argv pattern from D-036).

**Status**: pending review
