# Matrix: DL-003, EL-003
Feature: Teacher lab deployment
  Teachers can deploy networking labs for N students using
  the teacher-lab example as a starting point.

  Background:
    Given a clean sandbox environment

  Scenario: Teacher lab generates inventory for all domains
    Given infra.yml from "teacher-lab"
    When I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0
    And inventory files exist for all domains

  Scenario: Teacher lab generates valid host_vars
    Given infra.yml from "teacher-lab"
    When I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0
    And generated host_vars contain valid IPs
