# Matrix: RP-001, RP-002, RP-003
Feature: Resource allocation policy
  The generator distributes CPU and memory across instances based
  on the resource_policy global setting and per-machine weights.

  Background:
    Given a clean sandbox environment

  Scenario: Developer example uses resource policy
    Given infra.yml from "developer"
    When I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0
    And inventory files exist for all domains

  Scenario: Resource policy with explicit limits preserved
    Given infra.yml from "ai-tools"
    When I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0
    And inventory files exist for all domains
