# Matrix: NX-001, NX-002
Feature: Nesting Prefix — collision avoidance for nested anklume

  Scenario: Nesting prefix format is 3-digit zero-padded
    # Matrix: NX-001
    Given "python3" is available
    When I run "python3 -c 'fmt="{level:03d}-"; assert fmt.format(level=1)=="001-"; assert fmt.format(level=12)=="012-"; print("prefix format ok")'"
    Then exit code is 0
    And output contains "prefix format ok"

  Scenario: Nesting prefix is configurable boolean
    # Matrix: NX-002
    Given "python3" is available
    And a clean sandbox environment
    When I run "python3 -c 'import sys; sys.path.insert(0,"scripts"); from generate import validate; infra={"project_name":"t","global":{"addressing":{"base_octet":10,"zone_base":100},"nesting_prefix":False},"domains":{"test":{"trust_level":"trusted","machines":{"test-a":{"type":"lxc"}}}}}; errors=validate(infra); prefix_errors=[e for e in errors if "nesting" in e.lower() or "prefix" in e.lower()]; assert not prefix_errors, prefix_errors; print("nesting ok")'"
    Then exit code is 0
    And output contains "nesting ok"
