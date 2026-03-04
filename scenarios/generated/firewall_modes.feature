# Matrix: FM-001, FM-002
@requires.generator
Feature: Firewall Modes — auto-creation and defense in depth

  Scenario: firewall_mode vm auto-creates anklume-firewall
    # Matrix: FM-001
    Given "python3" is available
    And a clean sandbox environment
    When I run "python3 -c 'import sys; sys.path.insert(0,"scripts"); from generate import enrich_infra, validate; infra={"project_name":"t","global":{"addressing":{"base_octet":10,"zone_base":100},"firewall_mode":"vm"},"domains":{"anklume":{"trust_level":"admin","machines":{"anklume-instance":{"type":"lxc"}}},"pro":{"trust_level":"trusted","machines":{"pro-dev":{"type":"lxc"}}}}}; errors=validate(infra); assert not errors, errors; enrich_infra(infra); machines=infra["domains"]["anklume"]["machines"]; assert "anklume-firewall" in machines; print("firewall auto-created")'"
    Then exit code is 0
    And output contains "firewall auto-created"

  Scenario: User-declared anklume-firewall prevents auto-creation
    # Matrix: FM-002
    Given "python3" is available
    And a clean sandbox environment
    When I run "python3 -c 'import sys; sys.path.insert(0,"scripts"); from generate import enrich_infra, validate; infra={"project_name":"t","global":{"addressing":{"base_octet":10,"zone_base":100},"firewall_mode":"vm"},"domains":{"anklume":{"trust_level":"admin","machines":{"anklume-instance":{"type":"lxc"},"anklume-firewall":{"type":"vm","roles":["firewall_router"]}}}}}; errors=validate(infra); assert not errors, errors; enrich_infra(infra); roles=infra["domains"]["anklume"]["machines"]["anklume-firewall"].get("roles",[]); assert "firewall_router" in roles; print("user-declared kept")'"
    Then exit code is 0
    And output contains "user-declared kept"
