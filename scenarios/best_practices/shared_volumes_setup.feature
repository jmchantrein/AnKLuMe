# Matrix: SV-001, SV-002
Feature: Shared volumes setup
  Shared volumes allow declarative inter-domain directory sharing
  via host bind mounts injected as Incus disk devices.

  Background:
    Given a clean sandbox environment

  Scenario: Sync generates shared volume devices
    Given infra.yml from "pro-workstation"
    When I run "make sync"
    Then exit code is 0
    And inventory files exist for all domains

  Scenario: Sync dry-run shows device changes
    Given infra.yml from "pro-workstation"
    When I run "make sync-dry"
    Then exit code is 0
