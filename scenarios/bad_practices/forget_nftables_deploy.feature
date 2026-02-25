# Matrix: NI-001, NI-002
Feature: Forget nftables-deploy after adding domain
  After adding a new domain and running make apply, the user must
  regenerate and deploy nftables rules. Without this step, the new
  domain's network is not isolated.

  Background:
    Given a clean sandbox environment

  Scenario: New domain added without nftables update
    Given infra.yml from "student-sysadmin"
    When I add a domain "new-unsecured" to infra.yml
    And I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0
    And inventory files exist for all domains
    And file "inventory/new-unsecured.yml" exists

  Scenario: Nftables generation produces rules for all domains
    Given infra.yml from "pro-workstation"
    When I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0
    When I run "python3 scripts/generate.py infra.yml --dry-run" and it may fail
    Then exit code is 0
