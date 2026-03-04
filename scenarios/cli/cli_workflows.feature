Feature: CLI workflows — multi-command integration chains
  End-to-end workflow scenarios testing sequences of commands
  that form natural usage patterns. Each workflow verifies that
  commands compose correctly in their expected order.

  Background:
    Given "python3" is available

  # ══════════════════════════════════════════════════════════════
  # Workflow: mode switching changes help visibility
  # ══════════════════════════════════════════════════════════════

  @requires.cli_help
  Scenario: mode switch from user to dev reveals dev group
    When I run "ANKLUME_MODE=user python3 -m scripts.cli --help" and it may fail
    Then output does not contain "telemetry"
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli --help" and it may fail
    Then output contains "telemetry"

  @requires.cli_help
  Scenario: mode switch from dev to student hides standard groups
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli --help" and it may fail
    Then output contains "instance"
    When I run "ANKLUME_MODE=student python3 -m scripts.cli --help" and it may fail
    Then output does not contain "telemetry"

  @requires.cli_help
  Scenario: mode user --help then mode dev --help both work
    When I run "python3 -m scripts.cli mode user --help"
    Then exit code is 0
    When I run "python3 -m scripts.cli mode dev --help"
    Then exit code is 0

  # ══════════════════════════════════════════════════════════════
  # Workflow: dev lint → dev test → dev scenario
  # ══════════════════════════════════════════════════════════════

  @requires.cli_help
  Scenario: dev lint --help → dev test --help → dev scenario --help chain
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli dev lint --help"
    Then exit code is 0
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli dev test --help"
    Then exit code is 0
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli dev scenario --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: dev lint filter options are consistent
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli dev lint --help"
    Then exit code is 0
    And output contains "--yaml"
    And output contains "--ansible"
    And output contains "--shell"
    And output contains "--python"

  @requires.cli_help
  Scenario: dev test filter options are consistent
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli dev test --help"
    Then exit code is 0
    And output contains "--generator"

  @requires.cli_help
  Scenario: dev scenario filter options are consistent
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli dev scenario --help"
    Then exit code is 0
    And output contains "--best"
    And output contains "--bad"

  # ══════════════════════════════════════════════════════════════
  # Workflow: sync → domain check (dry-run safety)
  # ══════════════════════════════════════════════════════════════

  @requires.cli_help
  Scenario: sync --help → domain check --help chain
    When I run "python3 -m scripts.cli sync --help"
    Then exit code is 0
    And output contains "dry-run"
    When I run "python3 -m scripts.cli domain check --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: sync and domain apply are distinct commands
    When I run "python3 -m scripts.cli sync --help"
    Then exit code is 0
    When I run "python3 -m scripts.cli domain apply --help"
    Then exit code is 0

  # ══════════════════════════════════════════════════════════════
  # Workflow: snapshot lifecycle (create → list → restore → delete)
  # ══════════════════════════════════════════════════════════════

  @requires.cli_help
  Scenario: snapshot lifecycle help chain
    When I run "python3 -m scripts.cli snapshot create --help"
    Then exit code is 0
    When I run "python3 -m scripts.cli snapshot list --help"
    Then exit code is 0
    When I run "python3 -m scripts.cli snapshot restore --help"
    Then exit code is 0
    When I run "python3 -m scripts.cli snapshot delete --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: snapshot rollback help is accessible
    When I run "python3 -m scripts.cli snapshot rollback --help"
    Then exit code is 0
    And output contains "--list"
    And output contains "--cleanup"

  # ══════════════════════════════════════════════════════════════
  # Workflow: doctor → fix → re-check
  # ══════════════════════════════════════════════════════════════

  @requires.cli_help
  Scenario: doctor --help → doctor --check deps chain
    When I run "python3 -m scripts.cli doctor --help"
    Then exit code is 0
    When I run "timeout 30 bash scripts/doctor.sh --check deps" and it may fail
    Then the command completed within 30 seconds

  @requires.cli_help
  Scenario: doctor categories can be checked independently
    When I run "timeout 30 bash scripts/doctor.sh --check config" and it may fail
    Then the command completed within 30 seconds
    When I run "timeout 30 bash scripts/doctor.sh --check deps" and it may fail
    Then the command completed within 30 seconds

  # ══════════════════════════════════════════════════════════════
  # Workflow: setup init (help chain)
  # ══════════════════════════════════════════════════════════════

  @requires.cli_help
  Scenario: setup init → setup shares → setup data-dirs help chain
    When I run "python3 -m scripts.cli setup init --help"
    Then exit code is 0
    When I run "python3 -m scripts.cli setup shares --help"
    Then exit code is 0
    When I run "python3 -m scripts.cli setup data-dirs --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: setup quickstart --help is accessible
    When I run "python3 -m scripts.cli setup quickstart --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: setup production --help is accessible
    When I run "python3 -m scripts.cli setup production --help"
    Then exit code is 0

  # ══════════════════════════════════════════════════════════════
  # Workflow: lab lifecycle (list → start → check → hint → reset)
  # ══════════════════════════════════════════════════════════════

  @requires.cli_help
  Scenario: lab lifecycle help chain
    When I run "python3 -m scripts.cli lab list --help"
    Then exit code is 0
    When I run "python3 -m scripts.cli lab start --help"
    Then exit code is 0
    When I run "python3 -m scripts.cli lab check --help"
    Then exit code is 0
    When I run "python3 -m scripts.cli lab hint --help"
    Then exit code is 0
    When I run "python3 -m scripts.cli lab reset --help"
    Then exit code is 0
    When I run "python3 -m scripts.cli lab solution --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: lab list does not crash without labs
    When I run "python3 -m scripts.cli lab list" and it may fail
    Then the command completed within 30 seconds

  # ══════════════════════════════════════════════════════════════
  # Workflow: learn lifecycle
  # ══════════════════════════════════════════════════════════════

  @requires.cli_help
  Scenario: learn lifecycle help chain
    When I run "python3 -m scripts.cli learn setup --help"
    Then exit code is 0
    When I run "python3 -m scripts.cli learn start --help"
    Then exit code is 0
    When I run "python3 -m scripts.cli learn teardown --help"
    Then exit code is 0

  # ══════════════════════════════════════════════════════════════
  # Workflow: instance management
  # ══════════════════════════════════════════════════════════════

  @requires.cli_help
  Scenario: instance list → instance info help chain
    When I run "python3 -m scripts.cli instance list --help"
    Then exit code is 0
    When I run "python3 -m scripts.cli instance info --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: instance list does not crash
    When I run "python3 -m scripts.cli instance list" and it may fail
    Then the command completed within 30 seconds

  # ══════════════════════════════════════════════════════════════
  # Workflow: network management
  # ══════════════════════════════════════════════════════════════

  @requires.cli_help
  Scenario: network status → network rules help chain
    When I run "python3 -m scripts.cli network status --help"
    Then exit code is 0
    When I run "python3 -m scripts.cli network rules --help"
    Then exit code is 0
    When I run "python3 -m scripts.cli network deploy --help"
    Then exit code is 0

  # ══════════════════════════════════════════════════════════════
  # Workflow: llm management
  # ══════════════════════════════════════════════════════════════

  @requires.cli_help
  Scenario: llm status → llm switch help chain
    When I run "python3 -m scripts.cli llm status --help"
    Then exit code is 0
    When I run "python3 -m scripts.cli llm switch --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: llm sanitize → llm patterns help chain
    When I run "python3 -m scripts.cli llm sanitize --help"
    Then exit code is 0
    When I run "python3 -m scripts.cli llm patterns --help"
    Then exit code is 0

  # ══════════════════════════════════════════════════════════════
  # Workflow: portal file transfer
  # ══════════════════════════════════════════════════════════════

  @requires.cli_help
  Scenario: portal push → portal pull help chain
    When I run "python3 -m scripts.cli portal push --help"
    Then exit code is 0
    When I run "python3 -m scripts.cli portal pull --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: portal list → portal copy help chain
    When I run "python3 -m scripts.cli portal list --help"
    Then exit code is 0
    When I run "python3 -m scripts.cli portal copy --help"
    Then exit code is 0

  # ══════════════════════════════════════════════════════════════
  # Workflow: live ISO management (dev mode)
  # ══════════════════════════════════════════════════════════════

  @requires.cli_help
  Scenario: live build → live test → live status help chain
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli live build --help"
    Then exit code is 0
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli live test --help"
    Then exit code is 0
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli live status --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: live mount → live umount help chain
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli live mount --help"
    Then exit code is 0
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli live umount --help"
    Then exit code is 0

  # ══════════════════════════════════════════════════════════════
  # Workflow: ai tools
  # ══════════════════════════════════════════════════════════════

  @requires.cli_help
  Scenario: ai switch → ai test help chain
    When I run "python3 -m scripts.cli ai switch --help"
    Then exit code is 0
    When I run "python3 -m scripts.cli ai test --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: ai agent-setup → ai agent-fix → ai agent-develop help chain
    When I run "python3 -m scripts.cli ai agent-setup --help"
    Then exit code is 0
    When I run "python3 -m scripts.cli ai agent-fix --help"
    Then exit code is 0
    When I run "python3 -m scripts.cli ai agent-develop --help"
    Then exit code is 0

  # ══════════════════════════════════════════════════════════════
  # Workflow: golden image lifecycle (dev mode)
  # ══════════════════════════════════════════════════════════════

  @requires.cli_help
  Scenario: golden create → golden list → golden publish help chain
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli golden create --help"
    Then exit code is 0
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli golden list --help"
    Then exit code is 0
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli golden publish --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: golden derive --help exits 0
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli golden derive --help"
    Then exit code is 0

  # ══════════════════════════════════════════════════════════════
  # Workflow: telemetry lifecycle (dev mode)
  # ══════════════════════════════════════════════════════════════

  @requires.cli_help
  Scenario: telemetry on → telemetry status → telemetry off help chain
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli telemetry on --help"
    Then exit code is 0
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli telemetry status --help"
    Then exit code is 0
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli telemetry off --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: telemetry clear → telemetry report help chain
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli telemetry clear --help"
    Then exit code is 0
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli telemetry report --help"
    Then exit code is 0

  # ══════════════════════════════════════════════════════════════
  # Workflow: desktop management
  # ══════════════════════════════════════════════════════════════

  @requires.cli_help
  Scenario: desktop apply → desktop reset help chain
    When I run "python3 -m scripts.cli desktop apply --help"
    Then exit code is 0
    When I run "python3 -m scripts.cli desktop reset --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: desktop plugins → desktop config help chain
    When I run "python3 -m scripts.cli desktop plugins --help"
    Then exit code is 0
    When I run "python3 -m scripts.cli desktop config --help"
    Then exit code is 0
