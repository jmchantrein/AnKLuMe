# Matrix: SV-003, SV-004, SV-005, SV-006
Feature: Invalid shared volumes configuration
  The generator catches invalid shared volume configurations
  early with clear error messages.

  Background:
    Given a clean sandbox environment

  Scenario: Unknown consumer domain rejected
    Given infra.yml with shared_volume consumer "nonexistent-domain"
    When I run "python3 scripts/generate.py infra.yml" and it may fail
    Then exit code is non-zero
    And output contains "consumer"

  Scenario: Relative mount path rejected
    Given infra.yml with shared_volume relative path "relative/path"
    When I run "python3 scripts/generate.py infra.yml" and it may fail
    Then exit code is non-zero
    And output contains "path"

  Scenario: Valid example passes generator
    Given infra.yml from "pro-workstation"
    When I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0
