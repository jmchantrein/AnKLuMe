# DECISIONS.md — Autonomous Implementation Decisions

Decisions made during overnight autonomous implementation.
Review and approve/decline each section.

---

## Phase 36: Naming Convention Migration

### Name mapping

| Old name | New name | Context |
|----------|----------|---------|
| `sys-firewall` (auto-created) | `anklume-firewall` | Already done (prior commit) |
| `sys-print` (container) | `shared-print` | Container in `shared` domain |
| `print-service` (domain) | `shared` | Domain for user-facing services |
| `examples/sys-print/` | `examples/shared-services/` | Example directory |

### Script naming

The script `scripts/sys-print.sh` retains its filename. It is a tool
(like `snap.sh`), not a container. Its examples and usage messages now
reference `shared-print` as the default instance name.

### Decision: `shared` domain in canonical infra.yml

The `shared` domain is NOT added to the canonical `infra.yml.example`.
Rationale: the canonical infra.yml is intentionally minimal (anklume +
work domains). The `shared` domain is documented in SPEC.md and
demonstrated in `examples/shared-services/`. Users add it when needed.

### `sys-` references NOT changed and why

| File | Reference | Reason |
|------|-----------|--------|
| `scripts/generate.py:941` | `"sys-firewall"` | Backward compatibility check |
| `tests/test_generate.py:541` | `sys-firewall` | Tests backward compatibility |
| `tests/test_generate_internals.py:1903` | `sys-firewall` | Tests backward compatibility |
| `docs/SPEC.md:402` | `sys-firewall` | Documents backward compatibility |
| `docs/parallel-prompts.md` | Multiple refs | Historical documentation |
| `docs/vision-ai-integration.md` | `sys-firewall`, `sys-print` | Documents the migration |
| `scripts/sys-print.sh` (filename) | `sys-print.sh` | Tool name, not container name |
| `tests/test_sys_print.py` (filename) | `test_sys_print.py` | Tests the tool |

### Questions for review

1. Should `scripts/sys-print.sh` be renamed to `scripts/shared-print.sh`?
2. Should the `shared` domain be added to `infra.yml.example` as commented-out?
3. Should `docs/sys-print.md` / `docs/sys-print_FR.md` be renamed?

---

## Phase 20g: Persistent Data & Flush Protection

### ADR numbering
- ADR-040 was already taken (credits/attribution). Used ADR-041 for
  persistent_data and ADR-042 for flush protection.

### persistent_data device prefix: `pd-`
- Chose `pd-` prefix to avoid collisions with `sv-` (shared volumes)
  and user-declared devices. Consistent with the `sv-` pattern from
  ADR-039.

### persistent_data source path convention
- Source: `<persistent_data_base>/<machine_name>/<volume_name>`
- Machine name in the path ensures isolation between instances.
- Default base: `/srv/anklume/data` (parallel to `/srv/anklume/shares`).

### shift: true by default on persistent_data
- Mirrored the shared_volumes default. Unprivileged containers need
  idmap shifting to access host-owned directories.

### Flush protection uses FORCE env var (not --force flag)
- The `--force` flag was already used for production safety (absolute_level
  check). The `FORCE` env var is a separate concept: bypass delete
  protection. The Makefile passes `FORCE=true` via env when the user
  specifies it.

### Step 5 project skip when instances remain
- Instead of attempting project delete and catching the error, the new
  flush.sh preemptively checks if instances remain after step 1.

### Test file exceeds 200 lines
- test_persistent_data.py is ~415 lines. Existing test files set
  precedent (test_spec_features.py: 1245L, test_flush.py: 493L).
  The 200-line rule applies to implementation files, not tests.

### Path collision detection between pd and sv
- persistent_data paths are checked against shared_volumes mount paths
  on the same machine, preventing two devices mounting to the same path.

### Questions for review

1. Should `persistent_data` support a `shift` option like shared_volumes?
   Currently hardcoded to `shift=true`.
2. Should `instance-remove.sh` also clean up host data directory at
   `/srv/anklume/data/<machine>/` when removing an instance?
3. The flush script's `FORCE` env var doubles as "bypass production
   safety" and "bypass delete protection". Should these be separate?

---
