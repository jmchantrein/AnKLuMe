# Matrix: NP-001 to NP-003
@requires.generator
Feature: Network Policies — cross-domain rules validation

  Scenario: Network policy validates known source and destination
    # Matrix: NP-001
    Given "python3" is available
    And a clean sandbox environment
    When I run "python3 -c 'import sys; sys.path.insert(0,"scripts"); from generate import validate; infra={"project_name":"t","global":{"addressing":{"base_octet":10,"zone_base":100}},"domains":{"pro":{"trust_level":"trusted","machines":{"pro-dev":{"type":"lxc"}}},"ai-tools":{"trust_level":"trusted","machines":{"ai-gpu":{"type":"lxc"}}}},"network_policies":[{"description":"Pro to AI","from":"pro","to":"ai-tools","ports":[11434],"protocol":"tcp"}]}; errors=validate(infra); policy_errors=[e for e in errors if "network" in e.lower() or "policy" in e.lower()]; assert not policy_errors, policy_errors; print("policy ok")'"
    Then exit code is 0
    And output contains "policy ok"

  Scenario: Network policy rejects unknown source domain
    # Matrix: NP-002
    Given "python3" is available
    And a clean sandbox environment
    When I run "python3 -c 'import sys; sys.path.insert(0,"scripts"); from generate import validate; infra={"project_name":"t","global":{"addressing":{"base_octet":10,"zone_base":100}},"domains":{"pro":{"trust_level":"trusted","machines":{"pro-dev":{"type":"lxc"}}}},"network_policies":[{"description":"bad","from":"unknown","to":"pro","ports":[80],"protocol":"tcp"}]}; errors=validate(infra); assert any("unknown" in e.lower() for e in errors), "Expected error about unknown: %s" % errors'"
    Then exit code is 0

  Scenario: Host keyword is valid in network policy
    # Matrix: NP-003
    Given "python3" is available
    And a clean sandbox environment
    When I run "python3 -c 'import sys; sys.path.insert(0,"scripts"); from generate import validate; infra={"project_name":"t","global":{"addressing":{"base_octet":10,"zone_base":100}},"domains":{"ai-tools":{"trust_level":"trusted","machines":{"ai-gpu":{"type":"lxc"}}}},"network_policies":[{"description":"Host to AI","from":"host","to":"ai-gpu","ports":[11434],"protocol":"tcp"}]}; errors=validate(infra); host_errors=[e for e in errors if "host" in e.lower() and ("unknown" in e.lower() or "invalid" in e.lower())]; assert not host_errors, host_errors; print("host ok")'"
    Then exit code is 0
    And output contains "host ok"
