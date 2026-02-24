# Matrix: DL-001, DL-002
Feature: Trust-level-aware addressing convention
  anklume uses ADR-038 zone-based IP addressing where the second
  octet encodes the trust level of each domain.

  Background:
    Given a clean sandbox environment

  Scenario: Pro workstation uses zone-aware IPs
    Given infra.yml from "pro-workstation"
    When I run "make sync"
    Then exit code is 0
    And inventory files exist for all domains
    And file "group_vars/pro.yml" exists
    And file "group_vars/perso.yml" exists

  Scenario: Sync is idempotent with addressing
    Given infra.yml from "pro-workstation"
    When I run "make sync"
    Then exit code is 0
    When I run "make sync"
    Then exit code is 0
