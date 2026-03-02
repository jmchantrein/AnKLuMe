# Matrix: EL-001, BA-001, BA-002
Feature: Ephemeral Policy and Boot Configuration

  Scenario: Ephemeral flag validates as boolean
    # Matrix: EL-001
    Given "python3" is available
    And a clean sandbox environment
    When I run "python3 -c 'import sys; sys.path.insert(0,"scripts"); from generate import validate; infra={"project_name":"t","global":{"addressing":{"base_octet":10,"zone_base":100}},"domains":{"test":{"trust_level":"trusted","ephemeral":"maybe","machines":{"test-a":{"type":"lxc"}}}}}; errors=validate(infra); assert any("ephemeral" in e.lower() for e in errors), "Expected ephemeral error: %s" % errors'"
    Then exit code is 0

  Scenario: Boot autostart validates as boolean
    # Matrix: BA-001
    Given "python3" is available
    And a clean sandbox environment
    When I run "python3 -c 'import sys; sys.path.insert(0,"scripts"); from generate import validate; infra={"project_name":"t","global":{"addressing":{"base_octet":10,"zone_base":100}},"domains":{"test":{"trust_level":"trusted","machines":{"test-a":{"type":"lxc","boot_autostart":"yes"}}}}}; errors=validate(infra); assert any("boot" in e.lower() or "autostart" in e.lower() for e in errors), "Expected boot error: %s" % errors'"
    Then exit code is 0

  Scenario: Boot priority must be 0-100
    # Matrix: BA-002
    Given "python3" is available
    And a clean sandbox environment
    And infra.yml with boot_priority 200
    When I run "python3 scripts/generate.py infra.yml" and it may fail
    Then exit code is non-zero
