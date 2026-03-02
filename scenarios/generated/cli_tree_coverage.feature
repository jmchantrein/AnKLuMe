Feature: CLI tree exhaustive coverage
  As a developer maintaining the anklume CLI
  I want every command group and subcommand to be reachable
  So that users always get working --help output

  Background:
    Given a clean sandbox environment

  # ── Top-level commands ──────────────────────────────────────

  Scenario: Root help shows all groups
    When I run "python3 -m scripts.cli --help"
    Then exit code is 0
    And output contains "domain"
    And output contains "instance"
    And output contains "stt"
    And output contains "system"
    And output contains "llm"

  Scenario: Version flag works
    When I run "python3 -m scripts.cli --version"
    Then exit code is 0
    And output contains "anklume"

  # ── domain group ────────────────────────────────────────────

  Scenario: domain help lists subcommands
    When I run "python3 -m scripts.cli domain --help"
    Then exit code is 0
    And output contains "list"
    And output contains "apply"
    And output contains "check"

  Scenario: domain list help works
    When I run "python3 -m scripts.cli domain list --help"
    Then exit code is 0

  Scenario: domain apply help works
    When I run "python3 -m scripts.cli domain apply --help"
    Then exit code is 0

  Scenario: domain check help works
    When I run "python3 -m scripts.cli domain check --help"
    Then exit code is 0

  Scenario: domain exec help works
    When I run "python3 -m scripts.cli domain exec --help"
    Then exit code is 0

  Scenario: domain status help works
    When I run "python3 -m scripts.cli domain status --help"
    Then exit code is 0

  # ── instance group ──────────────────────────────────────────

  Scenario: instance help lists subcommands
    When I run "python3 -m scripts.cli instance --help"
    Then exit code is 0
    And output contains "list"
    And output contains "remove"
    And output contains "exec"

  Scenario: instance list help works
    When I run "python3 -m scripts.cli instance list --help"
    Then exit code is 0

  Scenario: instance remove help works
    When I run "python3 -m scripts.cli instance remove --help"
    Then exit code is 0

  Scenario: instance info help works
    When I run "python3 -m scripts.cli instance info --help"
    Then exit code is 0

  # ── snapshot group ──────────────────────────────────────────

  Scenario: snapshot help lists subcommands
    When I run "python3 -m scripts.cli snapshot --help"
    Then exit code is 0
    And output contains "create"
    And output contains "restore"
    And output contains "delete"

  Scenario: snapshot create help works
    When I run "python3 -m scripts.cli snapshot create --help"
    Then exit code is 0

  Scenario: snapshot restore help works
    When I run "python3 -m scripts.cli snapshot restore --help"
    Then exit code is 0

  # ── network group ───────────────────────────────────────────

  Scenario: network help lists subcommands
    When I run "python3 -m scripts.cli network --help"
    Then exit code is 0
    And output contains "rules"
    And output contains "deploy"
    And output contains "status"

  Scenario: network rules help works
    When I run "python3 -m scripts.cli network rules --help"
    Then exit code is 0

  Scenario: network deploy help works
    When I run "python3 -m scripts.cli network deploy --help"
    Then exit code is 0

  # ── lab group ───────────────────────────────────────────────

  Scenario: lab help lists subcommands
    When I run "python3 -m scripts.cli lab --help"
    Then exit code is 0
    And output contains "list"
    And output contains "start"
    And output contains "check"

  Scenario: lab list help works
    When I run "python3 -m scripts.cli lab list --help"
    Then exit code is 0

  Scenario: lab start help works
    When I run "python3 -m scripts.cli lab start --help"
    Then exit code is 0

  # ── setup group ─────────────────────────────────────────────

  Scenario: setup help lists subcommands
    When I run "python3 -m scripts.cli setup --help"
    Then exit code is 0
    And output contains "init"
    And output contains "hooks"
    And output contains "production"

  Scenario: setup init help works
    When I run "python3 -m scripts.cli setup init --help"
    Then exit code is 0

  Scenario: setup production help works
    When I run "python3 -m scripts.cli setup production --help"
    Then exit code is 0

  # ── ai group ────────────────────────────────────────────────

  Scenario: ai help lists subcommands
    When I run "python3 -m scripts.cli ai --help"
    Then exit code is 0
    And output contains "switch"
    And output contains "claude"

  Scenario: ai switch help works
    When I run "python3 -m scripts.cli ai switch --help"
    Then exit code is 0

  # ── backup group ────────────────────────────────────────────

  Scenario: backup help lists subcommands
    When I run "python3 -m scripts.cli backup --help"
    Then exit code is 0
    And output contains "create"
    And output contains "restore"

  # ── portal group ────────────────────────────────────────────

  Scenario: portal help lists subcommands
    When I run "python3 -m scripts.cli portal --help"
    Then exit code is 0
    And output contains "push"
    And output contains "pull"

  # ── app group ───────────────────────────────────────────────

  Scenario: app help lists subcommands
    When I run "python3 -m scripts.cli app --help"
    Then exit code is 0
    And output contains "export"
    And output contains "list"

  # ── desktop group ───────────────────────────────────────────

  Scenario: desktop help lists subcommands
    When I run "python3 -m scripts.cli desktop --help"
    Then exit code is 0
    And output contains "apply"
    And output contains "reset"

  # ── docs group ──────────────────────────────────────────────

  Scenario: docs help lists subcommands
    When I run "python3 -m scripts.cli docs --help"
    Then exit code is 0
    And output contains "build"
    And output contains "serve"

  # ── mode group ──────────────────────────────────────────────

  Scenario: mode help lists subcommands
    When I run "python3 -m scripts.cli mode --help"
    Then exit code is 0
    And output contains "user"
    And output contains "student"
    And output contains "dev"

  # ── learn group ─────────────────────────────────────────────

  Scenario: learn help lists subcommands
    When I run "python3 -m scripts.cli learn --help"
    Then exit code is 0
    And output contains "start"
    And output contains "setup"
    And output contains "teardown"

  # ── dev group ───────────────────────────────────────────────

  Scenario: dev help lists subcommands
    When I run "python3 -m scripts.cli dev --help"
    Then exit code is 0
    And output contains "test"
    And output contains "lint"
    And output contains "scenario"

  Scenario: dev test help works
    When I run "python3 -m scripts.cli dev test --help"
    Then exit code is 0

  Scenario: dev lint help works
    When I run "python3 -m scripts.cli dev lint --help"
    Then exit code is 0
