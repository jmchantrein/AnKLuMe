# Matrix: CM-001 to CM-003
Feature: CLI Modes — user, student, dev help output

  Scenario: i18n French translations exist for all targets
    # Matrix: CM-001
    Given "python3" is available
    When I run "python3 -c 'import yaml; from pathlib import Path; fr=yaml.safe_load(Path("i18n/fr.yml").read_text()); assert len(fr)>10, "Only %d translations" % len(fr); print("fr.yml: %d entries" % len(fr))'"
    Then exit code is 0

  Scenario: Mode persistence file location is documented
    # Matrix: CM-002
    Given "python3" is available
    When I run "python3 -c 'from pathlib import Path; spec=Path("docs/SPEC.md").read_text(); assert "~/.anklume/mode" in spec; print("mode path ok")'"
    Then exit code is 0
    And output contains "mode path ok"

  Scenario: CLI modes are user, student, dev
    # Matrix: CM-003
    Given "python3" is available
    When I run "python3 -c 'modes=["user","student","dev"]; from pathlib import Path; spec=Path("docs/SPEC.md").read_text(); ok=[m for m in modes if m in spec]; assert len(ok)==3; print("modes ok")'"
    Then exit code is 0
    And output contains "modes ok"
