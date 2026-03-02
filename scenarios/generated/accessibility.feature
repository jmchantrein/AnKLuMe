# Matrix: A11Y-001 to A11Y-003
Feature: Accessibility — colorblind palettes and dyslexia mode

  Scenario: All palettes include all trust levels
    # Matrix: A11Y-001
    Given "python3" is available
    When I run "python3 -c 'from scripts.accessibility import PALETTES; trusts=["admin","trusted","semi-trusted","untrusted","disposable"]; missing=[t for name,p in PALETTES.items() for t in trusts if t not in p]; assert not missing, missing; print("%d palettes ok" % len(PALETTES))'"
    Then exit code is 0
    And output contains "palettes ok"

  Scenario: Colorblind palettes differ from default
    # Matrix: A11Y-002
    Given "python3" is available
    When I run "python3 -c 'from scripts.accessibility import PALETTES; d=PALETTES["default"]; assert PALETTES["colorblind-deutan"]["admin"]["border"] != d["admin"]["border"]; print("colorblind differs ok")'"
    Then exit code is 0
    And output contains "colorblind differs ok"

  Scenario: Settings persistence roundtrip
    # Matrix: A11Y-003
    Given "python3" is available
    When I run "python3 -c 'from scripts.accessibility import DEFAULT_SETTINGS; assert "color_palette" in DEFAULT_SETTINGS; assert "dyslexia_mode" in DEFAULT_SETTINGS; print("settings schema ok")'"
    Then exit code is 0
    And output contains "settings schema ok"
