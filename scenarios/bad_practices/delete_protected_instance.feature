# Matrix: EL-001
Feature: Delete protected instance
  The flush command must refuse to destroy non-ephemeral (protected)
  infrastructure without the FORCE flag on production systems.

  Background:
    Given a clean sandbox environment

  Scenario: Flush without FORCE on production
    Given infra.yml from "student-sysadmin"
    When I run "scripts/flush.sh" and it may fail
    Then exit code is non-zero
    And output contains "FORCE"

  Scenario: Flush with FORCE succeeds
    Given infra.yml from "student-sysadmin"
    When I run "scripts/flush.sh --force"
    Then exit code is 0
