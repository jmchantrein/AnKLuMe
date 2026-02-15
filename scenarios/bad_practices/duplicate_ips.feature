# Matrix: DL-001, DL-002
Feature: Duplicate IPs in infra.yml
  The PSOT generator must reject configurations with duplicate IPs
  across domains and provide a clear error message.

  Background:
    Given a clean sandbox environment

  Scenario: Two machines share the same IP
    Given infra.yml with two machines sharing "10.100.200.10"
    When I run "make sync" and it may fail
    Then exit code is non-zero
    And output contains "duplicate"
    And file "inventory/test-a.yml" does not exist
