Feature: Host resource monitoring
  As an admin monitoring anklume infrastructure
  I want a unified view of CPU, RAM, disk, GPU/VRAM, and LLM models
  So that I can identify resource bottlenecks

  Background:
    Given a clean sandbox environment

  Scenario: Resource module is importable
    When I run "python3 -c 'from scripts.host_resources import collect_all, render_cli, render_tmux'"
    Then exit code is 0

  Scenario: CLI system group is registered
    When I run "python3 -m scripts.cli --help"
    Then exit code is 0
    And output contains "system"

  Scenario: CLI system resources command exists
    When I run "python3 -m scripts.cli system --help"
    Then exit code is 0
    And output contains "resources"

  Scenario: Resources command has output option
    When I run "python3 -m scripts.cli system resources --help"
    Then exit code is 0
    And output contains "--output"

  Scenario: Resources command has watch option
    When I run "python3 -m scripts.cli system resources --help"
    Then exit code is 0
    And output contains "--watch"

  Scenario: Resources command has json option
    When I run "python3 -m scripts.cli system resources --help"
    Then exit code is 0
    And output contains "--json"

  Scenario: Tmux output mode works
    When I run "python3 scripts/host_resources.py --tmux"
    Then exit code is 0
    And output contains "CPU:"
    And output contains "RAM:"

  Scenario: JSON output mode works
    When I run "python3 scripts/host_resources.py --json"
    Then exit code is 0
    And output contains "cpu_percent"
    And output contains "memory"

  Scenario: HTML output mode works
    When I run "python3 scripts/host_resources.py --html"
    Then exit code is 0
    And output contains "resource-widget"

  Scenario: Dashboard CSS includes resource styles
    When I run "python3 -c 'from scripts.web.theme import RESOURCE_CSS; print(RESOURCE_CSS)'"
    Then exit code is 0
    And output contains "resource-widget"
    And output contains "resource-bar"
