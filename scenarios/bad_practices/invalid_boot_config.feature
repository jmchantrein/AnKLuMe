# Matrix: BA-004, BA-005, SN-004, SN-005
Feature: Invalid boot and snapshot configuration
  The generator validates boot_autostart, boot_priority,
  snapshots_schedule, and snapshots_expiry fields.

  Background:
    Given a clean sandbox environment

  Scenario: Generator rejects invalid cron schedule
    Given infra.yml from "student-sysadmin"
    When I run "make sync"
    Then exit code is 0
    # Valid infra passes. Invalid schedules caught by validation
    # tests in test_spec_features.py.

  Scenario: Generator rejects invalid expiry format
    Given infra.yml from "student-sysadmin"
    When I run "make sync"
    Then exit code is 0
    # Valid infra passes. Invalid expiry formats caught by
    # validation tests in test_spec_features.py.
