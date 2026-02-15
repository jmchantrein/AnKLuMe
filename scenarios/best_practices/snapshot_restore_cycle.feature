# Matrix: DL-001, EL-001
Feature: Snapshot and restore cycle
  Best practice: always snapshot before making changes so you can rollback.

  Background:
    Given a clean sandbox environment
    And a running infrastructure

  Scenario: Create and list snapshots
    When I run "scripts/snap.sh list"
    Then exit code is 0

  Scenario: Snapshot before risky operation
    When I run "scripts/snap.sh create self before-change"
    Then exit code is 0
    When I run "scripts/snap.sh list self"
    Then exit code is 0
    And output contains "before-change"
