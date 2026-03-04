Feature: CLI functional tests — commands produce correct output
  Tests that CLI commands actually work (not just --help), producing
  meaningful output or modifying state correctly.

  @requires.cli_help
  Scenario: mode show displays current mode
    Given "python3" is available
    When I run "python3 -m scripts.cli mode"
    Then exit code is 0
    And output contains "Current mode"

  @requires.cli_help
  Scenario: mode user sets mode to user
    Given "python3" is available
    When I run "python3 -m scripts.cli mode user"
    Then exit code is 0
    And output contains "user"
    When I run "python3 -m scripts.cli mode"
    Then exit code is 0
    And output contains "user"

  @requires.cli_help
  Scenario: mode student sets mode to student
    Given "python3" is available
    When I run "python3 -m scripts.cli mode student"
    Then exit code is 0
    When I run "python3 -m scripts.cli mode"
    Then exit code is 0
    And output contains "student"
    # Restore user mode
    When I run "python3 -m scripts.cli mode user"
    Then exit code is 0

  @requires.cli_help
  Scenario: mode dev sets mode to dev
    Given "python3" is available
    When I run "python3 -m scripts.cli mode dev"
    Then exit code is 0
    When I run "python3 -m scripts.cli mode"
    Then exit code is 0
    And output contains "dev"
    # Restore user mode
    When I run "python3 -m scripts.cli mode user"
    Then exit code is 0

  @requires.cli_help
  Scenario: mode accessibility --show displays settings
    Given "python3" is available
    When I run "python3 -m scripts.cli mode accessibility --show"
    Then exit code is 0
    And output contains "Palette"

  @requires.cli_help
  Scenario: mode learn-incus shows current state
    Given "python3" is available
    When I run "python3 -m scripts.cli mode learn-incus"
    Then exit code is 0
    And output contains "learning mode"

  @requires.cli_help
  Scenario: domain list shows domains from infra.yml
    Given "python3" is available
    And a clean sandbox environment
    And infra.yml from "student-sysadmin"
    When I run "python3 -m scripts.cli domain list"
    Then exit code is 0
    And output contains "Domains"

  @requires.cli_help
  Scenario: sync --dry-run previews changes
    Given "python3" is available
    And a clean sandbox environment
    And infra.yml from "student-sysadmin"
    When I run "python3 -m scripts.cli sync --dry-run"
    Then exit code is 0

  @requires.cli_help
  Scenario: sync generates files from infra.yml
    Given "python3" is available
    And a clean sandbox environment
    And infra.yml from "student-sysadmin"
    When I run "python3 -m scripts.cli sync"
    Then exit code is 0
    And inventory files exist for all domains

  @requires.cli_help
  Scenario: domain check --help documents check/diff
    Given "python3" is available
    When I run "python3 -m scripts.cli domain check --help"
    Then exit code is 0
    And output contains "check"
