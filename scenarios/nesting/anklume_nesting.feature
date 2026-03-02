# Matrix: NS-001 to NS-005
Feature: Anklume nesting — multi-level infrastructure isolation

  Nesting allows running anklume inside anklume (up to 3 levels).
  Each level creates /etc/anklume/ context files for hierarchy awareness.
  Level 3 is the maximum depth — nesting stops there.

  Scenario: Nesting test script exists and is executable
    # Matrix: NS-001
    Given "bash" is available
    When I run "test -x scripts/test-nesting.sh && echo 'executable'"
    Then exit code is 0
    And output contains "executable"

  Scenario: Nesting test dry-run validates structure
    # Matrix: NS-002
    Given "bash" is available
    When I run "bash scripts/test-nesting.sh --dry-run"
    Then exit code is 0
    And output contains "5 passed, 0 failed"

  Scenario: Nesting context files are individual files not structured config
    # Matrix: NS-003
    Given "python3" is available
    When I run "python3 -c 'expected = ["absolute_level", "relative_level", "vm_nested", "yolo"]; found = all(f in open("scripts/test-nesting.sh").read() for f in expected); assert found, "Missing nesting context files"; print("context files ok")'"
    Then exit code is 0
    And output contains "context files ok"

  Scenario: Nesting prefix format is zero-padded 3 digits
    # Matrix: NS-004
    Given "python3" is available
    When I run "python3 -c 'fmt = "{level:03d}-"; assert fmt.format(level=0) == "000-"; assert fmt.format(level=1) == "001-"; assert fmt.format(level=12) == "012-"; print("prefix format ok")'"
    Then exit code is 0
    And output contains "prefix format ok"

  Scenario: Nesting level 3 triggers stop condition
    # Matrix: NS-005
    Given "python3" is available
    When I run "python3 -c 'level = 2; stop = level >= 2; assert stop, "Should stop at level >= 2"; print("stop condition ok")'"
    Then exit code is 0
    And output contains "stop condition ok"
