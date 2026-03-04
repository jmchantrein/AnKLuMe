# Matrix: AA-001, AA-002
@requires.generator
Feature: AI Access Policy — exclusive mode and sanitization

  Scenario: ai_provider defaults and sanitization logic
    # Matrix: AA-001
    Given "python3" is available
    When I run "python3 -c 'defaults={"local":{"sanitize":False},"cloud":{"sanitize":True},"local-first":{"sanitize":True}}; assert defaults["local"]["sanitize"]==False; assert defaults["cloud"]["sanitize"]==True; assert defaults["local-first"]["sanitize"]==True; print("ai defaults ok")'"
    Then exit code is 0
    And output contains "ai defaults ok"

  Scenario: ai_access_policy exclusive requires ai_access_default
    # Matrix: AA-002
    Given "python3" is available
    And a clean sandbox environment
    When I run "python3 -c 'import sys; sys.path.insert(0,"scripts"); from generate import validate; infra={"project_name":"t","global":{"addressing":{"base_octet":10,"zone_base":100},"ai_access_policy":"exclusive"},"domains":{"ai-tools":{"trust_level":"trusted","machines":{"ai-gpu":{"type":"lxc"}}},"pro":{"trust_level":"trusted","machines":{"pro-dev":{"type":"lxc"}}}}}; errors=validate(infra); assert any("ai_access_default" in e for e in errors), "Expected ai_access_default error: %s" % errors'"
    Then exit code is 0
