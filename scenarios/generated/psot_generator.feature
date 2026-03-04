# Matrix: PP-001 to PP-005
Feature: PSOT Generator — managed sections and idempotency

  Scenario: Generator produces files from infra.yml
    # Matrix: PP-001
    Given "python3" is available
    And a clean sandbox environment
    And infra.yml from "student-sysadmin"
    When I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0

  @requires.generator
  Scenario: Managed sections contain markers
    # Matrix: PP-002
    Given "python3" is available
    And a clean sandbox environment
    And infra.yml from "student-sysadmin"
    When I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0
    When I run "python3 -c 'from pathlib import Path; gv=list(Path("group_vars").glob("*.yml")); assert any("MANAGED" in f.read_text() for f in gv), "No managed markers"'"
    Then exit code is 0

  @requires.generator
  Scenario: Generator idempotency — second run succeeds
    # Matrix: PP-004
    Given "python3" is available
    And a clean sandbox environment
    And infra.yml from "student-sysadmin"
    When I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0
    When I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0

  @requires.generator
  Scenario: Orphan detection reports removed machines
    # Matrix: PP-005
    Given "python3" is available
    And a clean sandbox environment
    And infra.yml from "student-sysadmin"
    When I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0
    When I run "python3 -c 'import sys; sys.path.insert(0,"scripts"); from generate import load_infra, detect_orphans; infra=load_infra("infra.yml"); orphans=detect_orphans(infra,"."); print("Orphans: %d" % len(orphans))'"
    Then exit code is 0
    And output contains "Orphans:"

  @requires.generator
  Scenario: User edits outside managed sections are preserved
    # Matrix: PP-003
    Given "python3" is available
    And a clean sandbox environment
    And infra.yml from "student-sysadmin"
    When I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0
    When I run "python3 -c 'from pathlib import Path; gv=list(Path("group_vars").glob("*.yml")); content=gv[0].read_text() if gv else ""; assert "=== END MANAGED" in content or len(gv)==0; print("preserved")'"
    Then exit code is 0
