# DECISIONS.md — Phase 36: Rename sys-firewall to anklume-firewall

## Summary

Pure rename of the auto-generated firewall VM from `sys-firewall` to
`anklume-firewall`. No behavioral changes. The `sys-` prefix was a
QubesOS legacy; the AnKLuMe convention is `anklume-` for infrastructure
machines in the anklume domain (matching `anklume-instance`).

## Files modified

### Generator (behavior change)

| File | Change |
|------|--------|
| `scripts/generate.py` | `_enrich_firewall()`: auto-created machine name changed from `sys-firewall` to `anklume-firewall`. Backward compatibility: check for both `anklume-firewall` and `sys-firewall` when detecting user overrides. Log message updated. |

### Specification

| File | Change |
|------|--------|
| `docs/SPEC.md` | Section "Auto-creation of sys-firewall" renamed to "Auto-creation of anklume-firewall". All references updated. Added backward compatibility note for legacy `sys-firewall`. |

### Documentation

| File | Change |
|------|--------|
| `docs/firewall-vm.md` | Title, architecture diagram, all examples and commands updated to `anklume-firewall`. |
| `docs/firewall-vm_FR.md` | French translation: same changes as English version. |
| `docs/addressing-convention.md` | Replaced `sys-` prefix convention with `anklume-` prefix convention. |
| `docs/decisions-log.md` | D-039: `sys-firewall` → `anklume-firewall` in description. |
| `docs/decisions-log_FR.md` | D-018, D-020, D-039: `sys-firewall` → `anklume-firewall`. |
| `docs/vision-ai-integration.md` | Updated naming table and migration notes to reflect rename is done. |
| `docs/ROADMAP.md` | Phase 11 title updated. Phase 36 checklist item marked done. |
| `docs/ROADMAP_FR.md` | Phase 11 title updated. |
| `README.md` | Feature table: `sys-firewall style` → `anklume-firewall`. |
| `README_FR.md` | Feature table: same change in French. |

### Tests

| File | Change |
|------|--------|
| `tests/test_generate.py` | All auto-creation assertions changed to `anklume-firewall`. Added new test `test_firewall_mode_vm_legacy_sys_firewall_blocks_auto_creation` for backward compatibility. |
| `tests/test_generate_internals.py` | All auto-creation assertions changed to `anklume-firewall`. Added test `test_legacy_sys_firewall_in_non_anklume_domain_blocks_auto_creation`. |
| `tests/test_generate_edge_cases.py` | Assertions updated to `anklume-firewall`. |
| `tests/test_addressing.py` | Firewall IP assertion updated to `anklume-firewall`. |
| `tests/test_integration.py` | Host file expectations and assertions updated. |
| `tests/test_psot_edge_cases.py` | Enrich tests updated to `anklume-firewall`. |
| `tests/behavior_matrix.yml` | All FM-* entries and cross-references updated. |

### Ansible roles (comments only)

| File | Change |
|------|--------|
| `roles/incus_firewall_vm/tasks/main.yml` | Comment: `sys-firewall` → `anklume-firewall`. |
| `roles/incus_firewall_vm/defaults/main.yml` | Comment: `sys-firewall` → `anklume-firewall`. |
| `roles/firewall_router/tasks/main.yml` | Comment: `sys-firewall` → `anklume-firewall`. |
| `roles/firewall_router/defaults/main.yml` | Comment: `sys-firewall` → `anklume-firewall`. |
| `roles/firewall_router/templates/firewall-router.nft.j2` | Comment: `sys-firewall` → `anklume-firewall`. |

## Backward compatibility decision

**Decision**: Accept `sys-firewall` as a legacy alias that prevents
auto-creation of `anklume-firewall`.

**Rationale**: Users who already have `sys-firewall` declared in their
`infra.yml` should not suddenly get a second firewall VM (`anklume-firewall`)
auto-created alongside their existing one. The generator checks for both
names when deciding whether to skip auto-creation.

**Behavior**:
- If user declares `anklume-firewall` → used as-is, no auto-creation
- If user declares `sys-firewall` → used as-is, no auto-creation
  (backward compatibility)
- If neither is declared and `firewall_mode: vm` → `anklume-firewall`
  is auto-created

**Migration path for existing users**:
1. Users with no explicit firewall declaration: transparent — the
   auto-created machine simply changes name from `sys-firewall` to
   `anklume-firewall`. Running `make sync && make apply` will create
   `anklume-firewall` (the old `sys-firewall` Incus instance must be
   manually removed if it exists).
2. Users with explicit `sys-firewall`: no action needed — their
   declaration continues to work. They can rename to `anklume-firewall`
   at their convenience.

## Impact on existing users

- **New deployments**: `anklume-firewall` is auto-created (instead of
  `sys-firewall`). No user action needed.
- **Existing deployments with auto-created sys-firewall**: After
  updating the framework, `make sync` will generate files for
  `anklume-firewall` instead. The old `sys-firewall` Incus instance
  must be manually deleted (`incus delete sys-firewall --project anklume`).
  Alternatively, users can declare `sys-firewall` explicitly in their
  `infra.yml` to keep the old name.
- **Existing deployments with explicit sys-firewall**: No change needed.
  The generator recognizes `sys-firewall` as a user override.

## Validation

- `ruff check scripts/generate.py`: all checks passed
- `pytest tests/`: 3261 passed, 21 skipped, 24 failed (pre-existing
  failures in test_upgrade.py and test_guide.py, unrelated to this change)
- All 16 firewall-specific tests pass (`pytest -k firewall`)
