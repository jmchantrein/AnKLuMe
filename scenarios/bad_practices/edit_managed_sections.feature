# Matrix: PG-002
Feature: Edit managed sections
  Content inside managed sections is overwritten by "make sync".
  Users must be warned that their changes will be lost.

  Background:
    Given a clean sandbox environment

  Scenario: Managed section content is overwritten by sync
    Given infra.yml from "student-sysadmin"
    When I run "make sync"
    Then exit code is 0
    When I edit the managed section in "group_vars/admin.yml"
    When I run "make sync"
    Then exit code is 0
    And the managed section in "group_vars/admin.yml" is unchanged
