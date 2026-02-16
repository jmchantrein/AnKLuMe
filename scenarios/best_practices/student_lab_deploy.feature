# Matrix: DL-001, DL-002
Feature: Student lab deployment
  A teacher deploys a lab environment with admin and student domains.

  Scenario: Generate lab infrastructure
    Given a clean sandbox environment
    And infra.yml from "student-sysadmin"
    When I run "make sync"
    Then exit code is 0
    And inventory files exist for all domains

  Scenario: Deploy and verify lab instances
    Given a clean sandbox environment
    And we are in a sandbox environment
    And images are pre-cached via shared repository
    And infra.yml from "student-sysadmin"
    When I run "make sync"
    Then exit code is 0
    When I run "make apply-infra"
    Then exit code is 0
    And all declared instances are running
