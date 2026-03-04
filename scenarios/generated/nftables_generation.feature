Feature: Network isolation — CLI commands and deploy script
  Verify that network-related CLI commands exist and the
  deploy script has valid syntax.

  @requires.cli_help
  Scenario: network rules --help exits 0
    Given "python3" is available
    When I run "python3 -m scripts.cli network rules --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: network deploy --help exits 0
    Given "python3" is available
    When I run "python3 -m scripts.cli network deploy --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: network status --help exits 0
    Given "python3" is available
    When I run "python3 -m scripts.cli network status --help"
    Then exit code is 0

  Scenario: deploy-nftables.sh has valid bash syntax
    Given "bash" is available
    When I run "bash -n scripts/deploy-nftables.sh"
    Then exit code is 0
