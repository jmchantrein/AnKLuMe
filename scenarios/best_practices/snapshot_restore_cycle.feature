# Matrix: DL-001, EL-001
Feature: Snapshot and restore cycle
  Best practice: always snapshot before making changes so you can rollback.

  Background:
    Given a clean sandbox environment
    And a running infrastructure
    And storage backend supports snapshots

  Scenario: Create and list snapshots
    When I run "scripts/snap.sh list"
    Then exit code is 0

  Scenario: Snapshot an instance before risky operation
    When I snapshot the first running instance as "before-change"
    Then exit code is 0
    When I list snapshots of the first running instance
    Then exit code is 0
    And output contains "before-change"
    When I delete snapshot "before-change" from the first running instance
    Then exit code is 0
