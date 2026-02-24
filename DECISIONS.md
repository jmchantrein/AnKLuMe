# DECISIONS.md — Phase 20g: Persistent Data & Flush Protection

## Decisions made

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
  flush.sh preemptively checks if instances remain after step 1. This is
  cleaner than relying on Incus error messages.

### Test file exceeds 200 lines
- test_persistent_data.py is ~415 lines. The flush protection tests
  require substantial mock environment setup. Existing test files
  (test_spec_features.py: 1245 lines, test_flush.py: 493 lines) set
  precedent for larger test files. The CLAUDE.md 200-line rule applies
  to implementation files.

### Path collision detection between pd and sv
- persistent_data paths are checked against shared_volumes mount paths
  on the same machine. This prevents two different disk devices mounting
  to the same container path.

## Questions for human review

1. Should `persistent_data` support a `shift` option like shared_volumes?
   Currently hardcoded to `shift=true`. Users who need `shift=false`
   (e.g., for VMs) would need to use raw `devices:` instead.

2. Should `instance-remove.sh` also clean up the host data directory
   at `/srv/anklume/data/<machine>/` when removing an instance? Currently
   it only removes the Incus instance. The data directory persists.

3. The flush script's `FORCE` env var doubles as both "bypass production
   safety" and "bypass delete protection". Should these be separate?

## Files modified

- `docs/ARCHITECTURE.md` — Added ADR-041 (persistent_data) and ADR-042 (flush protection)
- `docs/SPEC.md` — Added persistent_data section, validation constraints, infra.yml format
- `docs/SPEC-operations.md` — Updated Flush section with protection behavior
- `scripts/generate.py` — Added persistent_data validation, enrichment, and device generation
- `scripts/flush.sh` — Added protection check, skipped counter, project skip logic
- `tests/test_flush.py` — Updated mock to handle config get, track deletions
- `tests/behavior_matrix.yml` — Added persistent_data and flush_protection capabilities
- `Makefile` — Added data-dirs and instance-remove targets

## Files created

- `scripts/create-data-dirs.py` — Creates host directories for persistent_data
- `scripts/instance-remove.sh` — Targeted instance removal with protection
- `tests/test_persistent_data.py` — Tests for PD-* and FP-* matrix cells
- `DECISIONS.md` — This file
