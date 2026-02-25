# Phase 20g: Data Persistence and Flush Protection

Implementation plan for per-machine persistent host bind mounts
(Docker-style) with flush protection for non-ephemeral resources.

## Context

`make flush` destroys everything indiscriminately, including instances
with `ephemeral: false` (protected). `storage_volumes` (Incus pool
volumes) are destroyed with the project. There is no mechanism for
persistent data like Docker bind mounts. No command exists to remove
individual instances.

## Three changes

### A) Flush respects `ephemeral: false` (ADR-041)

`scripts/flush.sh` (155 lines) — modify step 1 (lines 63-75):
- Before each `incus delete`, query `incus config get <instance>
  security.protection.delete --project <project>`
- If `true` and not `FORCE` → skip with `PROTECTED (skipped)` message
- Step 5 (projects): skip projects that still have instances
- Never delete `/srv/anklume/data/` or `/srv/anklume/shares/`
- Counter `skipped` + final summary message

### B) `make instance-remove` — targeted removal

New script `scripts/instance-remove.sh` (~80 lines):

```
make instance-remove DOMAIN=pro SCOPE=ephemeral  # ephemeral in domain
make instance-remove DOMAIN=pro SCOPE=all         # entire domain
make instance-remove I=pro-dev                     # single instance
make instance-remove I=pro-dev FORCE=true          # bypass protection
```

Logic: find Incus project via `incus list --all-projects`, check
`security.protection.delete`, interactive confirmation if protected.

### C) `persistent_data` per-machine (ADR-040)

infra.yml syntax:

```yaml
global:
  persistent_data_base: /srv/anklume/data   # Default

machines:
  pro-dev:
    persistent_data:
      db:
        path: /var/lib/postgresql           # Required, absolute
      config:
        path: /etc/myapp
        readonly: true                      # Optional, default: false
```

Mechanism (identical to shared_volumes):
- Enrichment: `_enrich_persistent_data()` builds
  `infra["_persistent_data_devices"]`
- Default source: `<base>/<domain>/<machine>/<volume>`
  (e.g., `/srv/anklume/data/pro/pro-dev/db`)
- Injected device: `pd-<name>` in `instance_devices`
  (prefix `pd-` like `sv-` for shared)
- Generation: merge pd-* + sv-* + user devices in host_vars
- Host dirs: `scripts/create-data-dirs.py` + `make data-dirs`
- The `incus_instances` role already handles arbitrary disk devices
  → no change needed

## Files to modify

| File | Action |
|------|--------|
| `docs/SPEC.md` | `persistent_data` schema, dedicated section, validation constraints, flush update |
| `docs/ARCHITECTURE.md` | ADR-040 (persistent data), ADR-041 (flush protection) |
| `docs/SPEC-operations.md` | Update Flush section |
| `scripts/generate.py` | validate() +30L, `_enrich_persistent_data()` +25L, generate() merge +10L |
| `scripts/flush.sh` | Query protection before delete, skip projects with remaining instances |
| `scripts/instance-remove.sh` | New (~80L) |
| `scripts/create-data-dirs.py` | New (~45L) |
| `Makefile` | Targets `data-dirs`, `instance-remove` |
| `tests/test_persistent_data.py` | New — validation + generation (~200L) |
| `tests/test_flush.py` | Add flush protection tests |
| `tests/behavior_matrix.yml` | PD-* and FP-* cells |

## What does NOT change

- `roles/incus_instances/tasks/main.yml` — already handles disk devices
- `shared_volumes` — independent feature, not modified
- `storage_volumes` — remains as Incus pool volumes (non-persistent)
- `site.yml` — no new plays

## persistent_data validation (in generate.py validate())

- Names DNS-safe: `^[a-z0-9]([a-z0-9-]*[a-z0-9])?$`
- `path`: required, absolute path
- `readonly`: boolean if present
- `persistent_data_base`: absolute path if present
- Device collision: `pd-<name>` not in existing devices
- Mount path collision: cross-check with shared_volumes and other
  persistent_data

## Behavior matrix (new IDs)

**persistent_data**: PD-001 to PD-007 (depth 1), PD-2-001/002
(depth 2), PD-3-001 (depth 3)

**flush_protection**: FP-001 to FP-003 (depth 1), FP-2-001 (depth 2)

## Implementation order

1. SPEC.md + ARCHITECTURE.md (spec first)
2. behavior_matrix.yml
3. tests/test_persistent_data.py + test_flush.py updates
4. generate.py: validate(), _enrich_persistent_data(), generate() merge
5. flush.sh: ephemeral protection
6. instance-remove.sh + create-data-dirs.py
7. Makefile: targets
8. `make lint && make test` → commit

## Verification

1. `python3 -m pytest tests/test_persistent_data.py -v` → all pass
2. `python3 -m pytest tests/ --ignore=tests/molecule -q` → 0 regressions
3. `python3 scripts/matrix-coverage.py` → 100% (PD + FP covered)
4. `ruff check scripts/generate.py`
5. `shellcheck scripts/instance-remove.sh scripts/flush.sh`
