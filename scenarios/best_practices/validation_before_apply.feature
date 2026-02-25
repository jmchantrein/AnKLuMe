# Matrix: PG-001
Feature: Validation before apply
  Best practice: always run make lint after make sync to catch issues
  before deploying infrastructure.

  Background:
    Given a clean sandbox environment

  Scenario: Lint passes on generated files
    Given infra.yml from "student-sysadmin"
    When I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0
    When I run "yamllint -c .yamllint.yml inventory/ group_vars/ host_vars/" and it may fail
    Then exit code is 0
