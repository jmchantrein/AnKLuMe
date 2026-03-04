Feature: Generator processes all example infra.yml files
  Verify that every example infra.yml can be synced without errors,
  produces valid Ansible files, and passes idempotency checks.

  @requires.generator
  Scenario Outline: Generator succeeds for <example> example
    Given "python3" is available
    And a clean sandbox environment
    And infra.yml from "<example>"
    When I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0
    And inventory files exist for all domains

    Examples:
      | example            |
      | student-sysadmin   |
      | developer          |
      | ai-tools           |
      | pro-workstation    |
      | sandbox-isolation  |
      | shared-services    |
      | teacher-lab        |
      | tor-gateway        |
      | llm-supervisor     |

  @requires.generator
  Scenario Outline: Generated IPs are valid for <example> example
    Given "python3" is available
    And a clean sandbox environment
    And infra.yml from "<example>"
    When I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0
    And generated host_vars contain valid IPs

    Examples:
      | example            |
      | student-sysadmin   |
      | developer          |
      | ai-tools           |
      | pro-workstation    |
      | sandbox-isolation  |
      | shared-services    |
      | tor-gateway        |

  @requires.generator
  Scenario Outline: Generator idempotency for <example>
    Given "python3" is available
    And a clean sandbox environment
    And infra.yml from "<example>"
    When I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0
    When I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0

    Examples:
      | example            |
      | student-sysadmin   |
      | developer          |
      | ai-tools           |
      | pro-workstation    |
      | sandbox-isolation  |
      | shared-services    |
      | teacher-lab        |
      | tor-gateway        |
      | llm-supervisor     |
