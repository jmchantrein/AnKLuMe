Feature: CLI dependency chain
  Commands must be run in prerequisite order. The resource flow
  model (_cli_deps.yml) defines which commands produce and consume
  each resource. Running a consumer before its producer fails.

  Background:
    Given a clean sandbox environment

  Scenario: sync before apply
    Given infra.yml from "student-sysadmin"
    When I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0
    And inventory files exist for all domains

  Scenario: Lint passes after sync
    Given "yamllint" is available
    And infra.yml from "student-sysadmin"
    When I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0
    When I run "yamllint -c .yamllint.yml inventory/ group_vars/ host_vars/" and it may fail
    Then exit code is 0

  Scenario: Full bootstrap chain with pro-workstation
    Given infra.yml from "pro-workstation"
    When I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0
    And inventory files exist for all domains
    And generated host_vars contain valid IPs

  Scenario: Full bootstrap chain with ai-tools
    Given infra.yml from "ai-tools"
    When I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0
    And inventory files exist for all domains
    And generated host_vars contain valid IPs

  Scenario: Full bootstrap chain with tor-gateway
    Given infra.yml from "tor-gateway"
    When I run "python3 scripts/generate.py infra.yml"
    Then exit code is 0
    And inventory files exist for all domains

  Scenario: Dependency graph generation
    When I run "python3 -m scripts.cli dev cli-tree --format deps" and it may fail
    Then exit code is 0
    And output contains "graph"

  Scenario: CLI tree introspection
    When I run "python3 -m scripts.cli dev cli-tree --format json" and it may fail
    Then exit code is 0
