Feature: LLM sanitizer dry-run
  As a security-conscious admin
  I want to preview what the sanitizer would redact
  So that I can tune patterns before deployment

  Background:
    Given a clean sandbox environment

  Scenario: Sanitizer module is importable
    When I run "python3 -c 'from scripts.sanitizer_dryrun import load_patterns, apply_patterns, format_diff'"
    Then exit code is 0

  Scenario: Patterns load from Ansible template
    When I run "python3 scripts/sanitizer_dryrun.py --stats"
    Then exit code is 0
    And output contains "ip_addresses"
    And output contains "credentials"
    And output contains "incus_resources"

  Scenario: Sanitizer redacts anklume IPs
    When I run "echo '10.120.1.5' | python3 scripts/sanitizer_dryrun.py"
    Then exit code is 0
    And output contains "redaction"
    And output contains "ip_addresses"

  Scenario: Sanitizer passes clean text
    When I run "echo 'Hello world' | python3 scripts/sanitizer_dryrun.py"
    Then exit code is 0
    And output contains "No redactions"

  Scenario: JSON output mode works
    When I run "echo '10.120.1.5' | python3 scripts/sanitizer_dryrun.py --json"
    Then exit code is 0
    And output contains "sanitized"
    And output contains "redactions"

  Scenario: CLI sanitize command exists
    When I run "python3 -m scripts.cli llm --help"
    Then exit code is 0
    And output contains "sanitize"

  Scenario: CLI patterns command exists
    When I run "python3 -m scripts.cli llm --help"
    Then exit code is 0
    And output contains "patterns"

  Scenario: CLI sanitize help text
    When I run "python3 -m scripts.cli llm sanitize --help"
    Then exit code is 0
    And output contains "Dry-run"

  Scenario: CLI patterns help text
    When I run "python3 -m scripts.cli llm patterns --help"
    Then exit code is 0
    And output contains "List sanitization"
