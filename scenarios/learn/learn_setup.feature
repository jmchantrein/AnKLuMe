@requires.learn_setup_syntax
Feature: Learn setup script
  Shell script for creating and destroying the anklume-learn container
  and demo infrastructure in the Incus learn project.

  # ── Syntax and quality ─────────────────────────────────

  Scenario: learn-setup.sh has valid bash syntax
    Given "bash" is available
    When I run "bash -n scripts/learn-setup.sh"
    Then exit code is 0

  Scenario: learn-setup.sh passes shellcheck
    Given "shellcheck" is available
    When I run "shellcheck -S warning scripts/learn-setup.sh"
    Then exit code is 0

  Scenario: learn-setup.sh has shebang
    Given "bash" is available
    When I run "head -1 scripts/learn-setup.sh | grep -q '#!/usr/bin/env bash'"
    Then exit code is 0

  Scenario: learn-setup.sh has set -euo pipefail
    Given "bash" is available
    When I run "grep -q 'set -euo pipefail' scripts/learn-setup.sh"
    Then exit code is 0

  Scenario: learn-setup.sh is under 200 lines
    Given "bash" is available
    When I run "test $(wc -l < scripts/learn-setup.sh) -le 200"
    Then exit code is 0

  # ── Constants ───────────────────────────────────────────

  Scenario: learn-setup.sh defines learn project name
    Given "bash" is available
    When I run "grep -q 'LEARN_PROJECT=\"learn\"' scripts/learn-setup.sh"
    Then exit code is 0

  Scenario: learn-setup.sh uses port 8890
    Given "bash" is available
    When I run "grep -q 'LEARN_PORT=8890' scripts/learn-setup.sh"
    Then exit code is 0

  Scenario: learn-setup.sh uses debian 13 image
    Given "bash" is available
    When I run "grep -q 'IMAGE=\"images:debian/13\"' scripts/learn-setup.sh"
    Then exit code is 0

  # ── Functions ───────────────────────────────────────────

  Scenario: learn-setup.sh has setup and teardown functions
    Given "bash" is available
    When I run "grep -q 'do_setup()' scripts/learn-setup.sh && grep -q 'do_teardown()' scripts/learn-setup.sh"
    Then exit code is 0

  Scenario: learn-setup.sh has check_incus function
    Given "bash" is available
    When I run "grep -q 'check_incus()' scripts/learn-setup.sh"
    Then exit code is 0

  Scenario: learn-setup.sh has project_exists function
    Given "bash" is available
    When I run "grep -q 'project_exists()' scripts/learn-setup.sh"
    Then exit code is 0

  Scenario: learn-setup.sh has container_exists and container_running functions
    Given "bash" is available
    When I run "grep -q 'container_exists()' scripts/learn-setup.sh && grep -q 'container_running()' scripts/learn-setup.sh"
    Then exit code is 0

  # ── Infrastructure ──────────────────────────────────────

  Scenario: learn-setup.sh creates demo instances
    Given "bash" is available
    When I run "grep -q 'learn-web' scripts/learn-setup.sh && grep -q 'learn-db' scripts/learn-setup.sh"
    Then exit code is 0

  Scenario: learn-setup.sh handles teardown via case statement
    Given "bash" is available
    When I run "grep -q 'teardown)' scripts/learn-setup.sh && grep 'setup|' scripts/learn-setup.sh | grep -q '[*]'"
    Then exit code is 0

  Scenario: learn-setup.sh installs FastAPI in container
    Given "bash" is available
    When I run "grep -q 'fastapi' scripts/learn-setup.sh && grep -q 'uvicorn' scripts/learn-setup.sh"
    Then exit code is 0

  Scenario: learn-setup.sh mounts project read-only
    Given "bash" is available
    When I run "grep -q 'readonly=true' scripts/learn-setup.sh && grep -q '/opt/anklume' scripts/learn-setup.sh"
    Then exit code is 0

  Scenario: learn-setup.sh configures TLS on Incus daemon
    Given "bash" is available
    When I run "grep -q 'core.https_address' scripts/learn-setup.sh"
    Then exit code is 0

  Scenario: learn-setup.sh proxies web port
    Given "bash" is available
    When I run "grep -q 'proxy' scripts/learn-setup.sh && grep -q '8890' scripts/learn-setup.sh"
    Then exit code is 0
