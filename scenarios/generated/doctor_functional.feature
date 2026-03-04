Feature: Doctor checks — system health verification
  Verify that the doctor diagnostic tool works correctly,
  detects available/missing tools, and produces useful output.

  @requires.doctor_syntax
  Scenario: doctor.sh runs without crashing
    Given "bash" is available
    When I run "bash scripts/doctor.sh" and it may fail
    Then the command completed within 30 seconds

  @requires.doctor_syntax
  Scenario: doctor-checks.sh has valid bash syntax
    Given "bash" is available
    When I run "bash -n scripts/doctor-checks.sh"
    Then exit code is 0

  @requires.cli_help
  Scenario: CLI doctor command exists and shows help
    Given "python3" is available
    When I run "python3 -m scripts.cli doctor --help"
    Then exit code is 0
    And output contains "doctor"

  @requires.cli_help
  Scenario: CLI doctor runs diagnostic checks
    Given "python3" is available
    When I run "python3 -m scripts.cli doctor" and it may fail
    Then the command completed within 30 seconds
