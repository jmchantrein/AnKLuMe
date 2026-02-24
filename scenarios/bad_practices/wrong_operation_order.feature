# Matrix: PG-001
Feature: Wrong operation order
  anklume has a required workflow: edit -> sync -> lint -> apply.
  Skipping or reordering steps leads to errors.

  Background:
    Given a clean sandbox environment

  Scenario: Lint before sync
    Given infra.yml from "student-sysadmin"
    When I run "make lint-yaml" and it may fail
    # Should work on existing files but won't catch generated content
    # if sync hasn't been run yet.

  Scenario: Sync then lint passes
    Given infra.yml from "student-sysadmin"
    When I run "make sync"
    Then exit code is 0
    When I run "make lint-yaml"
    Then exit code is 0
