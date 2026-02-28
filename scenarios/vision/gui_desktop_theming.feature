@vision @gui
Feature: Desktop theming follows trust levels
  Desktop window borders and decorations use QubesOS-style
  color coding based on domain trust levels from infra.yml.

  Background:
    Given a clean sandbox environment
    And vision agent is available

  Scenario: Desktop screenshot shows themed windows
    Given a desktop screenshot is available
    Then the screenshot shows window decorations
    And window borders use domain-specific colors

  Scenario: Desktop theme is consistent with infra.yml
    Given a desktop screenshot is available
    Then the screenshot layout matches expected desktop environment
