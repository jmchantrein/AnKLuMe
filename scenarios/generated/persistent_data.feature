# Matrix: PD-001, PD-002
Feature: Persistent Data — per-machine host bind mounts

  Scenario: Persistent data generates pd- prefixed devices
    # Matrix: PD-001
    Given "python3" is available
    And a clean sandbox environment
    When I run "python3 -c 'import sys; sys.path.insert(0,"scripts"); from generate import generate, validate, enrich_infra; import yaml; from pathlib import Path; infra={"project_name":"t","global":{"addressing":{"base_octet":10,"zone_base":100}},"domains":{"pro":{"trust_level":"trusted","machines":{"pro-dev":{"type":"lxc","persistent_data":{"projects":{"path":"/home/user/projects"}}}}}}}; Path("infra.yml").write_text(yaml.dump(infra,sort_keys=False)); errors=validate(infra); assert not errors, errors; enrich_infra(infra); generate(infra,"."); hv=Path("host_vars/pro-dev.yml"); content=hv.read_text(); assert "pd-projects" in content; print("pd ok")'"
    Then exit code is 0
    And output contains "pd ok"

  Scenario: Persistent data path must be absolute
    # Matrix: PD-002
    Given "python3" is available
    And a clean sandbox environment
    When I run "python3 -c 'import sys; sys.path.insert(0,"scripts"); from generate import validate; infra={"project_name":"t","global":{"addressing":{"base_octet":10,"zone_base":100}},"domains":{"pro":{"trust_level":"trusted","machines":{"pro-dev":{"type":"lxc","persistent_data":{"data":{"path":"relative/path"}}}}}}}; errors=validate(infra); assert any("path" in e.lower() or "absolute" in e.lower() for e in errors), "Expected path error: %s" % errors'"
    Then exit code is 0
