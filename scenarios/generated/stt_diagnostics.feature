Feature: STT service diagnostics
  As an admin managing Speaches/Whisper
  I want CLI commands to diagnose and restart STT
  So that I can quickly resolve CUDA/VRAM issues

  Background:
    Given a clean sandbox environment

  Scenario: STT diagnostic script exists and is executable
    Given the file "scripts/stt-diag.sh" exists
    Then it is executable

  Scenario: STT script uses bash with strict mode
    When I run "head -5 scripts/stt-diag.sh"
    Then exit code is 0
    And output contains "set -euo pipefail"

  Scenario: CLI stt group is registered
    When I run "python3 -m scripts.cli --help"
    Then exit code is 0
    And output contains "stt"

  Scenario: CLI stt status command exists
    When I run "python3 -m scripts.cli stt --help"
    Then exit code is 0
    And output contains "status"

  Scenario: CLI stt restart command exists
    When I run "python3 -m scripts.cli stt --help"
    Then exit code is 0
    And output contains "restart"

  Scenario: CLI stt logs command exists
    When I run "python3 -m scripts.cli stt --help"
    Then exit code is 0
    And output contains "logs"

  Scenario: CLI stt test command exists
    When I run "python3 -m scripts.cli stt --help"
    Then exit code is 0
    And output contains "test"

  Scenario: CLI stt logs has lines option
    When I run "python3 -m scripts.cli stt logs --help"
    Then exit code is 0
    And output contains "--lines"
