Feature: Generator validation — error detection on invalid infra.yml
  Test that the generator correctly rejects various types of invalid
  configurations with meaningful error messages.

  @requires.generator
  Scenario: Duplicate IPs are rejected
    Given "python3" is available
    And a clean sandbox environment
    And infra.yml with two machines sharing "10.120.0.1"
    When I run "python3 scripts/generate.py infra.yml" and it may fail
    Then exit code is non-zero

  @requires.generator
  Scenario: Invalid trust level is rejected
    Given "python3" is available
    And a clean sandbox environment
    And infra.yml with invalid trust_level "dangerous"
    When I run "python3 scripts/generate.py infra.yml" and it may fail
    Then exit code is non-zero

  @requires.generator
  Scenario: Invalid snapshots schedule is rejected
    Given "python3" is available
    And a clean sandbox environment
    And infra.yml with invalid snapshots_schedule "every day"
    When I run "python3 scripts/generate.py infra.yml" and it may fail
    Then exit code is non-zero

  @requires.generator
  Scenario: Invalid snapshots expiry is rejected
    Given "python3" is available
    And a clean sandbox environment
    And infra.yml with invalid snapshots_expiry "forever"
    When I run "python3 scripts/generate.py infra.yml" and it may fail
    Then exit code is non-zero

  @requires.generator
  Scenario: Out-of-range boot priority is rejected
    Given "python3" is available
    And a clean sandbox environment
    And infra.yml with boot_priority 200
    When I run "python3 scripts/generate.py infra.yml" and it may fail
    Then exit code is non-zero

  @requires.generator
  Scenario: Unknown shared volume consumer is rejected
    Given "python3" is available
    And a clean sandbox environment
    And infra.yml with shared_volume consumer "nonexistent-domain"
    When I run "python3 scripts/generate.py infra.yml" and it may fail
    Then exit code is non-zero

  @requires.generator
  Scenario: Relative shared volume path is rejected
    Given "python3" is available
    And a clean sandbox environment
    And infra.yml with shared_volume relative path "relative/path"
    When I run "python3 scripts/generate.py infra.yml" and it may fail
    Then exit code is non-zero

  @requires.generator
  Scenario: Duplicate machine names across domains are rejected
    Given "python3" is available
    And a clean sandbox environment
    And infra.yml with duplicate machine "shared-name" in two domains
    When I run "python3 scripts/generate.py infra.yml" and it may fail
    Then exit code is non-zero

  @requires.generator
  Scenario: Missing domains section is rejected
    Given "python3" is available
    And a clean sandbox environment
    And infra.yml with no domains section
    When I run "python3 scripts/generate.py infra.yml" and it may fail
    Then exit code is non-zero
