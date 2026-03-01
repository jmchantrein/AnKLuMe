Feature: Web factory
  The web factory creates FastAPI applications with standard config.

  Scenario: Web factory creates FastAPI app with default title
    Given "python3" is available
    When I run "python3 -c 'from scripts.web import create_app; a = create_app(); assert a.title == "anklume"'"
    Then exit code is 0

  Scenario: Web factory creates FastAPI app with custom title
    Given "python3" is available
    When I run "python3 -c 'from scripts.web import create_app; a = create_app("X"); assert a.title == "X"'"
    Then exit code is 0

  Scenario: Web factory returns FastAPI instance
    Given "python3" is available
    When I run "python3 -c 'from fastapi import FastAPI; from scripts.web import create_app; assert isinstance(create_app(), FastAPI)'"
    Then exit code is 0
