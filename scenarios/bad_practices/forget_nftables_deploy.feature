# Matrix: NI-001, NI-002
Feature: Forget nftables-deploy after adding domain
  After adding a new domain and running make apply, the user must
  regenerate and deploy nftables rules. Without this step, the new
  domain's network is not isolated.

  Background:
    Given a clean sandbox environment
    And a running infrastructure

  Scenario: New domain added without nftables update
    When I add a domain "new-unsecured" to infra.yml
    When I run "make sync"
    Then exit code is 0
    # Without make nftables && make nftables-deploy,
    # the new bridge has no isolation rules.
    # This scenario documents the required workflow.
