Feature: Guide prerequisite checks
  The interactive guide requires all anklume prerequisites.

  Scenario: Guide detects missing Incus
    Given "bash" is available
    When I run "env PATH=/dev/null bash scripts/guide.sh --auto" and it may fail
    Then exit code is non-zero

  Scenario: Guide setup detects missing Incus
    Given "bash" is available
    When I run "env PATH=/dev/null bash scripts/guide-setup.sh --auto" and it may fail
    Then exit code is non-zero

  Scenario: Guide skips GPU chapter when no GPU
    Given "bash" is available
    And "incus" is available
    And Incus daemon is available
    When I run "env GUIDE_AUTO=true bash scripts/guide/ch08-ai.sh" and it may fail
    Then output contains "GPU"

  Scenario: Welcome script imports cleanly without full CLI
    Given "python3" is available
    When I run "cd scripts && python3 -c 'import welcome'"
    Then exit code is 0

  Scenario: Guide skips GUI chapter without Wayland
    Given "bash" is available
    And "incus" is available
    And Incus daemon is available
    When I run "env GUIDE_AUTO=true WAYLAND_DISPLAY= bash scripts/guide/ch03-gui-apps.sh" and it may fail
    Then output contains "Wayland"

  # ── Non-interactive mode ───────────────────────────────────

  @requires.guide_help
  Scenario: guide.sh --help shows usage
    Given "bash" is available
    When I run "bash scripts/guide.sh --help"
    Then exit code is 0
    And output contains "Usage"

  @requires.guide_lib
  Scenario: guide-lib.sh is sourceable without side effects
    Given "bash" is available
    When I run "bash -c 'source scripts/guide-lib.sh && echo GUIDE_LIB_OK'"
    Then exit code is 0
    And output contains "GUIDE_LIB_OK"

  @requires.guide_lib
  Scenario: guide-lib.sh exports GUIDE_TOTAL_CHAPTERS
    Given "bash" is available
    When I run "bash -c 'source scripts/guide-lib.sh && echo $GUIDE_TOTAL_CHAPTERS'"
    Then exit code is 0
    And output contains "8"

  @requires.guide_help
  Scenario: guide.sh --auto mode exits without hanging
    Given "bash" is available
    And "incus" is available
    And Incus daemon is available
    When I run "timeout 30 bash scripts/guide.sh --auto" and it may fail
    Then the command completed within 30 seconds
