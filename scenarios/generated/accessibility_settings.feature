Feature: Accessibility settings — palette, font, dyslexia mode
  Verify that accessibility settings persist correctly and
  reject invalid values.

  Scenario: Accessibility module is importable
    Given "python3" is available
    When I run "python3 -c 'from scripts.accessibility import load_accessibility, save_accessibility; s=load_accessibility(); assert isinstance(s, dict)'"
    Then exit code is 0

  @requires.cli_help
  Scenario: Accessibility palette can be changed
    Given "python3" is available
    When I run "python3 -m scripts.cli mode accessibility --palette high-contrast"
    Then exit code is 0
    And output contains "updated"
    When I run "python3 -m scripts.cli mode accessibility --show"
    Then exit code is 0
    And output contains "high-contrast"
    # Restore default
    When I run "python3 -m scripts.cli mode accessibility --palette default"
    Then exit code is 0

  @requires.cli_help
  Scenario: Invalid palette is rejected
    Given "python3" is available
    When I run "python3 -m scripts.cli mode accessibility --palette neon-glow" and it may fail
    Then exit code is non-zero

  @requires.cli_help
  Scenario: Font size can be set
    Given "python3" is available
    When I run "python3 -m scripts.cli mode accessibility --font-size 16"
    Then exit code is 0
    And output contains "updated"

  @requires.cli_help
  Scenario: Invalid font size is rejected
    Given "python3" is available
    When I run "python3 -m scripts.cli mode accessibility --font-size 200" and it may fail
    Then exit code is non-zero

  @requires.cli_help
  Scenario: Dyslexia mode can be toggled
    Given "python3" is available
    When I run "python3 -m scripts.cli mode accessibility --dyslexia"
    Then exit code is 0
    When I run "python3 -m scripts.cli mode accessibility --show"
    Then exit code is 0
    And output contains "True"
    When I run "python3 -m scripts.cli mode accessibility --no-dyslexia"
    Then exit code is 0

  @requires.cli_help
  Scenario: Tmux coloring option is accepted
    Given "python3" is available
    When I run "python3 -m scripts.cli mode accessibility --tmux-coloring title-only"
    Then exit code is 0
    When I run "python3 -m scripts.cli mode accessibility --show"
    Then exit code is 0
    And output contains "title-only"
    # Restore
    When I run "python3 -m scripts.cli mode accessibility --tmux-coloring full"
    Then exit code is 0
