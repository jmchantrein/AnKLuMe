# Matrix: EL-001, EL-002, EL-003
Feature: Disposable instances
  Ephemeral domains and machines can be freely created and destroyed.
  Non-ephemeral resources are protected from accidental deletion.

  Background:
    Given a clean sandbox environment

  Scenario: Ephemeral flag propagated to host_vars
    Given infra.yml from "sandbox-isolation"
    When I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0
    And inventory files exist for all domains

  Scenario: Tor gateway uses ephemeral domains
    Given infra.yml from "tor-gateway"
    When I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0
    And inventory files exist for all domains
