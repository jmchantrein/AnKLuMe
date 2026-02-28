@vision
Feature: CLI help output visual verification
  The --help output must be formatted and readable when rendered
  as an image. Uses VisionAgent to verify terminal output quality.

  Background:
    Given a clean sandbox environment
    And vision agent is available

  Scenario: anklume --help is readable
    When I capture CLI output of "python3 -m scripts.cli --help"
    Then the captured output is readable
    And the captured output contains visible text "Usage"

  Scenario: anklume dev --help shows subcommands
    When I capture CLI output of "python3 -m scripts.cli dev --help"
    Then the captured output is readable
    And the captured output contains visible text "lint"
