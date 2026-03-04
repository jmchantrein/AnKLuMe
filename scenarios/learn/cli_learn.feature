@requires.learn_cli
Feature: Learn CLI
  CLI commands for the interactive learning platform. Provides start,
  setup, and teardown commands.

  Scenario: Learn CLI module has valid syntax
    Given "python3" is available
    When I run "python3 -m py_compile scripts/cli/learn.py"
    Then exit code is 0

  Scenario: Learn CLI has three commands
    Given "python3" is available
    When I run "python3 -c 'from scripts.cli.learn import app; cmds = [c.callback.__name__ for c in app.registered_commands]; assert "start" in cmds and "setup" in cmds and "teardown" in cmds'"
    Then exit code is 0

  Scenario: Learn CLI app name is learn
    Given "python3" is available
    When I run "python3 -c 'from scripts.cli.learn import app; assert app.info.name == "learn"'"
    Then exit code is 0

  Scenario: Learn CLI app has help text
    Given "python3" is available
    When I run "python3 -c 'from scripts.cli.learn import app; assert app.info.help is not None and len(app.info.help) > 10'"
    Then exit code is 0

  Scenario: Learn CLI has exactly three registered commands
    Given "python3" is available
    When I run "python3 -c 'from scripts.cli.learn import app; assert len(app.registered_commands) == 3'"
    Then exit code is 0
