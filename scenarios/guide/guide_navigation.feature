Feature: Guide navigation and progression
  The guide presents chapters sequentially with progression tracking.

  Scenario: Guide displays help
    Given "bash" is available
    When I run "bash scripts/guide.sh --help"
    Then exit code is 0
    And output contains "--chapter"
    And output contains "--setup"

  Scenario: Guide setup mode delegates to setup wizard
    Given "bash" is available
    And "incus" is available
    And Incus daemon is available
    When I run "bash scripts/guide-setup.sh --auto --step 1" and it may fail
    Then output contains "Prerequisites"

  Scenario: Guide chapter scripts are executable
    Given "bash" is available
    When I run "bash -n scripts/guide/ch01-isolation.sh"
    Then exit code is 0

  Scenario: All chapter scripts have valid syntax
    Given "bash" is available
    When I run "for f in scripts/guide/ch*.sh; do bash -n $f || exit 1; done"
    Then exit code is 0

  Scenario: Guide lib is sourceable
    Given "bash" is available
    When I run "bash -c 'source scripts/guide-lib.sh'"
    Then exit code is 0
