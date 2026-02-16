# Matrix: PG-001, PG-002
Feature: Sync idempotency
  Best practice: make sync is idempotent — running it twice produces
  the same result. User content outside managed sections is preserved.

  Background:
    Given a clean sandbox environment

  Scenario: Sync is idempotent
    Given infra.yml from "student-sysadmin"
    When I run "make sync"
    Then exit code is 0
    When I run "make sync"
    Then exit code is 0

  Scenario: Dry-run previews without writing
    Given no generated files exist
    And infra.yml from "student-sysadmin"
    When I run "make sync-dry"
    Then exit code is 0
    And file "inventory/anklume.yml" does not exist
