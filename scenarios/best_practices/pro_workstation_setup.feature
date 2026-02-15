# Matrix: DL-001, NI-001, NI-002
Feature: Pro workstation setup
  An admin deploys a pro/perso infrastructure with network isolation.
  This is the recommended workflow for compartmentalizing a workstation.

  Background:
    Given a clean sandbox environment
    And images are pre-cached via shared repository

  Scenario: Generate Ansible files from example
    Given infra.yml from "pro-workstation"
    When I run "make sync"
    Then exit code is 0
    And inventory files exist for all domains
    And file "group_vars/admin.yml" exists
    And file "host_vars/admin-ansible.yml" exists

  Scenario: Full deployment with isolation verified
    Given infra.yml from "pro-workstation"
    When I run "make sync"
    Then exit code is 0
    When I run "make apply"
    Then exit code is 0
    And all declared instances are running
    Then intra-domain connectivity works
    But inter-domain connectivity is blocked
