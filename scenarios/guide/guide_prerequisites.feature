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

  Scenario: Guide skips GUI chapter without Wayland
    Given "bash" is available
    And "incus" is available
    And Incus daemon is available
    When I run "env GUIDE_AUTO=true WAYLAND_DISPLAY= bash scripts/guide/ch03-gui-apps.sh" and it may fail
    Then output contains "Wayland"
