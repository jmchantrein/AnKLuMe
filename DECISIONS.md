# DECISIONS.md — Parallel branch merge decisions

This file consolidates DECISIONS.md from all merged branches.
It will be removed after review.

---

## Branch 1: boot_autostart & snapshots_config (20 tests)

### Tests added

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

### Open questions
1. `bool` subclass of `int` bug: `boot_priority=True` passes validation (maps to 1)
2. Existing tests tagged BA-001 actually test BA-004 behavior — retag?

---

## Branch 2: nesting_prefix & resource_policy (11 tests)

### Tests added

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

### Coverage impact: 89% → 93%

### Open questions
1. Existing NX-001/RP-007 tag mismatches — retag?
2. RP-3-001 tests 4 features but matrix cell says depth 3
3. NX-3-001 references `sys-firewall` (renamed in branch 4)
