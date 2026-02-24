# DECISIONS.md — Autonomous decisions log

Decisions made during development that are pending user review.
Each entry documents the context, decision, and rationale.

---

## 2026-02-25: Phase 39 — LLM sanitization proxy

### ai_provider / ai_sanitize as domain-level fields

**Context**: The sanitization proxy needs configuration per domain.
It could be global (one policy for all domains) or per-domain.

**Decision**: Domain-level fields (`ai_provider`, `ai_sanitize`)
because different domains have fundamentally different sensitivity
levels. An `admin` domain should always sanitize cloud requests,
while a `disposable` sandbox may not need it.

### Default ai_sanitize based on ai_provider

**Context**: Users who set `ai_provider: cloud` likely want
sanitization but may forget to enable it explicitly.

**Decision**: Auto-default `ai_sanitize: true` when `ai_provider`
is `cloud` or `local-first`. Auto-default `false` for `local`.
This follows the project principle of safe defaults (ADR-018,
ADR-020 precedent: safe by default, explicit opt-out).

### Pattern-based detection, not ML-based

**Context**: Could use an ML classifier to detect sensitive data,
or use curated regex patterns.

**Decision**: Regex patterns. They are predictable, auditable,
have zero false positives from model drift, and require no GPU
resources. IaC identifiers follow strict naming conventions
(ADR-038 IP scheme, Incus naming) that are ideal for regex.

### ai_sanitize accepts "always" as a string value

**Context**: `true`/`false` covers most cases, but some users
need sanitization even for local requests (compliance, shared
infrastructure).

**Decision**: Accept `"always"` as a third value. This is a
string, not a boolean, to distinguish it from `true`. The
generator validates the enum: `true | false | "always"`.
