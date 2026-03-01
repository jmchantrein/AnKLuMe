Feature: Guide chapter content
  Each chapter explains, demonstrates, and invites interaction.

  Scenario: Chapter 1 shows domain isolation
    Given "bash" is available
    And "incus" is available
    And Incus daemon is available
    When I run "env GUIDE_AUTO=true bash scripts/guide/ch01-isolation.sh" and it may fail
    Then output contains "incus list"

  Scenario: Chapter 2 mentions tmux console
    Given "bash" is available
    And "incus" is available
    And Incus daemon is available
    When I run "env GUIDE_AUTO=true bash scripts/guide/ch02-console.sh" and it may fail
    Then output contains "console"

  Scenario: Chapter 5 mentions nftables
    Given "bash" is available
    And "incus" is available
    And Incus daemon is available
    When I run "env GUIDE_AUTO=true bash scripts/guide/ch05-network.sh" and it may fail
    Then output contains "nftables"

  Scenario: Chapter 6 mentions snapshots
    Given "bash" is available
    And "incus" is available
    And Incus daemon is available
    When I run "env GUIDE_AUTO=true bash scripts/guide/ch06-snapshots.sh" and it may fail
    Then output contains "snapshot"

  Scenario: Chapter metadata is valid Python
    Given "python3" is available
    When I run "python3 -c 'from scripts.guide_chapters import CHAPTERS; assert len(CHAPTERS) == 8'"
    Then exit code is 0

  Scenario: Chapter strings are valid Python
    Given "python3" is available
    When I run "python3 -c 'from scripts.guide_strings import STRINGS; assert len(STRINGS) == 2'"
    Then exit code is 0
