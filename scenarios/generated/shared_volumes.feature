# Matrix: SV-001 to SV-004
@requires.generator
Feature: Shared Volumes — declarative cross-domain data sharing

  Scenario: Shared volume generates sv- prefixed devices
    # Matrix: SV-001
    Given "python3" is available
    And a clean sandbox environment
    When I run "python3 -c 'import sys; sys.path.insert(0,"scripts"); from generate import load_infra, generate, validate, enrich_infra; import yaml; from pathlib import Path; infra={"project_name":"t","global":{"addressing":{"base_octet":10,"zone_base":100}},"domains":{"pro":{"trust_level":"trusted","machines":{"pro-dev":{"type":"lxc"}}}},"shared_volumes":{"docs":{"path":"/shared/docs","consumers":{"pro":"ro"}}}}; Path("infra.yml").write_text(yaml.dump(infra,sort_keys=False)); errors=validate(infra); assert not errors, errors; enrich_infra(infra); generate(infra,"."); hv=Path("host_vars/pro-dev.yml"); content=hv.read_text(); assert "sv-docs" in content; print("sv ok")'"
    Then exit code is 0
    And output contains "sv ok"

  Scenario: Shared volume rejects unknown consumer
    # Matrix: SV-003
    Given "python3" is available
    And a clean sandbox environment
    And infra.yml with shared_volume consumer "nonexistent"
    When I run "python3 scripts/generate.py infra.yml" and it may fail
    Then exit code is non-zero

  Scenario: Shared volume rejects relative path
    # Matrix: SV-004
    Given "python3" is available
    And a clean sandbox environment
    And infra.yml with shared_volume relative path "relative/path"
    When I run "python3 scripts/generate.py infra.yml" and it may fail
    Then exit code is non-zero
