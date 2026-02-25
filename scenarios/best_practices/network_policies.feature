# Matrix: NP-001, NP-002
Feature: Network policies for cross-domain access
  Network policies declare selective exceptions to the default
  drop-all inter-domain firewall, enabling specific services
  to be accessed across domain boundaries.

  Background:
    Given a clean sandbox environment

  Scenario: AI-tools example has network policies
    Given infra.yml from "ai-tools"
    When I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0
    And inventory files exist for all domains

  Scenario: Tor gateway example generates without error
    Given infra.yml from "tor-gateway"
    When I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0
    And inventory files exist for all domains
