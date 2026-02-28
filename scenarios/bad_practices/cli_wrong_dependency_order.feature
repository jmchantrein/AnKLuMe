Feature: CLI wrong dependency order
  Running commands out of their dependency order leads to errors.
  The resource flow model enforces: producer must run before consumer.

  Background:
    Given a clean sandbox environment

  Scenario: apply without sync fails
    Given infra.yml exists but no inventory files
    When I run "make apply" and it may fail
    Then exit code is non-zero

  Scenario: lint without sync fails
    Given "yamllint" is available
    And infra.yml from "student-sysadmin"
    And no generated files exist
    When I run "yamllint -c .yamllint.yml inventory/" and it may fail
    Then exit code is non-zero

  Scenario: Sync with invalid infra.yml fails gracefully
    Given infra.yml with invalid trust_level "super-trusted"
    When I run "python3 scripts/generate.py infra.yml" and it may fail
    Then exit code is non-zero
    And output contains "trust_level"
