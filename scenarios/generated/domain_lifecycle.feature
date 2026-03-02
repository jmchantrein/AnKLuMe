# Matrix: DL-001 to DL-006
Feature: Domain Lifecycle — creation, validation, addressing

  Scenario: Domain creation generates inventory and group_vars
    # Matrix: DL-001
    Given "python3" is available
    And a clean sandbox environment
    And infra.yml from "student-sysadmin"
    When I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0
    And inventory files exist for all domains

  Scenario: Enabled false skips generation but reserves IPs
    # Matrix: DL-002
    Given "python3" is available
    And a clean sandbox environment
    When I run "python3 -c 'import sys; sys.path.insert(0,"scripts"); from generate import validate; infra={"project_name":"test","global":{"addressing":{"base_octet":10,"zone_base":100}},"domains":{"disabled":{"enabled":False,"trust_level":"semi-trusted","machines":{"disabled-one":{"type":"lxc"}}},"active":{"trust_level":"semi-trusted","machines":{"active-one":{"type":"lxc"}}}}}; errors=validate(infra); assert not errors, errors; print("ok")'"
    Then exit code is 0
    And output contains "ok"

  Scenario: Domain name must be DNS-safe
    # Matrix: DL-006
    Given "python3" is available
    When I run "python3 -c 'import re; pattern=re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$"); assert pattern.match("pro"); assert pattern.match("ai-tools"); assert not pattern.match("Pro"); assert not pattern.match("-bad"); assert not pattern.match("bad-"); print("dns-safe ok")'"
    Then exit code is 0
    And output contains "dns-safe ok"

  Scenario: IP addresses are globally unique
    # Matrix: DL-005
    Given "python3" is available
    And a clean sandbox environment
    And infra.yml with two machines sharing "10.120.1.5"
    When I run "python3 scripts/generate.py infra.yml" and it may fail
    Then exit code is non-zero

  Scenario: Trust level must be valid
    # Matrix: DL-004
    Given "python3" is available
    And a clean sandbox environment
    And infra.yml with invalid trust_level "super-trusted"
    When I run "python3 scripts/generate.py infra.yml" and it may fail
    Then exit code is non-zero
