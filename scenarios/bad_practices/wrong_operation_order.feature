# Matrix: PG-001
Feature: Wrong operation order
  anklume has a required workflow: edit -> sync -> lint -> apply.
  Skipping or reordering steps leads to errors.

  Background:
    Given a clean sandbox environment

  Scenario: Lint before sync detects no generated files
    Given infra.yml from "student-sysadmin"
    And no generated files exist
    When I run "yamllint -c .yamllint.yml inventory/" and it may fail
    Then exit code is non-zero

  Scenario: Sync then lint passes
    Given infra.yml from "student-sysadmin"
    When I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0
    When I run "yamllint -c .yamllint.yml inventory/ group_vars/ host_vars/" and it may fail
    Then exit code is 0
