# Matrix: DL-001, DL-002
Feature: Trust-level-aware addressing convention
  anklume uses ADR-038 zone-based IP addressing where the second
  octet encodes the trust level of each domain.

  Background:
    Given a clean sandbox environment

  Scenario: Pro workstation uses zone-aware IPs
    Given infra.yml from "pro-workstation"
    When I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0
    And inventory files exist for all domains
    And file "group_vars/pro.yml" exists
    And file "group_vars/perso.yml" exists

  Scenario: Sync is idempotent with addressing
    Given infra.yml from "pro-workstation"
    When I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0
    When I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0

  Scenario: Student sysadmin uses addressing convention
    Given infra.yml from "student-sysadmin"
    When I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0
    And inventory files exist for all domains
    And generated host_vars contain valid IPs

  Scenario: AI-tools example uses addressing convention
    Given infra.yml from "ai-tools"
    When I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0
    And inventory files exist for all domains
    And generated host_vars contain valid IPs
