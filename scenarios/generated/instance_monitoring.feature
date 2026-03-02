# Matrix: IM-001 to IM-002
Feature: Instance monitoring — Rich table with resource usage

  Scenario: Instance list command exists in CLI
    # Matrix: IM-001
    Given "python3" is available
    When I run "python3 -c 'from scripts.cli.instance import app; cmds=[c.name for c in app.registered_commands]; assert "list" in cmds; print("list command ok")'"
    Then exit code is 0
    And output contains "list command ok"

  Scenario: Instance list supports sort option
    # Matrix: IM-002
    Given "python3" is available
    When I run "python3 -c 'import inspect; from scripts.cli.instance import list_; sig=inspect.signature(list_); assert "sort" in sig.parameters; print("sort option ok")'"
    Then exit code is 0
    And output contains "sort option ok"
