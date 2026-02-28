@vision @gui
Feature: Console domain color coding
  The anklume console shows domain panes with QubesOS-style
  color coding matching trust levels. Requires running infrastructure
  and a GUI environment.

  Background:
    Given a clean sandbox environment
    And vision agent is available

  Scenario: Console screenshot shows colored domain labels
    Given a console screenshot is available
    Then the screenshot shows domain color coding
    And the screenshot contains labeled panes

  Scenario: Trust level colors match specification
    Given a console screenshot is available
    Then admin domains appear in blue tones
    And untrusted domains appear in red tones
