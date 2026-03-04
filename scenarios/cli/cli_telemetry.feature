Feature: CLI telemetry — local-only usage analytics lifecycle
  Telemetry is opt-in and local-only. Data is stored in
  ~/.anklume/telemetry/ and never leaves the machine. These
  scenarios test the full telemetry lifecycle: enable, log,
  report, disable, clear.

  # ── Help and discoverability ───────────────────────────────

  @requires.cli_help
  Scenario: Telemetry --help shows all 5 user commands
    Given "python3" is available
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli telemetry --help"
    Then exit code is 0
    And output contains "on"
    And output contains "off"
    And output contains "status"
    And output contains "clear"
    And output contains "report"

  # ── Backend script direct invocation ───────────────────────

  @gate.telemetry_backend
  Scenario: Telemetry backend script runs status without error
    Given "python3" is available
    When I run "python3 scripts/telemetry.py status"
    Then exit code is 0
    And output contains "Telemetry:"

  @requires.telemetry_backend
  Scenario: Telemetry backend script has valid syntax
    Given "python3" is available
    When I run "python3 -m py_compile scripts/telemetry.py"
    Then exit code is 0

  # ── Enable/disable lifecycle ───────────────────────────────

  @requires.telemetry_backend
  Scenario: Telemetry enable creates state file
    Given "python3" is available
    And telemetry state is clean
    When I run "python3 scripts/telemetry.py on"
    Then exit code is 0
    And output contains "enabled"
    And telemetry enabled file exists

  @requires.telemetry_backend
  Scenario: Telemetry status shows enabled after enable
    Given "python3" is available
    And telemetry state is clean
    When I run "python3 scripts/telemetry.py on"
    And I run "python3 scripts/telemetry.py status"
    Then exit code is 0
    And output contains "enabled"

  @requires.telemetry_backend
  Scenario: Telemetry disable preserves data
    Given "python3" is available
    And telemetry state is clean
    When I run "python3 scripts/telemetry.py on"
    And I run "python3 scripts/telemetry.py off"
    Then exit code is 0
    And output contains "disabled"
    And telemetry enabled file does not exist

  @requires.telemetry_backend
  Scenario: Telemetry status shows disabled after disable
    Given "python3" is available
    And telemetry state is clean
    When I run "python3 scripts/telemetry.py on"
    And I run "python3 scripts/telemetry.py off"
    And I run "python3 scripts/telemetry.py status"
    Then exit code is 0
    And output contains "disabled"

  # ── Logging and reporting ──────────────────────────────────

  @requires.telemetry_backend
  Scenario: Telemetry logs events when enabled
    Given "python3" is available
    And telemetry state is clean
    When I run "python3 scripts/telemetry.py on"
    And I run "python3 scripts/telemetry.py log --target sync --duration 1.5 --exit-code 0"
    Then exit code is 0
    And telemetry usage file has at least 1 event

  @requires.telemetry_backend
  Scenario: Telemetry does not log events when disabled
    Given "python3" is available
    And telemetry state is clean
    When I run "python3 scripts/telemetry.py log --target sync --duration 1.0 --exit-code 0"
    Then exit code is 0
    And telemetry usage file does not exist

  @requires.telemetry_backend
  Scenario: Telemetry report shows data when events exist
    Given "python3" is available
    And telemetry state is clean
    When I run "python3 scripts/telemetry.py on"
    And I run "python3 scripts/telemetry.py log --target sync --duration 2.0 --exit-code 0"
    And I run "python3 scripts/telemetry.py log --target apply --duration 5.0 --exit-code 1"
    And I run "python3 scripts/telemetry.py report"
    Then exit code is 0
    And output contains "Total events: 2"

  @requires.telemetry_backend
  Scenario: Telemetry report with no data shows clean message
    Given "python3" is available
    And telemetry state is clean
    When I run "python3 scripts/telemetry.py report"
    Then exit code is 0
    And output contains "No telemetry data"

  # ── Clear ──────────────────────────────────────────────────

  @requires.telemetry_backend
  Scenario: Telemetry clear removes all data
    Given "python3" is available
    And telemetry state is clean
    When I run "python3 scripts/telemetry.py on"
    And I run "python3 scripts/telemetry.py log --target test --duration 1.0 --exit-code 0"
    And I run "python3 scripts/telemetry.py clear"
    Then exit code is 0
    And output contains "deleted"
    And telemetry usage file does not exist
    And telemetry enabled file does not exist

  @requires.telemetry_backend
  Scenario: Telemetry clear with no data does not crash
    Given "python3" is available
    And telemetry state is clean
    When I run "python3 scripts/telemetry.py clear"
    Then exit code is 0
    And output contains "No telemetry data"

  # ── Event format ───────────────────────────────────────────

  @requires.telemetry_backend
  Scenario: Telemetry events contain required fields
    Given "python3" is available
    And telemetry state is clean
    When I run "python3 scripts/telemetry.py on"
    And I run "python3 scripts/telemetry.py log --target lint --domain pro --duration 3.5 --exit-code 0"
    Then exit code is 0
    And telemetry last event has field "target" with value "lint"
    And telemetry last event has field "domain" with value "pro"
    And telemetry last event has field "exit_code" with value "0"
