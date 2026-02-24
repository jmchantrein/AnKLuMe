# DECISIONS.md -- Phase 36: Naming Convention Migration

## Name mapping

| Old name | New name | Context |
|----------|----------|---------|
| `sys-firewall` (auto-created) | `anklume-firewall` | Already done (prior commit) |
| `sys-print` (container) | `shared-print` | Container in `shared` domain |
| `print-service` (domain) | `shared` | Domain for user-facing services |
| `examples/sys-print/` | `examples/shared-services/` | Example directory |

## Script naming

The script `scripts/sys-print.sh` retains its filename. It is a tool
(like `snap.sh`), not a container. Its examples and usage messages now
reference `shared-print` as the default instance name.

## Decision: `shared` domain in canonical infra.yml

The `shared` domain is NOT added to the canonical `infra.yml.example`.
Rationale: the canonical infra.yml is intentionally minimal (anklume +
work domains). The `shared` domain is documented in SPEC.md and
demonstrated in `examples/shared-services/`. Users add it when needed.

## `sys-` references NOT changed and why

| File | Reference | Reason |
|------|-----------|--------|
| `scripts/generate.py:941` | `"sys-firewall"` | Backward compatibility check -- must still detect legacy user declarations |
| `tests/test_generate.py:541` | `sys-firewall` | Tests the backward compatibility path |
| `tests/test_generate_internals.py:1903` | `sys-firewall` | Tests the backward compatibility path |
| `docs/SPEC.md:402` | `sys-firewall` | Documents backward compatibility |
| `docs/parallel-prompts.md` | Multiple `sys-firewall` refs | Historical prompt documentation |
| `docs/parallel-prompts_FR.md` | Multiple `sys-firewall` refs | Historical prompt documentation (FR) |
| `docs/vision-ai-integration.md` | `sys-firewall`, `sys-print` | Documents the migration itself |
| `docs/vision-ai-integration_FR.md` | Same | French translation of migration docs |
| `scripts/sys-print.sh` (filename) | `sys-print.sh` | Tool name, not container name |
| `tests/test_sys_print.py` (filename) | `test_sys_print.py` | Tests the tool `sys-print.sh` |

## Questions for human review

1. Should `scripts/sys-print.sh` be renamed to `scripts/shared-print.sh`
   or a more generic name like `scripts/print-service.sh`? Current decision:
   keep as-is since it is a standalone tool name.

2. Should the `shared` domain be added to the canonical `infra.yml.example`
   as a commented-out section? Current decision: no, keep it minimal.

3. The `docs/sys-print.md` and `docs/sys-print_FR.md` filenames still use
   the `sys-print` prefix. Should they be renamed? This would break
   existing links. Current decision: keep filenames, update content.
