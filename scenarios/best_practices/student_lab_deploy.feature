# Matrix: DL-001, DL-002
Feature: Student lab deployment
  A teacher deploys a lab environment with admin and student domains.

  Background:
    Given a clean sandbox environment
    And images are pre-cached via shared repository

  Scenario: Generate lab infrastructure
    Given infra.yml from "student-sysadmin"
    When I run "make sync"
    Then exit code is 0
    And inventory files exist for all domains

  Scenario: Deploy and verify lab instances
    Given infra.yml from "student-sysadmin"
    When I run "make sync"
    Then exit code is 0
    When I run "make apply"
    Then exit code is 0
    And all declared instances are running
