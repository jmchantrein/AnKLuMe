# DECISIONS.md — Test additions for boot_autostart and snapshots_config matrix coverage

## Tests added

### boot_autostart — Depth 1

| Test | Matrix ID | What it verifies |
|------|-----------|-----------------|
| `TestBootAutostartDepth1::test_boot_autostart_string_true` | BA-004 | `boot_autostart="true"` (string) triggers validation error |
| `TestBootAutostartDepth1::test_boot_autostart_int_zero` | BA-004 | `boot_autostart=0` (int) triggers validation error |
| `TestBootAutostartDepth1::test_boot_priority_negative_value` | BA-005 | `boot_priority=-10` triggers validation error (0-100 range) |
| `TestBootAutostartDepth1::test_boot_priority_over_max` | BA-005 | `boot_priority=200` triggers validation error (0-100 range) |
| `TestBootAutostartDepth1::test_boot_priority_float_value` | BA-005 | `boot_priority=3.14` (float) triggers validation error |
| `TestBootAutostartDepth1::test_boot_priority_string_value` | BA-005 | `boot_priority="low"` (string) triggers validation error |
| `TestBootAutostartDepth1::test_omitted_boot_fields` | BA-006 | Omitted fields: no validation errors AND no `instance_boot_*` in host_vars |

### boot_autostart — Depth 2

| Test | Matrix ID | What it verifies |
|------|-----------|-----------------|
| `TestBootAutostartDepth2::test_boot_autostart_and_priority_on_same_machine` | BA-2-001 | Both `boot_autostart` and `boot_priority` on one machine produce both keys in host_vars |
| `TestBootAutostartDepth2::test_boot_priority_on_vm_and_lxc` | BA-2-002 | `boot_priority` works identically on `type: vm` and `type: lxc` — same value, correct `instance_type` |

### boot_autostart — Depth 3

| Test | Matrix ID | What it verifies |
|------|-----------|-----------------|
| `TestBootAutostartDepth3::test_boot_ephemeral_resource_policy` | BA-3-001 | `boot_autostart` + `ephemeral: true` (domain) + `resource_policy: {}` all coexist: boot config in host_vars, ephemeral inherited, resource allocation applied |

### snapshots_config — Depth 1

| Test | Matrix ID | What it verifies |
|------|-----------|-----------------|
| `TestSnapshotsDepth1::test_invalid_cron_three_fields` | SN-004 | 3-field cron `"0 * *"` triggers validation error |
| `TestSnapshotsDepth1::test_invalid_cron_boolean` | SN-004 | `snapshots_schedule=True` (non-string) triggers validation error |
| `TestSnapshotsDepth1::test_invalid_cron_empty_string` | SN-004 | `snapshots_schedule=""` (empty) triggers validation error |
| `TestSnapshotsDepth1::test_invalid_expiry_weeks_unit` | SN-005 | `"7w"` (weeks not valid, only d/h/m) triggers validation error |
| `TestSnapshotsDepth1::test_invalid_expiry_float` | SN-005 | `snapshots_expiry=30.5` (float) triggers validation error |
| `TestSnapshotsDepth1::test_invalid_expiry_bare_unit` | SN-005 | `"d"` (no number before unit) triggers validation error |
| `TestSnapshotsDepth1::test_omitted_snapshot_fields` | SN-006 | Omitted fields: no validation errors AND no `instance_snapshots_*` in host_vars |

### snapshots_config — Depth 2

| Test | Matrix ID | What it verifies |
|------|-----------|-----------------|
| `TestSnapshotsDepth2::test_schedule_and_expiry_both_written` | SN-2-001 | Both `snapshots_schedule` and `snapshots_expiry` on same machine appear in host_vars; other machine has neither |

### snapshots_config — Depth 3

| Test | Matrix ID | What it verifies |
|------|-----------|-----------------|
| `TestSnapshotsDepth3::test_snapshots_ephemeral_boot_combined` | SN-3-001 | Snapshots + ephemeral domain + boot_autostart all coexist: snapshot config, ephemeral flag, and boot config all present in host_vars |

## Decisions

1. **BA-004 invalid values**: Chose `"true"` (string) and `0` (int) as test values. These are distinct from the existing BA-001 tests that use `"yes"` and `1`. The Python `bool` subclass of `int` means `isinstance(0, bool)` is `False`, so `0` is correctly rejected by the `isinstance(boot_autostart, bool)` check in `validate()`.

2. **BA-005 invalid values**: Chose `-10`, `200`, `3.14`, and `"low"` — covering negative, over-max, float, and string cases. The SPEC says "must be an integer 0-100", so all non-int types and out-of-range ints are invalid. Note: Python's `bool` is a subclass of `int`, so `True`/`False` would technically pass the `isinstance(boot_priority, int)` check. This is an edge case not tested because `True` maps to `1` (valid range) — testing it would be a corner case beyond what the matrix cell requires.

3. **BA-006 combined test**: The matrix cell says "No errors, no instance_boot_* in host_vars" — this tests both validation AND generation in a single test. Existing tests test these separately (BA-001 for validation, BA-003 for generation), but BA-006 explicitly requires both assertions together.

4. **BA-2-002 VM + LXC**: Changed `pro-dev` to `type: vm` and kept `pro-web` as `type: lxc`. Both get `boot_priority=80`. The test verifies both the priority value AND the instance_type to prove the feature is type-agnostic.

5. **BA-3-001 resource_policy mock**: Used `patch("generate._detect_host_resources")` with 8 CPU / 16 GiB mock host, same pattern as `TestResourcePolicyEnrichment`. Asserts resource allocation happened by checking `instance_config` contains either `limits.memory` or `limits.cpu.allowance`.

6. **SN-004 invalid cron values**: Chose 3-field string, boolean `True`, and empty string `""`. These cover wrong field count (different from existing 4-field and 6-field tests tagged SN-001), non-string type (different from existing int test), and empty edge case.

7. **SN-005 invalid expiry values**: Chose `"7w"` (weeks — invalid unit, SPEC says d/h/m only), `30.5` (float), and `"d"` (bare unit without number). The regex `^\d+[dhm]$` requires at least one digit before the unit letter.

8. **SN-2-001 isolation check**: Beyond verifying both fields on `pro-dev`, the test also checks `pro-web` has no snapshot config — confirming per-machine isolation of snapshot settings.

9. **SN-3-001 three-way combination**: Combines ephemeral at domain level (inherited by machine), snapshots on specific machine, and boot_autostart on same machine. Tests that all three features produce independent, correct output without interference.

## Questions for human review

1. **Existing tests tagged differently**: Tests like `test_invalid_boot_autostart_string` (line 93) are tagged `# Matrix: BA-001` but test what BA-004 describes (invalid boolean types). The instructions said not to modify existing tests, so the new BA-004 tests use different invalid values. Should the existing tests be re-tagged?

2. **`boot_priority = True` edge case**: Since Python `bool` is a subclass of `int`, `boot_priority = True` passes validation (maps to `1`, within 0-100). This is arguably a generator bug but not what the matrix cells ask to test. Worth adding a separate test or matrix cell?

3. **SN-006 / BA-006 overlap with existing tests**: The existing `test_omitted_boot_fields_valid` (BA-001) and `test_boot_omitted_not_in_host_vars` (BA-003) separately test what BA-006 combines. The new BA-006 test is not redundant — it explicitly asserts both validation AND generation in one test. Same pattern for SN-006. Acceptable duplication?
