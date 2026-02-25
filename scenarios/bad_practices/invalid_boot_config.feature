# Matrix: BA-004, BA-005, SN-004, SN-005
Feature: Invalid boot and snapshot configuration
  The generator validates boot_autostart, boot_priority,
  snapshots_schedule, and snapshots_expiry fields.

  Background:
    Given a clean sandbox environment

  Scenario: Generator rejects invalid cron schedule
    Given infra.yml with invalid snapshots_schedule "not-a-cron"
    When I run "python3 scripts/generate.py infra.yml" and it may fail
    Then exit code is non-zero
    And output contains "snapshots_schedule"

  Scenario: Generator rejects invalid expiry format
    Given infra.yml with invalid snapshots_expiry "forever"
    When I run "python3 scripts/generate.py infra.yml" and it may fail
    Then exit code is non-zero
    And output contains "snapshots_expiry"

  Scenario: Generator rejects boot_priority out of range
    Given infra.yml with boot_priority 999
    When I run "python3 scripts/generate.py infra.yml" and it may fail
    Then exit code is non-zero
    And output contains "boot_priority"
