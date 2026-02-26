# End-to-End Scenario Testing (BDD)

anklume includes human-readable acceptance scenarios that test complete
user workflows against real Incus infrastructure. Scenarios are written
in Gherkin format using `pytest-bdd`.

## Quick start

```bash
anklume dev scenario          # Run all scenarios
anklume dev scenario --best     # Best practices only
anklume dev scenario --bad      # Bad practices only
anklume dev scenario --list          # List available scenarios
```

Or run directly with pytest:

```bash
python3 -m pytest scenarios/ -v --tb=long
python3 -m pytest scenarios/best_practices/ -v
python3 -m pytest scenarios/bad_practices/ -v -k "duplicate"
```

## Architecture

```
scenarios/
├── best_practices/              # Recommended workflows
│   ├── pro_workstation_setup.feature
│   ├── student_lab_deploy.feature
│   ├── snapshot_restore_cycle.feature
│   ├── sync_idempotency.feature
│   └── validation_before_apply.feature
├── bad_practices/               # Common mistakes
│   ├── apply_without_sync.feature
│   ├── duplicate_ips.feature
│   ├── delete_protected_instance.feature
│   ├── edit_managed_sections.feature
│   ├── forget_nftables_deploy.feature
│   └── wrong_operation_order.feature
├── conftest.py                  # Step definitions + fixtures
└── pitfalls.yml                 # Pitfall database for guide.sh
```

## Two categories

### Best practices

Validate recommended workflows. These scenarios serve as living
documentation of how to use anklume correctly:

- **Pro workstation setup**: Full deployment with network isolation
- **Student lab deploy**: Teacher deploys a lab environment
- **Snapshot restore cycle**: Snapshot before changes, restore on failure
- **Sync idempotency**: Running sync twice produces the same result
- **Validation before apply**: Always lint after sync

### Bad practices

Verify that anklume catches mistakes early with clear error messages:

- **Apply without sync**: No inventory files, stale inventory
- **Duplicate IPs**: Generator rejects duplicate IP addresses
- **Delete protected instance**: Flush without FORCE on production
- **Edit managed sections**: Content overwritten by sync
- **Forget nftables-deploy**: New domain not isolated
- **Wrong operation order**: Skipping steps in the workflow

## Writing scenarios

Scenarios use Gherkin syntax with `Given/When/Then` steps:

```gherkin
# Matrix: XX-NNN
Feature: Descriptive name
  Explanation of what this scenario tests.

  Background:
    Given a clean sandbox environment

  Scenario: Specific test case
    Given infra.yml from "student-sysadmin"
    When I run "anklume sync"
    Then exit code is 0
    And inventory files exist for all domains
```

### Available steps

**Given** (preconditions):
- `a clean sandbox environment` — verify anklume project directory
- `images are pre-cached via shared repository` — skip if no Incus
- `infra.yml from "<example>"` — copy example infra.yml
- `infra.yml exists but no inventory files` — simulate missing sync
- `a running infrastructure` — skip if no running instances
- `infra.yml with two machines sharing "<ip>"` — duplicate IP test
- `infra.yml with managed section content in "<file>"` — verify file

**When** (actions):
- `I run "<command>"` — execute a shell command
- `I run "<command>" and it may fail` — command expected to fail
- `I add a domain "<name>" to infra.yml` — modify infra.yml
- `I edit the managed section in "<file>"` — inject content

**Then** (assertions):
- `exit code is 0` / `exit code is non-zero`
- `output contains "<text>"` / `stderr contains "<text>"`
- `inventory files exist for all domains`
- `file "<path>" exists` / `file "<path>" does not exist`
- `all declared instances are running`
- `intra-domain connectivity works`
- `inter-domain connectivity is blocked`
- `no Incus resources were created`
- `the managed section in "<file>" is unchanged`

### Matrix annotations

Link scenarios to behavior matrix IDs for coverage tracking:

```gherkin
# Matrix: DL-001, NI-002
Feature: ...
```

The `scripts/matrix-coverage.py` tool scans these annotations.

## Guide integration

Bad-practice scenarios feed back into the interactive guide
(`scripts/guide.sh`). The `scenarios/pitfalls.yml` file maps each
pitfall to a guide step and warning message.

The guide displays proactive warnings at relevant steps:
- Step 3 (infra.yml editing): managed sections, duplicate IPs
- Step 4 (generate): correct workflow order
- Step 6 (apply): inventory check, nftables reminder

## Dependencies

```bash
pip install pytest-bdd
```

pytest-bdd is listed in `pyproject.toml` under `[project.optional-dependencies]`.

## Execution notes

- Scenarios are **on-demand only** — not part of CI
- Some scenarios require a running Incus daemon (skipped otherwise)
- Best-practice deployment scenarios may take several minutes
- Image pre-caching via Phase 18e reduces startup latency
