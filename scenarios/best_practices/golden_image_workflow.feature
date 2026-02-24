# Matrix: IM-001, IM-002
Feature: Golden image workflow
  anklume extracts all unique OS images from infra.yml and
  pre-downloads them for fast deployment.

  Background:
    Given a clean sandbox environment

  Scenario: Image list generated in all.yml
    Given infra.yml from "pro-workstation"
    When I run "make sync"
    Then exit code is 0
    And file "group_vars/all.yml" exists
