Feature: Script imports — all user-facing Python scripts importable
  Every Python script that users or the framework invoke must be
  importable without crashing. This catches missing dependencies,
  circular imports, and syntax errors before they reach production.

  # ── Gate: core imports work ────────────────────────────────

  @gate.script_imports
  Scenario: generate.py is importable from project root
    Given "python3" is available
    When I run "python3 -c 'import scripts.generate'"
    Then exit code is 0

  @gate.script_imports
  Scenario: generate.py is importable from scripts directory
    Given "python3" is available
    When I run "cd scripts && python3 -c 'import generate'"
    Then exit code is 0

  # ── welcome.py (CRITICAL - was broken) ─────────────────────

  @gate.welcome_import
  Scenario: welcome.py is importable from scripts directory
    Given "python3" is available
    When I run "cd scripts && python3 -c 'import welcome'"
    Then exit code is 0

  @requires.welcome_import
  Scenario: welcome.py syntax is valid
    Given "python3" is available
    When I run "python3 -m py_compile scripts/welcome.py"
    Then exit code is 0

  @requires.welcome_import
  Scenario: welcome_strings.py is importable from scripts directory
    Given "python3" is available
    When I run "cd scripts && python3 -c 'import welcome_strings'"
    Then exit code is 0

  @requires.welcome_import
  Scenario: welcome_strings.py is importable from project root
    Given "python3" is available
    When I run "python3 -c 'import scripts.welcome_strings'"
    Then exit code is 0

  # ── console.py ─────────────────────────────────────────────

  @requires.script_imports
  Scenario: console.py syntax is valid
    Given "python3" is available
    When I run "python3 -m py_compile scripts/console.py"
    Then exit code is 0

  @requires.script_imports
  Scenario: console.py is importable from scripts directory
    Given "python3" is available
    When I run "cd scripts && python3 -c 'import console'"
    Then exit code is 0

  # ── dashboard.py ───────────────────────────────────────────

  @requires.script_imports
  Scenario: dashboard.py syntax is valid
    Given "python3" is available
    When I run "python3 -m py_compile scripts/dashboard.py"
    Then exit code is 0

  @requires.script_imports
  Scenario: dashboard.py is importable from project root
    Given "python3" is available
    When I run "python3 -c 'import scripts.dashboard'"
    Then exit code is 0

  # ── platform_server.py ─────────────────────────────────────

  @requires.script_imports
  Scenario: platform_server.py syntax is valid
    Given "python3" is available
    When I run "python3 -m py_compile scripts/platform_server.py"
    Then exit code is 0

  @requires.script_imports
  Scenario: platform_server.py is importable from project root
    Given "python3" is available
    When I run "python3 -c 'from scripts.platform_server import app'"
    Then exit code is 0

  # ── telemetry.py ───────────────────────────────────────────

  @requires.script_imports
  Scenario: telemetry.py syntax is valid
    Given "python3" is available
    When I run "python3 -m py_compile scripts/telemetry.py"
    Then exit code is 0

  @requires.script_imports
  Scenario: telemetry.py is importable from scripts directory
    Given "python3" is available
    When I run "cd scripts && python3 -c 'import telemetry'"
    Then exit code is 0

  # ── CLI module compiles ────────────────────────────────────

  @requires.script_imports
  Scenario: CLI __init__.py compiles
    Given "python3" is available
    When I run "python3 -m py_compile scripts/cli/__init__.py"
    Then exit code is 0

  @requires.script_imports
  Scenario: CLI __main__.py compiles
    Given "python3" is available
    When I run "python3 -m py_compile scripts/cli/__main__.py"
    Then exit code is 0

  @requires.script_imports
  Scenario: CLI helpers compile
    Given "python3" is available
    When I run "python3 -m py_compile scripts/cli/_helpers.py"
    Then exit code is 0
