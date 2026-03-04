Feature: CLI bootstrap — verify the anklume CLI starts correctly
  The CLI is the primary user interface for anklume. Every subcommand
  group must be registered and accessible. Unknown commands must fail
  cleanly instead of crashing.

  # ── Gate: CLI is functional ─────────────────────────────────

  @gate.cli_help
  Scenario: CLI --help shows help text
    Given "python3" is available
    When I run "python3 -m scripts.cli --help"
    Then exit code is 0
    And output contains "Declarative infrastructure compartmentalization framework"

  @gate.cli_help
  Scenario: CLI --version shows version
    Given "python3" is available
    When I run "python3 -m scripts.cli --version"
    Then exit code is 0
    And output contains "anklume"

  # ── Subcommand group registration ──────────────────────────

  @requires.cli_help
  Scenario: CLI registers domain group
    Given "python3" is available
    When I run "python3 -m scripts.cli domain --help"
    Then exit code is 0
    And output contains "domain"

  @requires.cli_help
  Scenario: CLI registers instance group
    Given "python3" is available
    When I run "python3 -m scripts.cli instance --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: CLI registers snapshot group
    Given "python3" is available
    When I run "python3 -m scripts.cli snapshot --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: CLI registers network group
    Given "python3" is available
    When I run "python3 -m scripts.cli network --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: CLI registers setup group
    Given "python3" is available
    When I run "python3 -m scripts.cli setup --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: CLI registers lab group
    Given "python3" is available
    When I run "python3 -m scripts.cli lab --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: CLI registers learn group
    Given "python3" is available
    When I run "python3 -m scripts.cli learn --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: CLI registers mode group
    Given "python3" is available
    When I run "python3 -m scripts.cli mode --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: CLI registers ai group
    Given "python3" is available
    When I run "python3 -m scripts.cli ai --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: CLI registers llm group
    Given "python3" is available
    When I run "python3 -m scripts.cli llm --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: CLI registers dev group (dev mode)
    Given "python3" is available
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli dev --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: CLI registers telemetry group (dev mode)
    Given "python3" is available
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli telemetry --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: CLI registers backup group
    Given "python3" is available
    When I run "python3 -m scripts.cli backup --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: CLI registers portal group
    Given "python3" is available
    When I run "python3 -m scripts.cli portal --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: CLI registers desktop group
    Given "python3" is available
    When I run "python3 -m scripts.cli desktop --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: CLI registers live group (dev mode)
    Given "python3" is available
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli live --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: CLI registers golden group (dev mode)
    Given "python3" is available
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli golden --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: CLI registers mcp group (dev mode)
    Given "python3" is available
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli mcp --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: CLI registers system group
    Given "python3" is available
    When I run "python3 -m scripts.cli system --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: CLI registers stt group
    Given "python3" is available
    When I run "python3 -m scripts.cli stt --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: CLI registers appexport group
    Given "python3" is available
    When I run "python3 -m scripts.cli app --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: CLI registers docs group
    Given "python3" is available
    When I run "python3 -m scripts.cli docs --help"
    Then exit code is 0

  # ── Error handling ─────────────────────────────────────────

  @requires.cli_help
  Scenario: CLI exits cleanly with unknown command
    Given "python3" is available
    When I run "python3 -m scripts.cli nonexistent-command" and it may fail
    Then exit code is non-zero

  @requires.cli_help
  Scenario: CLI with no arguments shows help
    Given "python3" is available
    When I run "python3 -m scripts.cli" and it may fail
    Then output contains "Usage"
