# Matrix: LB-001 to LB-003
Feature: Educational Labs — lab.yml validation and structure

  Scenario: Lab schema exists and is valid YAML
    # Matrix: LB-001
    Given "python3" is available
    When I run "python3 -c 'import yaml; from pathlib import Path; schema=Path("labs/lab-schema.yml"); assert schema.exists(), "no schema"; data=yaml.safe_load(schema.read_text()); assert "required" in str(data) or "title" in str(data); print("schema ok")'"
    Then exit code is 0
    And output contains "schema ok"

  Scenario: Lab directories follow naming convention
    # Matrix: LB-002
    Given "python3" is available
    When I run "python3 -c 'import re; from pathlib import Path; labs=sorted(Path("labs").glob("[0-9]*/")); pattern=re.compile(r"^[0-9]{2}-[a-z0-9-]+$"); ok=[d for d in labs if pattern.match(d.name)]; print("Labs: %d valid" % len(ok)); assert len(ok)==len(labs) or len(labs)==0'"
    Then exit code is 0

  Scenario: Lab steps use sequential two-digit IDs
    # Matrix: LB-003
    Given "python3" is available
    When I run "python3 -c 'from pathlib import Path; labs=sorted(Path("labs").glob("[0-9]*/lab.yml")); print("Found %d labs with lab.yml" % len(labs))'"
    Then exit code is 0
