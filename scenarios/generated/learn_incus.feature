# Matrix: LI-001 to LI-002
Feature: Learn Incus — display underlying incus commands

  Scenario: Learn incus toggle file path
    # Matrix: LI-001
    Given "python3" is available
    When I run "python3 -c 'from scripts.cli._helpers import is_learn_incus; from pathlib import Path; p=Path.home()/".anklume"/"learn_incus"; print("path: %s" % p)'"
    Then exit code is 0
    And output contains ".anklume/learn_incus"

  Scenario: Learn incus mode command exists
    # Matrix: LI-002
    Given "python3" is available
    When I run "python3 -c 'from scripts.cli.mode import app; cmds=[c.name for c in app.registered_commands]; assert "learn-incus" in cmds; print("learn-incus command ok")'"
    Then exit code is 0
    And output contains "learn-incus command ok"
