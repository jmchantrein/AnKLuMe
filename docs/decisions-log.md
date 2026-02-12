# Decisions Log

Autonomous implementation decisions made during Phases 7+.
Read this file to understand choices made without human review.

---

## Phase 7: Documentation + Publication

### D-001: Example directory structure

**Problem**: ROADMAP lists examples as flat files (`examples/student-sysadmin.infra.yml`)
but also says "each example accompanied by a README". Flat files + READMEs would be messy.

**Decision**: Use subdirectories per example:
```
examples/
├── README.md                    # Overview of all examples
├── student-sysadmin/
│   ├── infra.yml
│   └── README.md
├── teacher-lab/
│   ├── infra.yml
│   └── README.md
...
```

**Rationale**: KISS — one directory = one self-contained use case. Git-friendly.

### D-002: All example infra.yml files must pass PSOT validation

**Problem**: Examples are documentation but also runnable. Dead examples are worse
than no examples.

**Decision**: Add a pytest test that validates every `examples/*/infra.yml` against
`scripts/generate.py`'s `validate()` function. This ensures examples stay valid
as the generator evolves.

**Rationale**: TDD — if examples break, tests catch it.

### D-003: Pre-existing ansible-lint violations

**Problem**: `make lint` fails due to pre-existing violations in ollama_server,
open_webui, and incus_snapshots (command-instead-of-module, risky-shell-pipe,
var-naming[read-only]). These are not Phase 7 issues.

**Decision**: Note them but do not fix in Phase 7 branch. Phase 7 focuses on
docs/examples. Lint violations are tracked for a future fix pass.

### D-004: README_FR.md sync

**Problem**: ADR-011 requires French translation kept in sync. Phase 7 adds
significant new docs.

**Decision**: Update README_FR.md to match README.md changes. New docs
(quickstart, lab-tp, gpu-llm) are in English only per ADR-011 — no separate
French translation files for guides (README_FR.md covers the main README only).

### D-005: Documentation line count vs 200-line rule

**Problem**: CLAUDE.md states "No file over 200 lines" (KISS). The gpu-llm.md
guide is 275 lines. But existing project docs already exceed this: SPEC.md (337),
ARCHITECTURE.md (352), ROADMAP.md (777).

**Decision**: The 200-line rule applies to code files (roles, scripts, playbooks).
Documentation files are exempt when the content is cohesive and splitting would
hurt readability. gpu-llm.md covers a single topic (GPU+LLM setup) and splitting
it would create unnecessary navigation burden.

**Rationale**: KISS applies to complexity, not raw line count for prose.

### D-006: .gitignore pattern for infra.yml in examples

**Problem**: `.gitignore` had `infra.yml` as a global pattern, which also ignored
`examples/*/infra.yml`. Example infra files must be committed.

**Decision**: Changed `.gitignore` patterns from global to root-anchored:
`infra.yml` → `/infra.yml`, `inventory/` → `/inventory/`, etc. This ignores
user-specific files at the root but allows example files in subdirectories.

**Rationale**: Git anchored patterns (`/pattern`) match only at the repo root.
No need for `!` negation or force-add workarounds.

---
