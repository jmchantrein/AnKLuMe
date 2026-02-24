# DECISIONS.md

Autonomous decisions made during Phase 38 implementation.
Pending human review. See [docs/decisions-log.md](docs/decisions-log.md)
for validated decisions from earlier phases.

---

## D-057: Heartbeat templates as OpenClaw workspace files, not systemd services

**Problem**: Phase 38 requires monitoring for per-domain OpenClaw
instances. The monitoring could be implemented as systemd timers
running inside the container, or as OpenClaw workspace instructions
that the agent executes via its built-in cron/skill system.

**Choice**: Implement as OpenClaw workspace files (HEARTBEAT.md,
CRON.md, skills/) deployed via Jinja2 templates. The agent uses
OpenClaw's native cron system to schedule checks, not systemd timers.

**Alternatives considered**:
(a) systemd timers + shell scripts -- rejected (duplicates OpenClaw's
cron capability, adds complexity, not reproducible from framework alone).
(b) Ansible scheduled tasks -- rejected (runs from controller, not from
the agent; breaks domain-scoping).

**Rationale**: OpenClaw already has a cron scheduler (`openclaw cron`).
Using it keeps monitoring within the agent's operational scope and
follows ADR-036 (reproducible from templates). The agent can adapt
its monitoring behavior by reading its HEARTBEAT.md instructions,
which is more flexible than static systemd units.

**Status**: pending review

---

## D-058: Domain-scoped monitoring only (no cross-domain checks)

**Problem**: OpenClaw agents could theoretically monitor the entire
infrastructure via the Incus socket. Should a per-domain agent check
resources outside its domain?

**Choice**: Each agent monitors only its own domain's Incus project.
Cross-domain monitoring requires explicit network policies and is
left to the admin domain's agent (if any).

**Alternatives considered**:
(a) Global monitoring from each agent -- rejected (violates domain
isolation principle, creates noisy duplicate alerts).
(b) Centralized monitoring agent -- deferred (could be added later
as a separate capability).

**Rationale**: Domain scoping aligns with anklume's isolation model.
An agent in the `pro` domain should only see `pro` containers. The
`incus list --project <project>` command naturally enforces this.

**Status**: pending review

---

## D-059: Heartbeat tasks split into separate included file

**Problem**: The `openclaw_server/tasks/main.yml` is already at 190
lines. Adding heartbeat deployment tasks would exceed the 200-line
limit (CLAUDE.md KISS principle).

**Choice**: Create `tasks/heartbeat.yml` and include it from `main.yml`
via `ansible.builtin.include_tasks`. This keeps each file under 200
lines and maintains single-responsibility.

**Alternatives considered**:
(a) Add tasks directly to main.yml -- rejected (would exceed 200 lines).
(b) Create a separate role -- rejected (heartbeat is part of openclaw
operational knowledge, not a standalone capability).

**Rationale**: Ansible's `include_tasks` is the standard mechanism for
splitting long task files. The heartbeat tasks share the same role
defaults and variable scope.

**Status**: pending review
