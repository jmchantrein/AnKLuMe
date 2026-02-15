# Matrix: PG-001
Feature: Apply without sync
  AnKLuMe must detect when the user skips the generate step and
  provides clear guidance to run "make sync" first.

  Background:
    Given a clean sandbox environment

  Scenario: No inventory files exist
    Given infra.yml exists but no inventory files
    When I run "make apply" and it may fail
    Then exit code is non-zero

  Scenario: Stale inventory after infra.yml change
    Given infra.yml from "student-sysadmin"
    When I run "make sync"
    Then exit code is 0
    When I add a domain "new-domain" to infra.yml
    When I run "make apply" and it may fail
    Then exit code is non-zero
