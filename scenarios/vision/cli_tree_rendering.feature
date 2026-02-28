@vision
Feature: CLI tree graph rendering
  The cli-tree command output must produce valid structured output
  that renders correctly as a visual graph.

  Background:
    Given a clean sandbox environment
    And vision agent is available

  Scenario: Mermaid output is a valid graph
    When I capture CLI output of "python3 -m scripts.cli dev cli-tree --format mermaid"
    Then the captured output contains visible text "graph"
    And the captured output is readable

  Scenario: Deps output shows dependency graph
    When I capture CLI output of "python3 -m scripts.cli dev cli-tree --format deps"
    Then the captured output contains visible text "graph"
    And the captured output is readable
