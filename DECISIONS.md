# DECISIONS.md — Parallel branch merge decisions

This file consolidates DECISIONS.md from all merged branches.
It will be removed after review.

---

## Branch 1: boot_autostart & snapshots_config (20 tests)

| Matrix ID | Test | Verifies |
|-----------|------|----------|
| BA-004 | test_boot_autostart_string_true | `"true"` (string) rejected |
| BA-004 | test_boot_autostart_int_zero | `0` (int) rejected |
| BA-005 | test_boot_priority_negative_value | `-10` rejected (0-100) |
| BA-005 | test_boot_priority_over_max | `200` rejected |
| BA-005 | test_boot_priority_float_value | `3.14` rejected |
| BA-005 | test_boot_priority_string_value | `"low"` rejected |
| BA-006 | test_omitted_boot_fields | No errors, no instance_boot_* |
| BA-2-001 | test_boot_autostart_and_priority_on_same_machine | Both keys in host_vars |
| BA-2-002 | test_boot_priority_on_vm_and_lxc | Type-agnostic |
| BA-3-001 | test_boot_ephemeral_resource_policy | 3-way: boot+ephemeral+resource |
| SN-004 | test_invalid_cron_three_fields | 3-field cron rejected |
| SN-004 | test_invalid_cron_boolean | `True` rejected |
| SN-004 | test_invalid_cron_empty_string | `""` rejected |
| SN-005 | test_invalid_expiry_weeks_unit | `"7w"` rejected |
| SN-005 | test_invalid_expiry_float | `30.5` rejected |
| SN-005 | test_invalid_expiry_bare_unit | `"d"` rejected |
| SN-006 | test_omitted_snapshot_fields | No errors, no instance_snapshots_* |
| SN-2-001 | test_schedule_and_expiry_both_written | Both in host_vars, sibling clean |
| SN-3-001 | test_snapshots_ephemeral_boot_combined | 3-way combination |

Open: `bool` subclass of `int` bug, existing BA-001/BA-004 tag mismatch.

---

## Branch 2: nesting_prefix & resource_policy (11 tests)

| Matrix ID | Test | Verifies |
|-----------|------|----------|
| NX-004 | test_invalid_nesting_prefix_list | `[true]` rejected |
| NX-004 | test_invalid_nesting_prefix_string_false | `"false"` rejected |
| NX-005 | test_inventory_and_host_vars_paths_unprefixed | Paths never prefixed |
| NX-2-001 | test_prefix_disabled_with_context_file | `false` + level=1 → no prefix |
| NX-2-002 | test_prefix_with_shared_volumes | Prefix on names, not on paths |
| NX-3-001 | test_prefix_addressing_firewall_vm | 3-way: prefix+addressing+firewall |
| RP-2-001 | test_explicit_cpu_excluded_auto_memory_allocated | Partial exclusion |
| RP-2-002 | test_weighted_machines_across_domains | Cross-domain weights |
| RP-3-001 | test_resource_policy_gpu_ephemeral_addressing | 4-way combination |

Coverage: 89% → 93%. Open: NX-3-001 references `sys-firewall` (now renamed).

---

## Branch 3: make help categories (Phase 32)

32 user-facing targets across 8 categories. All other targets in `help-all`.
Fix: warn() added to llm-bench.sh.

---

## Branch 4: sys-firewall → anklume-firewall (Phase 36)

Pure rename across 26 files. Backward compatibility: user-declared `sys-firewall`
still prevents auto-creation. New deployments get `anklume-firewall`. Existing
auto-created `sys-firewall` must be manually removed after update.
