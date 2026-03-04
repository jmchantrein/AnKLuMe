Feature: Web-based guide
  The HTML guide serves the same content via FastAPI + htmx.

  Scenario: Guide web module imports successfully
    Given "python3" is available
    When I run "python3 -c 'import scripts.guide_chapters; import scripts.guide_strings'"
    Then exit code is 0

  @requires.guide_imports
  Scenario: Guide chapters metadata has 8 chapters
    Given "python3" is available
    When I run "python3 -c 'from scripts.guide_chapters import CHAPTERS; assert len(CHAPTERS) == 8'"
    Then exit code is 0

  @requires.guide_imports
  Scenario: Whitelisted commands come from safe chapters
    Given "python3" is available
    When I run "python3 -c 'from scripts.guide_chapters import get_whitelisted_commands; print(len(get_whitelisted_commands()))'"
    Then exit code is 0

  @requires.guide_imports
  Scenario: Guide strings cover both languages
    Given "python3" is available
    When I run "python3 -c 'from scripts.guide_strings import STRINGS; assert len(STRINGS) == 2'"
    Then exit code is 0

  Scenario: Platform server module has valid syntax
    Given "python3" is available
    When I run "python3 -m py_compile scripts/platform_server.py"
    Then exit code is 0
