# Matrix: EL-001
Feature: Delete protected instance
  The flush command requires confirmation to prevent accidental destruction.
  On production hosts (absolute_level=0), it requires --force explicitly.

  Background:
    Given a clean sandbox environment
    And Incus daemon is available

  Scenario: Flush without --force asks for confirmation and aborts
    When I run "scripts/flush.sh" and it may fail
    Then output contains "anklume Flush"

  Scenario: Flush with --force destroys infrastructure
    When I run "scripts/flush.sh --force"
    Then exit code is 0
    And output contains "Flush complete"
