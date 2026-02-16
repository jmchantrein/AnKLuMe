# Matrix: DL-001, NI-001, NI-002
Feature: Pro workstation setup
  An admin deploys a pro/perso infrastructure with network isolation.
  This is the recommended workflow for compartmentalizing a workstation.

  Scenario: Generate Ansible files from example
    Given a clean sandbox environment
    And infra.yml from "pro-workstation"
    When I run "make sync"
    Then exit code is 0
    And inventory files exist for all domains
    And file "group_vars/anklume.yml" exists
    And file "host_vars/pw-admin.yml" exists

  Scenario: Full deployment with isolation verified
    Given a clean sandbox environment
    And we are in a sandbox environment
    And images are pre-cached via shared repository
    And infra.yml from "pro-workstation"
    When I run "make sync"
    Then exit code is 0
    When I run "make apply-infra"
    Then exit code is 0
    And all declared instances are running
    Then intra-domain connectivity works
    But inter-domain connectivity is blocked
