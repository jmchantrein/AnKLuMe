# Matrix: PG-001
Feature: Wrong operation order
  anklume has a required workflow: edit -> sync -> lint -> apply.
  Skipping or reordering steps leads to errors.

  Background:
    Given a clean sandbox environment

  Scenario: Lint before sync detects no generated files
    Given infra.yml from "student-sysadmin"
    And no generated files exist
    When I run "make lint-yaml" and it may fail
    Then exit code is non-zero

  Scenario: Sync then lint passes
    Given infra.yml from "student-sysadmin"
    When I run "make sync"
    Then exit code is 0
    When I run "make lint-yaml"
    Then exit code is 0
