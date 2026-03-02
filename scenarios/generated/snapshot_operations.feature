# Matrix: SN-001, SN-002
Feature: Snapshot Operations — shell script and Ansible role

  Scenario: snap.sh passes shellcheck
    # Matrix: SN-001
    Given "shellcheck" is available
    When I run "shellcheck -S warning scripts/snap.sh"
    Then exit code is 0

  Scenario: snap.sh supports self keyword and help
    # Matrix: SN-002
    Given "bash" is available
    When I run "bash scripts/snap.sh --help"
    Then exit code is 0
    And output contains "Usage"
