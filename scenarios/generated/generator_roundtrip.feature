Feature: Generator roundtrip — sync produces consistent files
  End-to-end tests verifying the full generate → verify → modify → re-generate
  workflow, including user edits outside managed sections.

  @requires.generator
  Scenario: Fresh generate from empty state
    Given "python3" is available
    And a clean sandbox environment
    And infra.yml from "student-sysadmin"
    And no generated files exist
    When I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0
    And inventory files exist for all domains
    And generated host_vars contain valid IPs

  @requires.generator
  Scenario: User edits outside managed sections survive re-sync
    Given "python3" is available
    And a clean sandbox environment
    And infra.yml from "student-sysadmin"
    When I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0
    When I run "bash -c 'f=$(ls group_vars/*.yml | head -1); echo >> $f; echo "# USER_CUSTOM_VARIABLE: true" >> $f'"
    Then exit code is 0
    When I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0
    When I run "grep -r USER_CUSTOM_VARIABLE group_vars/"
    Then exit code is 0
    And output contains "USER_CUSTOM_VARIABLE"

  @requires.generator
  Scenario: Adding a domain creates new inventory and group_vars
    Given "python3" is available
    And a clean sandbox environment
    And infra.yml from "student-sysadmin"
    When I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0
    When I add a domain "newdomain" to infra.yml
    When I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0
    Then file "inventory/newdomain.yml" exists
    And file "group_vars/newdomain.yml" exists

  @requires.generator
  Scenario: Dry-run mode does not write files
    Given "python3" is available
    And a clean sandbox environment
    And infra.yml from "student-sysadmin"
    And no generated files exist
    When I run "python3 scripts/generate.py infra.yml --dry-run"
    Then exit code is 0
    Then file "inventory/pro.yml" does not exist

  @requires.generator
  Scenario: Managed section markers are present in generated files
    Given "python3" is available
    And a clean sandbox environment
    And infra.yml from "student-sysadmin"
    When I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0
    When I run "grep -rl MANAGED group_vars/"
    Then exit code is 0
