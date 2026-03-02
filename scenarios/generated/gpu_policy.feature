# Matrix: GP-001, GP-005
Feature: GPU Policy — exclusive and shared modes

  Scenario: Exclusive GPU policy rejects duplicate gpu instances
    # Matrix: GP-001
    Given "python3" is available
    And a clean sandbox environment
    When I run "python3 -c 'import sys; sys.path.insert(0,"scripts"); from generate import validate; infra={"project_name":"t","global":{"addressing":{"base_octet":10,"zone_base":100}},"domains":{"test":{"trust_level":"trusted","machines":{"test-a":{"type":"lxc","gpu":True},"test-b":{"type":"lxc","gpu":True}}}}}; errors=validate(infra); assert any("gpu" in e.lower() or "GPU" in e for e in errors), "No GPU error: %s" % errors'"
    Then exit code is 0

  Scenario: Shared GPU policy allows multiple GPU instances
    # Matrix: GP-005
    Given "python3" is available
    And a clean sandbox environment
    When I run "python3 -c 'import sys; sys.path.insert(0,"scripts"); from generate import validate; infra={"project_name":"t","global":{"addressing":{"base_octet":10,"zone_base":100},"gpu_policy":"shared"},"domains":{"test":{"trust_level":"trusted","machines":{"test-a":{"type":"lxc","gpu":True},"test-b":{"type":"lxc","gpu":True}}}}}; errors=validate(infra); gpu_errors=[e for e in errors if "gpu" in e.lower() or "GPU" in e]; assert not gpu_errors, gpu_errors; print("shared ok")'"
    Then exit code is 0
    And output contains "shared ok"
