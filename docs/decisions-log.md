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
