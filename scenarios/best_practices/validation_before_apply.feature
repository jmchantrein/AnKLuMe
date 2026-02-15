# Matrix: PG-001
Feature: Validation before apply
  Best practice: always run make lint after make sync to catch issues
  before deploying infrastructure.

  Background:
    Given a clean sandbox environment

  Scenario: Lint passes on generated files
    Given infra.yml from "student-sysadmin"
    When I run "make sync"
    Then exit code is 0
    When I run "make lint-yaml"
    Then exit code is 0
    When I run "make syntax"
    Then exit code is 0
