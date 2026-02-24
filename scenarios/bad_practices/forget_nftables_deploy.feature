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
    And I run "make sync"
    Then exit code is 0
    And inventory files exist for all domains
    # Without make nftables && make nftables-deploy,
    # the new bridge has no isolation rules.
    # The correct workflow is: make sync, make apply, make nftables,
    # make nftables-deploy. Forgetting the nftables steps leaves the
    # new domain's bridge unprotected.

  Scenario: Correct workflow includes nftables regeneration
    Given infra.yml from "student-sysadmin"
    When I run "make sync"
    Then exit code is 0
    When I run "make nftables" and it may fail
    # make nftables generates isolation rules inside the container.
    # make nftables-deploy applies them on the host.
    # Both steps are required after adding a domain.
