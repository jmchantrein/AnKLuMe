Feature: LLM sanitizer — dry-run pattern matching
  Verify that the sanitization engine correctly detects and redacts
  infrastructure-specific data (IPs, hostnames, credentials).

  Scenario: sanitizer module is importable
    Given "python3" is available
    When I run "python3 -c 'from scripts.sanitizer_dryrun import load_patterns, apply_patterns'"
    Then exit code is 0

  Scenario: sanitizer loads at least 10 patterns
    Given "python3" is available
    When I run "python3 -c 'from scripts.sanitizer_dryrun import load_patterns; p=load_patterns(); assert len(p) > 10'"
    Then exit code is 0

  Scenario: sanitizer detects anklume IP addresses
    Given "python3" is available
    When I run "python3 -c 'from scripts.sanitizer_dryrun import apply_patterns,load_patterns; ip=chr(49)+chr(48)+chr(46)+chr(49)+chr(50)+chr(48)+chr(46)+chr(48)+chr(46)+chr(53); s,r=apply_patterns(ip,load_patterns()); assert len(r)>0'"
    Then exit code is 0

  @requires.cli_help
  Scenario: llm patterns command lists patterns
    Given "python3" is available
    When I run "python3 -m scripts.cli llm patterns"
    Then exit code is 0
    And output contains "patterns"

  @requires.cli_help
  Scenario: llm sanitize --help documents --text
    Given "python3" is available
    When I run "python3 -m scripts.cli llm sanitize --help"
    Then exit code is 0
    And output contains "--text"

  @requires.cli_help
  Scenario: llm sanitize --help documents --json
    Given "python3" is available
    When I run "python3 -m scripts.cli llm sanitize --help"
    Then exit code is 0
    And output contains "--json"

  @requires.cli_help
  Scenario: llm sanitize --help documents --file
    Given "python3" is available
    When I run "python3 -m scripts.cli llm sanitize --help"
    Then exit code is 0
    And output contains "--file"
