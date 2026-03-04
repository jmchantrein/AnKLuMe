Feature: Live ISO welcome guide — non-interactive context safety
  The welcome guide runs on the Live ISO at setup. It must
  never hang or crash when stdin is closed (non-interactive context
  like systemd services, CI pipelines, or automated testing).

  # ── Syntax and import safety ───────────────────────────────

  @requires.welcome_import
  Scenario: welcome.py passes syntax check
    Given "python3" is available
    When I run "python3 -m py_compile scripts/welcome.py"
    Then exit code is 0

  @requires.welcome_import
  Scenario: welcome_strings has French translations
    Given "python3" is available
    When I run "python3 -c 'from scripts.welcome_strings import STRINGS; k=chr(102)+chr(114); assert k in STRINGS and len(STRINGS[k]) >= 40'"
    Then exit code is 0

  @requires.welcome_import
  Scenario: welcome_strings has English translations
    Given "python3" is available
    When I run "python3 -c 'from scripts.welcome_strings import STRINGS; k=chr(101)+chr(110); assert k in STRINGS and len(STRINGS[k]) >= 40'"
    Then exit code is 0

  @requires.welcome_import
  Scenario: welcome_strings has matching keys in both languages
    Given "python3" is available
    When I run "python3 -c 'from scripts.welcome_strings import STRINGS; assert set(STRINGS[chr(102)+chr(114)]) == set(STRINGS[chr(101)+chr(110)])'"
    Then exit code is 0

  # ── Non-interactive safety ─────────────────────────────────

  @requires.welcome_import
  Scenario: welcome.py with stdin closed exits without hanging
    Given "python3" is available
    When I run "cd scripts && timeout 10 python3 -c 'import os; os.close(0); import welcome' </dev/null" and it may fail
    Then the command completed within 10 seconds

  @requires.welcome_import
  Scenario: welcome.py detect_lang function works without TTY
    Given "python3" is available
    When I run "cd scripts && python3 -c 'import welcome; lang = welcome.detect_lang(); assert lang in (chr(102)+chr(114), chr(101)+chr(110))'"
    Then exit code is 0

  # ── Live OS detection ──────────────────────────────────────

  @requires.welcome_import
  Scenario: is_live_os returns boolean on non-live host
    Given "python3" is available
    When I run "python3 -c 'from scripts.cli._helpers import is_live_os; result = is_live_os(); assert isinstance(result, bool)'"
    Then exit code is 0
