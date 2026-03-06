@requires.web_factory
Feature: Platform server
  The unified learning platform server serves lab content with a
  split-pane terminal interface and lab navigation.

  # ── Landing page ────────────────────────────────────────

  Scenario: Platform server landing page returns 200
    Given "python3" is available
    When I run "python3 -c 'from starlette.testclient import TestClient; from scripts.platform_server import app; r = TestClient(app).get("/"); assert r.status_code == 200'"
    Then exit code is 0

  @requires.platform_server
  Scenario: Landing page has labs link
    Given "python3" is available
    When I run "python3 -c 'from starlette.testclient import TestClient; from scripts.platform_server import app; r = TestClient(app).get("/"); assert "/labs" in r.text'"
    Then exit code is 0

  # ── Guide ───────────────────────────────────────────────

  @requires.platform_server
  Scenario: Guide index returns 200
    Given "python3" is available
    When I run "python3 -c 'from starlette.testclient import TestClient; from scripts.platform_server import app; r = TestClient(app).get("/guide"); assert r.status_code == 200'"
    Then exit code is 0

  @requires.platform_server
  Scenario: Guide chapter 1 returns 200
    Given "python3" is available
    When I run "python3 -c 'from starlette.testclient import TestClient; from scripts.platform_server import app; r = TestClient(app).get("/guide/1"); assert r.status_code == 200'"
    Then exit code is 0

  # ── Labs ────────────────────────────────────────────────

  @requires.platform_server
  Scenario: Labs page returns 200
    Given "python3" is available
    When I run "python3 -c 'from starlette.testclient import TestClient; from scripts.platform_server import app; r = TestClient(app).get("/labs"); assert r.status_code == 200'"
    Then exit code is 0

  # ── Server internals ───────────────────────────────────

  Scenario: Platform server module has valid syntax
    Given "python3" is available
    When I run "python3 -m py_compile scripts/platform_server.py"
    Then exit code is 0

  @requires.platform_server
  Scenario: Platform server has lifespan cleanup
    Given "python3" is available
    When I run "python3 -c 'from scripts.platform_server import app; assert app.router.lifespan_context is not None'"
    Then exit code is 0

  @requires.platform_server
  Scenario: Platform server TERMINAL_JS has runCmd function
    Given "python3" is available
    When I run "python3 -c 'from scripts.platform_server import TERMINAL_JS; assert "runCmd" in TERMINAL_JS and "WebSocket" in TERMINAL_JS'"
    Then exit code is 0
