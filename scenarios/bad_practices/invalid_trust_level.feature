# Matrix: DL-004
Feature: Invalid trust level rejected
  The generator validates trust_level values and rejects
  unknown trust levels with clear error messages.

  Background:
    Given a clean sandbox environment

  Scenario: Unknown trust level rejected
    Given infra.yml with invalid trust_level "top-secret"
    When I run "python3 scripts/generate.py infra.yml" and it may fail
    Then exit code is non-zero
    And output contains "trust_level"

  Scenario: Valid trust levels accepted
    Given infra.yml from "pro-workstation"
    When I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0
