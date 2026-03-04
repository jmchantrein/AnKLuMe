# Matrix: RP-001, RP-002
@requires.generator
Feature: Resource Policy — automatic CPU and memory allocation

  Scenario: Resource policy validates mode values
    # Matrix: RP-001
    Given "python3" is available
    And a clean sandbox environment
    When I run "python3 -c 'import sys; sys.path.insert(0,"scripts"); from generate import validate; infra={"project_name":"t","global":{"addressing":{"base_octet":10,"zone_base":100},"resource_policy":{"mode":"invalid"}},"domains":{"test":{"trust_level":"trusted","machines":{"test-a":{"type":"lxc"}}}}}; errors=validate(infra); assert any("mode" in e.lower() or "resource" in e.lower() for e in errors), "Expected resource mode error: %s" % errors'"
    Then exit code is 0

  Scenario: Resource policy proportional mode accepted
    # Matrix: RP-002
    Given "python3" is available
    And a clean sandbox environment
    When I run "python3 -c 'import sys; sys.path.insert(0,"scripts"); from generate import validate; infra={"project_name":"t","global":{"addressing":{"base_octet":10,"zone_base":100},"resource_policy":{"mode":"proportional","host_reserve":{"cpu":"20%","memory":"20%"}}},"domains":{"test":{"trust_level":"trusted","machines":{"test-a":{"type":"lxc"}}}}}; errors=validate(infra); rp_errors=[e for e in errors if "resource" in e.lower() or "mode" in e.lower()]; assert not rp_errors, rp_errors; print("rp ok")'"
    Then exit code is 0
    And output contains "rp ok"
