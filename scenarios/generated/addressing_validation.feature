# Matrix: AD-001 to AD-004
@requires.generator
Feature: Addressing Convention — trust-zone-aware IP addressing

  Scenario: base_octet must be 10
    # Matrix: AD-001
    Given "python3" is available
    And a clean sandbox environment
    When I run "python3 -c 'import sys; sys.path.insert(0,"scripts"); from generate import validate; infra={"project_name":"t","global":{"addressing":{"base_octet":11,"zone_base":100}},"domains":{"test":{"trust_level":"trusted","machines":{"test-a":{"type":"lxc"}}}}}; errors=validate(infra); assert any("base_octet" in e or "10" in e for e in errors), "Expected base_octet error: %s" % errors'"
    Then exit code is 0

  Scenario: zone_base must be in valid range
    # Matrix: AD-002
    Given "python3" is available
    And a clean sandbox environment
    When I run "python3 -c 'import sys; sys.path.insert(0,"scripts"); from generate import validate; infra={"project_name":"t","global":{"addressing":{"base_octet":10,"zone_base":250}},"domains":{"test":{"trust_level":"trusted","machines":{"test-a":{"type":"lxc"}}}}}; errors=validate(infra); assert any("zone_base" in e for e in errors), "Expected zone_base error: %s" % errors'"
    Then exit code is 0

  Scenario: Trust levels map to correct zone offsets
    # Matrix: AD-003
    Given "python3" is available
    When I run "python3 -c 'import sys; sys.path.insert(0,"scripts"); from generate import ZONE_OFFSETS; assert ZONE_OFFSETS["admin"]==0; assert ZONE_OFFSETS["untrusted"]==40; print("zones ok")'"
    Then exit code is 0
    And output contains "zones ok"

  Scenario: Gateway is always .254
    # Matrix: AD-004
    Given "python3" is available
    When I run "python3 -c 'from pathlib import Path; spec=Path("docs/SPEC.md").read_text(); assert ".254" in spec; assert "gateway" in spec.lower(); print("gateway ok")'"
    Then exit code is 0
    And output contains "gateway ok"
