# Matrix: IM-001, IM-002
Feature: Golden image workflow
  anklume extracts all unique OS images from infra.yml and
  pre-downloads them for fast deployment.

  Background:
    Given a clean sandbox environment

  Scenario: Image list generated in all.yml
    Given infra.yml from "pro-workstation"
    When I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0
    And file "group_vars/all.yml" exists

  Scenario: Sync with multiple image types
    Given infra.yml from "student-sysadmin"
    When I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0
    And file "group_vars/all.yml" exists
    And inventory files exist for all domains

  Scenario: Dry-run shows image extraction
    Given infra.yml from "pro-workstation"
    When I run "python3 scripts/generate.py infra.yml --dry-run"
    Then exit code is 0
