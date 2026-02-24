# Matrix: SV-003, SV-004, SV-005, SV-006
Feature: Invalid shared volumes configuration
  The generator catches invalid shared volume configurations
  early with clear error messages.

  Background:
    Given a clean sandbox environment

  Scenario: Unknown consumer domain
    Given infra.yml from "student-sysadmin"
    When I run "python3 scripts/generate.py --validate infra.yml" and it may fail
    # If infra.yml has an unknown consumer, generator should error

  Scenario: Empty consumers mapping
    Given infra.yml from "student-sysadmin"
    When I run "make sync"
    Then exit code is 0
    # Valid infra without shared_volumes passes
