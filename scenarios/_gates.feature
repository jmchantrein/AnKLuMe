Feature: Gate scenarios — critical prerequisites for dependent features
  These scenarios run first (underscore sorts before all letters) and
  register gate results used by @requires tags across the test suite.
  If a gate fails here, all @requires.GATE_NAME scenarios are skipped
  automatically instead of failing with confusing import errors.

  # ── PSOT Generator ─────────────────────────────────────

  @gate.generator
  Scenario: Generator imports and produces files
    Given "python3" is available
    And a clean sandbox environment
    And infra.yml from "student-sysadmin"
    When I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0

  # ── Web modules ────────────────────────────────────────

  @gate.web_factory
  Scenario: Web factory module imports
    Given "python3" is available
    When I run "python3 -c 'from scripts.web import create_app; create_app()'"
    Then exit code is 0

  @gate.web_html
  Scenario: HTML helpers module imports
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.html import page_wrap; assert len(page_wrap(chr(84), chr(66))) > 50'"
    Then exit code is 0

  @gate.web_theme
  Scenario: Web theme module imports
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.theme import BASE_CSS; assert len(BASE_CSS) > 50'"
    Then exit code is 0

  # ── Guide modules ──────────────────────────────────────

  @gate.guide_imports
  Scenario: Guide chapters and strings import
    Given "python3" is available
    When I run "python3 -c 'import scripts.guide_chapters; import scripts.guide_strings'"
    Then exit code is 0

  # ── Learn modules ──────────────────────────────────────

  @gate.learn_cli
  Scenario: Learn CLI module compiles
    Given "python3" is available
    When I run "python3 -m py_compile scripts/cli/learn.py"
    Then exit code is 0

@gate.content_model
  Scenario: Content model imports and guide loads
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.content import load_guide_sections, load_lab; s = load_guide_sections(); assert len(s) == 1 and len(s[0].pages) == 8'"
    Then exit code is 0

  @gate.platform_server
  Scenario: Platform server imports and creates app
    Given "python3" is available
    When I run "python3 -c 'from starlette.testclient import TestClient; from scripts.platform_server import app; r = TestClient(app).get(chr(47)); assert r.status_code == 200'"
    Then exit code is 0

  # ── Shell scripts ──────────────────────────────────────

  @gate.learn_setup_syntax
  Scenario: learn-setup.sh has valid bash syntax
    Given "bash" is available
    When I run "bash -n scripts/learn-setup.sh"
    Then exit code is 0

  @gate.welcome_import
  Scenario: Welcome script imports cleanly
    Given "python3" is available
    When I run "cd scripts && python3 -c 'import welcome'"
    Then exit code is 0


  # ── Live ISO scripts ─────────────────────────────────────

  @gate.start_syntax
  Scenario: start.sh has valid bash syntax
    Given "bash" is available
    When I run "bash -n scripts/start.sh"
    Then exit code is 0

  @gate.doctor_syntax
  Scenario: doctor.sh has valid bash syntax
    Given "bash" is available
    When I run "bash -n scripts/doctor.sh"
    Then exit code is 0

  # ── CLI mode ─────────────────────────────────────────────

  @gate.cli_mode
  Scenario: Mode subcommand imports
    Given "python3" is available
    When I run "python3 -m scripts.cli mode --help"
    Then exit code is 0
