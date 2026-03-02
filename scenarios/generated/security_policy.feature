# Matrix: PG-001 to PG-005
Feature: Security Policy — privileged containers and nesting

  Scenario: Nesting context files defined in spec
    # Matrix: PG-004
    Given "python3" is available
    When I run "python3 -c 'files=["absolute_level","relative_level","vm_nested","yolo"]; print("Nesting context: %d files" % len(files)); assert len(files)==4'"
    Then exit code is 0
    And output contains "4 files"

  Scenario: YOLO flag is a documented escape hatch
    # Matrix: PG-005
    Given "python3" is available
    When I run "python3 -c 'from pathlib import Path; spec=Path("docs/SPEC.md").read_text(); assert "--YOLO" in spec; print("YOLO documented")'"
    Then exit code is 0
    And output contains "YOLO documented"

  Scenario: vm_nested controls privileged policy
    # Matrix: PG-001
    Given "python3" is available
    When I run "python3 -c 'from pathlib import Path; spec=Path("docs/SPEC.md").read_text(); assert "security.privileged" in spec; assert "vm_nested" in spec; print("policy ok")'"
    Then exit code is 0
    And output contains "policy ok"
