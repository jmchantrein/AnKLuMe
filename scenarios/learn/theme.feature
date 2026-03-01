Feature: Web theme
  Shared CSS theme for all anklume web applications. Single source of
  truth for the dark theme, trust-level colors, and component styles.

  Scenario: Web theme module is importable
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.theme import BASE_CSS; assert chr(58) + chr(114) + chr(111) + chr(111) + chr(116) in BASE_CSS'"
    Then exit code is 0

  Scenario: Theme has all CSS constants
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.theme import BASE_CSS, DASHBOARD_CSS, GUIDE_CSS, TERMINAL_CSS; assert all(len(c) > 50 for c in [BASE_CSS, DASHBOARD_CSS, GUIDE_CSS, TERMINAL_CSS])'"
    Then exit code is 0

  Scenario: BASE_CSS has root variables for colors
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.theme import BASE_CSS; assert all(v in BASE_CSS for v in ["--bg", "--fg", "--card", "--border", "--accent", "--success", "--muted", "--dim"])'"
    Then exit code is 0

  Scenario: BASE_CSS has body styles
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.theme import BASE_CSS; assert "body" in BASE_CSS and "font-family" in BASE_CSS'"
    Then exit code is 0

  Scenario: BASE_CSS has card class with border-radius
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.theme import BASE_CSS; assert ".card" in BASE_CSS and "border-radius" in BASE_CSS'"
    Then exit code is 0

  Scenario: BASE_CSS has btn and grid classes
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.theme import BASE_CSS; assert ".btn" in BASE_CSS and ".grid" in BASE_CSS and "grid-template-columns" in BASE_CSS'"
    Then exit code is 0

  Scenario: BASE_CSS has nav and terminal classes
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.theme import BASE_CSS; assert ".nav" in BASE_CSS and "pre.terminal" in BASE_CSS'"
    Then exit code is 0

  Scenario: BASE_CSS has empty class
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.theme import BASE_CSS; assert ".empty" in BASE_CSS'"
    Then exit code is 0

  Scenario: TERMINAL_CSS has split-pane layout
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.theme import TERMINAL_CSS; assert all(c in TERMINAL_CSS for c in [".learn-layout", ".learn-content", ".learn-terminal"])'"
    Then exit code is 0

  Scenario: TERMINAL_CSS has cmd-block and run-btn
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.theme import TERMINAL_CSS; assert ".cmd-block" in TERMINAL_CSS and ".run-btn" in TERMINAL_CSS'"
    Then exit code is 0

  Scenario: TERMINAL_CSS has learn-nav
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.theme import TERMINAL_CSS; assert ".learn-nav" in TERMINAL_CSS'"
    Then exit code is 0

  Scenario: DASHBOARD_CSS has status indicators
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.theme import DASHBOARD_CSS; assert all(c in DASHBOARD_CSS for c in [".status", ".running", ".stopped"])'"
    Then exit code is 0

  Scenario: DASHBOARD_CSS has domain-badge and net-card
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.theme import DASHBOARD_CSS; assert ".domain-badge" in DASHBOARD_CSS and ".net-card" in DASHBOARD_CSS'"
    Then exit code is 0

  Scenario: DASHBOARD_CSS has policy and refresh-info
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.theme import DASHBOARD_CSS; assert ".policy" in DASHBOARD_CSS and ".refresh-info" in DASHBOARD_CSS'"
    Then exit code is 0

  Scenario: GUIDE_CSS has chapter card classes
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.theme import GUIDE_CSS; assert all(c in GUIDE_CSS for c in [".chapters", ".ch-card", ".ch-num", ".ch-title", ".ch-desc"])'"
    Then exit code is 0

  Scenario: Trust CSS returns colors for all trust levels
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.theme import trust_css; results = [trust_css(l) for l in ["admin","trusted","semi-trusted","untrusted","disposable"]]; assert all("border" in r and "bg" in r for r in results)'"
    Then exit code is 0

  Scenario: Trust CSS admin has blue border
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.theme import trust_css; assert trust_css("admin")["border"] == "#3333ff"'"
    Then exit code is 0

  Scenario: Trust CSS trusted has green border
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.theme import trust_css; assert trust_css("trusted")["border"] == "#33cc33"'"
    Then exit code is 0

  Scenario: Trust CSS untrusted has red border
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.theme import trust_css; assert trust_css("untrusted")["border"] == "#cc3333"'"
    Then exit code is 0

  Scenario: Trust CSS returns fallback for unknown level
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.theme import trust_css; c = trust_css("unknown"); assert c["border"] == "#30363d" and c["bg"] == "#161b22"'"
    Then exit code is 0

  Scenario: Trust CSS returns dict with exactly two keys
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.theme import trust_css; assert set(trust_css("admin").keys()) == {"border", "bg"}'"
    Then exit code is 0
