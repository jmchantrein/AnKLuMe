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
(ADR-001 to ADR-040).

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

**Problem**: `enrich_infra()` (auto-creates anklume-firewall, network
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
acceptable — anklume already requires pip packages (pyyaml, pytest,
libtmux). The stdio transport maps naturally to `incus exec` and Incus
proxy devices.

**Status**: validated

---

## D-052: Tor + CUPS as shell scripts, not Ansible roles

**Problem**: Phase 20e requires Tor gateway and CUPS container setup.
Need to decide between Ansible roles and shell scripts.

**Choice**: Implement as standalone shell scripts (`scripts/tor-gateway.sh`,
`scripts/cups-setup.sh`) wrapping `incus exec` commands. Same approach as
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

**Status**: validated

---

## D-053: pytest-bdd over behave for scenario testing

**Problem**: Phase 22 requires a BDD framework for Gherkin `.feature`
files. The two main Python options are pytest-bdd and behave.

**Choice**: Use pytest-bdd. Alternatives considered:
(a) behave — rejected (separate test runner, no pytest integration,
cannot reuse existing pytest fixtures and configuration),
(b) Custom parser — rejected (reinventing the wheel).

**Rationale**: pytest-bdd integrates natively with the existing pytest
infrastructure (fixtures, markers, conftest.py, CLI options). Scenarios
can share the same `python3 -m pytest` runner used for generator tests.
pytest-bdd has ~1.5k GitHub stars and active maintenance. Adding
"scenarios" to `testpaths` in pyproject.toml is sufficient — no
separate runner configuration needed.

**Status**: rejected — migrated to behave

**Review outcome (2026-02-25)**: behave est préféré pour les scénarios
Gherkin. behave est le framework BDD de référence en Python, avec un
meilleur support Gherkin natif (tables, outlines, tags). pytest reste
pour les tests unitaires et de propriétés. Les deux outils coexistent
sans duplication : pytest pour les tests techniques, behave pour les
scénarios BDD.

**Implementation (2026-02-25)**: Migration completed. pytest-bdd removed,
behave installed. `scenarios/conftest.py` replaced by `environment.py`
(behave hooks) + `support.py` (Sandbox class). Step files converted.
`test_bad_practices.py` and `test_best_practices.py` deleted (behave
auto-discovers). Makefile targets updated. All 21 features / 44 scenarios /
252 steps resolve correctly.

---

## D-054: Dashboard uses stdlib http.server, no Flask

**Problem**: Phase 21 requires a web dashboard. The ROADMAP mentions
Flask/FastAPI + htmx. Need to decide on the framework.

**Choice**: Use Python's `http.server` (stdlib) with htmx loaded from
CDN. No Flask or FastAPI dependency.

**Alternatives considered**:
(a) Flask — adds a pip dependency for what is essentially a read-only
status page with a few JSON endpoints. Flask would be warranted for a
multi-page app with forms and authentication, but the dashboard is
read-only and has 4 endpoints.
(b) FastAPI — even heavier (requires uvicorn + pydantic), overkill
for this use case.
(c) Streamlit — heavy dependency, not suitable for deployment.

**Rationale**: The dashboard is a single-file script with 4 endpoints.
stdlib `http.server` handles this trivially. htmx (loaded from CDN)
provides reactive auto-refresh without writing JavaScript. No pip
install needed to run the dashboard. This follows the project's
principle of minimizing external dependencies.

**Status**: validated with modification — migrated to FastAPI

**Review outcome (2026-02-25)**: http.server fonctionne pour la v1
lecture seule, mais ne permet pas d'évoluer facilement vers l'interactivité
(formulaires, WebSocket, authentification). Décision : migrer vers FastAPI
dès maintenant pour préparer les évolutions futures.

**Implementation (2026-02-25)**: Migration completed. `http.server`
replaced by FastAPI + uvicorn. All 4 routes preserved. htmx frontend
unchanged. `fastapi` and `uvicorn` added to `pyproject.toml` runtime deps
and `make init`.

---

## D-055: Clipboard bridging via incus file push/pull

**Problem**: Phase 21 requires controlled clipboard sharing between
host and containers. Need to decide the transport mechanism.

**Choice**: Use `incus file push/pull` to transfer clipboard content
to/from `/tmp/anklume-clipboard` in containers. Host-side clipboard
access via `wl-copy`/`wl-paste` (Wayland) or `xclip`/`xsel` (X11)
with auto-detection.

**Alternatives considered**:
(a) MCP clipboard tools (Phase 20c) — requires MCP server running in
the container, adds setup complexity for a simple copy/paste.
(b) Custom Wayland protocol integration — complex, non-portable,
requires understanding Wayland compositor internals.
(c) Shared volume mount — requires instance restart, breaks isolation
model.

**Rationale**: `incus file push/pull` works out of the box with any
container, requires no setup, no running daemon, and no network access.
It's the simplest mechanism that preserves the explicit-action security
model. Compatible with MCP clipboard tools (same file path).

**Status**: validated with enhancement — QubesOS-style clipboard security implemented

**Review outcome (2026-02-25)**: Le mécanisme `incus file push/pull`
est validé comme transport. Ajout d'un modèle de sécurité inspiré de
QubesOS :
- **Purge automatique** : le presse-papier est purgé après chaque
  collage (une seule utilisation par copie)
- **Purge au changement de domaine** : le presse-papier est vidé lors
  du switch de pane tmux vers un autre domaine
- **Timeout configurable** : purge automatique après N secondes
  d'inactivité (défaut raisonnable, ex: 30s)
- **Historique** : `~/.anklume/clipboard/` conserve les entrées purgées
  pour récupération via `anklume clipboard history` et `recall`
- **Warning directionnel** : avertissement visuel lors d'un collage
  depuis un domaine untrusted vers un domaine trusted
- **Pas de chiffrement** : les entrées historiques ne sont pas chiffrées
  (le répertoire `~/.anklume/` est déjà sur le host, protégé par les
  permissions UNIX)

**Implementation (2026-02-25)**: All features implemented in
`scripts/clipboard.sh`. New commands: `history`, `recall`, `purge`.
`ANKLUME_CLIPBOARD_TIMEOUT` env var (default 30s). Trust-level warning
on copy-from untrusted/disposable domains. History stored in
`~/.anklume/clipboard/`. Tmux domain-switch purge implemented via
`scripts/hooks/tmux-domain-switch.sh` — registered as an
`after-select-pane` hook in `scripts/console.py` (`create_session`).

---

## D-056: Desktop config as Python generator, not static configs

**Problem**: Phase 21 requires desktop environment integration for
Sway, foot terminal, and .desktop entries. Need to decide between
static config files or a generator script.

**Choice**: A generator script (`scripts/desktop_config.py`) that reads
`infra.yml` and outputs environment-specific configs. Generates Sway
rules, foot profiles, and .desktop files into a `desktop/` directory.

**Alternatives considered**:
(a) Static config files — would not adapt to user's infra.yml, require
manual editing per deployment.
(b) Ansible role — overkill for generating a few text files, and desktop
config is host-side (not container-side).
(c) Template files — would need a separate rendering step.

**Rationale**: The generator reads trust levels and machine names from
infra.yml, ensuring desktop configs always match the actual infrastructure.
Output to `desktop/` (gitignored) lets users copy what they need. Same
pattern as `scripts/console.py` (reads infra.yml, generates output).

**Status**: validated

---

## D-058: Phase 41 — Three-tier role resolution with Galaxy integration

**Problem**: anklume lacked a mechanism for leveraging official Ansible
Galaxy roles (e.g., `geerlingguy.docker`), forcing custom implementations
for common software installations.

**Choice**: Implement a three-tier `roles_path` priority:
`roles_custom/ > roles/ > roles_vendor/`. Galaxy roles are declared in
`requirements.yml` (roles section) and installed to `roles_vendor/` via
`make init`. User overrides go in `roles_custom/` (gitignored).

**Alternatives considered**:
(a) Single roles directory with Galaxy roles mixed in — pollutes the
framework's own roles.
(b) Collections only — Galaxy roles are different from collections and
need a separate install path.
(c) Git submodules — poor UX, version pinning harder.

**Rationale**: The three-tier pattern mirrors how anklume already handles
overrides (user > framework > vendor). `roles_vendor/` is gitignored to
keep the repo clean. ADR-045 formalized this decision.

**Status**: validated

---

## D-059: Phase 42 — Desktop plugin system with schema-driven interface

**Problem**: The desktop configuration generator (Phase 21) was tightly
coupled to Sway. Users with GNOME, KDE, or Hyprland couldn't benefit.

**Choice**: Create a plugin system under `plugins/desktop/<engine>/`
with a standardized interface: `detect.sh` (is this DE active?) and
`apply.sh` (apply domain config). A YAML schema
(`plugins/desktop/plugin.schema.yml`) defines the contract. The
orchestrator script (`scripts/desktop-plugin.sh`) discovers, validates,
and invokes plugins.

**Alternatives considered**:
(a) Single monolithic script with if/elif for each DE — poor extensibility.
(b) Ansible role per DE — overkill for client-side config that runs on
the host, not in containers.
(c) Python plugin system — shell scripts are more appropriate for DE
detection and config file generation.

**Rationale**: The plugin pattern is extensible (add a directory, get a
new DE), testable (each plugin validated independently), and follows the
framework's "detect then apply" pattern. Trust-level colors in the schema
mirror the console QubesOS-style visual identification.

**Status**: validated

---

## D-060: Phase 31 — Toram copy integrity verification

**Problem**: The `anklume-toram` initramfs hook copied the squashfs root
image to RAM without verifying the copy was complete. A partial copy
(e.g., disk error, tmpfs full) would leave an unusable root filesystem.

**Choice**: Added post-copy size verification comparing `stat -c %s` of
source and destination. If sizes differ, the copy is removed and the
hook returns an error, falling back to disk-based boot.

**Rationale**: Defense in depth for a critical boot path. The check adds
negligible overhead (two stat calls) but prevents silent boot failures
from corrupted RAM copies.

**Status**: validated

---

## D-057: Phase 22 — BDD scenarios use generator directly, not `make sync`

**Problem**: All 17 BDD scenario features used `make sync` which requires
running inside `anklume-instance` (the admin container). This meant
15/30+ scenarios failed on the host, making them untestable during
development.

**Choice**: Updated all generator-only scenarios to call
`python3 scripts/generate.py infra.yml` directly instead of `make sync`.
Scenarios that require Incus (deployment, snapshots) still use `make`
targets and are gated behind `we are in a sandbox environment`.

**Alternatives considered**:
(a) Skip all scenarios on host — defeats the purpose of testing.
(b) Remove `require_container` check — would break production safety.
(c) Add a `SKIP_CONTAINER_CHECK=1` env var — adds complexity and could
be misused.

**Rationale**: Generator scenarios only test `scripts/generate.py` which
runs anywhere. Separating "generator validation" from "deployment testing"
makes the BDD suite useful in both development and sandbox contexts.
Result: 40 passed (from 0 on host), 4 legitimately skipped.

Also fixed the `add_domain_to_infra` step which used legacy `base_subnet`
syntax incompatible with ADR-038 addressing convention.

**Status**: validated

---

## D-061: Phase numbering — three branches merged as 44/45/46

**Problem**: Three remote branches independently proposed "Phase 44":
- `claude/audit-testing-gherkin-ZwzaI` → test infrastructure consolidation
- `claude/improve-documentation-0INTB` → MkDocs documentation site
- `claude/anklume-security-audit-a3ooi` → security hardening from audit

All were based on commit `4a6aa27` (pre-Live-ISO work). Merging all
three as "Phase 44" would create numbering chaos.

**Choice**: Assign sequential numbers based on implementation priority:
- Phase 44: Test Infrastructure Consolidation (has actual code deliverables)
- Phase 45: Documentation Site (MkDocs Material + Mermaid + CI)
- Phase 46: Security Hardening (from operational audit)

**Alternatives considered**:
(a) Single mega-Phase 44 combining all three — too broad, violates KISS
(b) Cherry-pick only one branch — wastes valid work from other branches
(c) Security first — reasonable, but testing has concrete code ready

**Rationale**: Testing consolidation already shipped partial code (Makefile
targets, test-summary.sh, Gherkin fixes). Documentation and security are
roadmap entries only. Ordering by implementation readiness minimizes
context-switching.

**Status**: pending review

---

## D-062: Security audit merged as documentation, not as blocking findings

**Problem**: The security audit branch (`docs/security-audit-operational.md`)
contains 12 findings rated CRITICAL to LOW. The previous agent analysis
recommended "NOT merging as-is" due to alarming findings without actionable
solutions.

**Choice**: Merged the audit document as-is (it IS well-structured and
constructive) and created Phase 46 as the roadmap entry for implementing
the fixes. The audit document serves as reference documentation, not as a
blocker.

**Alternatives considered**:
(a) Reject the branch entirely — loses valuable security analysis
(b) Rewrite the audit with softer language — dishonest
(c) Merge only the ROADMAP entry, not the audit doc — loses context

**Rationale**: The executive summary correctly states the architecture is
"fundamentally sound." FINDING-01 (Incus socket) and FINDING-02 (OpenClaw
proxy) are accepted architectural constraints documented in ADR-004 and
ADR-043. The remaining findings have concrete fixes in Phase 46 deliverables.

**Status**: pending review
