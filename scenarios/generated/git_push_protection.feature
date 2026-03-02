Feature: Git push production protection
  As a sysadmin deploying anklume in production
  I want git push to be blocked on deployed instances
  So that production infrastructure is not accidentally modified

  Background:
    Given a clean sandbox environment

  Scenario: Pre-push hook exists and is executable
    Given the file "scripts/hooks/pre-push" exists
    Then it is executable

  Scenario: Pre-push hook uses POSIX shell
    Given the file "scripts/hooks/pre-push" exists
    Then the file starts with "#!/bin/sh"

  Scenario: Hook passes without production marker
    When I run "sh scripts/hooks/pre-push" and it may fail
    Then exit code is 0

  Scenario: Makefile install-hooks target installs pre-push
    When I run "grep pre-push Makefile"
    Then exit code is 0
    And output contains "pre-push"

  Scenario: CLI setup production command is registered
    When I run "python3 -m scripts.cli setup --help"
    Then exit code is 0
    And output contains "production"

  Scenario: CLI setup production help text
    When I run "python3 -m scripts.cli setup production --help"
    Then exit code is 0
    And output contains "blocks git push"

  Scenario: Bootstrap --prod writes deployed marker
    When I run "grep '/etc/anklume/deployed' scripts/bootstrap.sh"
    Then exit code is 0
    And output contains "Production marker"
