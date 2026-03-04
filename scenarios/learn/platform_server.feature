@requires.web_factory
Feature: Platform server
  The unified learning platform server serves guide content with a
  split-pane terminal interface, chapter navigation, and labs placeholder.

  # ── Landing page ────────────────────────────────────────

  Scenario: Platform server landing page returns 200
    Given "python3" is available
    When I run "python3 -c 'from starlette.testclient import TestClient; from scripts.platform_server import app; r = TestClient(app).get("/"); assert r.status_code == 200'"
    Then exit code is 0

  @requires.platform_server
  Scenario: Landing page has guide and labs links
    Given "python3" is available
    When I run "python3 -c 'from starlette.testclient import TestClient; from scripts.platform_server import app; r = TestClient(app).get("/"); assert "/guide" in r.text and "/labs" in r.text'"
    Then exit code is 0

  @requires.platform_server
  Scenario: Landing page has platform title
    Given "python3" is available
    When I run "python3 -c 'from starlette.testclient import TestClient; from scripts.platform_server import app; r = TestClient(app).get("/"); assert "Learning Platform" in r.text'"
    Then exit code is 0

  # ── Guide index ─────────────────────────────────────────

  @requires.platform_server
  Scenario: Guide index page returns 200
    Given "python3" is available
    When I run "python3 -c 'from starlette.testclient import TestClient; from scripts.platform_server import app; r = TestClient(app).get("/guide"); assert r.status_code == 200'"
    Then exit code is 0

  @requires.platform_server
  Scenario: Guide index lists all 8 chapters
    Given "python3" is available
    When I run "python3 -c 'from starlette.testclient import TestClient; from scripts.platform_server import app; r = TestClient(app).get("/guide"); assert all(("/guide/" + str(i)) in r.text for i in range(1, 9))'"
    Then exit code is 0

  @requires.platform_server
  Scenario: Guide index has chapter titles
    Given "python3" is available
    When I run "python3 -c 'from starlette.testclient import TestClient; from scripts.platform_server import app; r = TestClient(app).get("/guide"); assert "Domain Isolation" in r.text and "ch-title" in r.text'"
    Then exit code is 0

  # ── Guide chapters ──────────────────────────────────────

  @requires.platform_server
  Scenario: Guide chapter 1 returns 200
    Given "python3" is available
    When I run "python3 -c 'from starlette.testclient import TestClient; from scripts.platform_server import app; r = TestClient(app).get("/guide/1"); assert r.status_code == 200'"
    Then exit code is 0

  @requires.platform_server
  Scenario: Guide chapter has split-pane layout
    Given "python3" is available
    When I run "python3 -c 'from starlette.testclient import TestClient; from scripts.platform_server import app; r = TestClient(app).get("/guide/1"); assert "learn-layout" in r.text and "learn-content" in r.text and "learn-terminal" in r.text'"
    Then exit code is 0

  @requires.platform_server
  Scenario: Guide chapter includes xterm.js
    Given "python3" is available
    When I run "python3 -c 'from starlette.testclient import TestClient; from scripts.platform_server import app; r = TestClient(app).get("/guide/1"); assert "xterm.js" in r.text'"
    Then exit code is 0

  @requires.platform_server
  Scenario: Guide chapter has navigation
    Given "python3" is available
    When I run "python3 -c 'from starlette.testclient import TestClient; from scripts.platform_server import app; r = TestClient(app).get("/guide/1"); assert "All chapters" in r.text and "/guide/2" in r.text'"
    Then exit code is 0

  @requires.platform_server
  Scenario: Guide chapter 1 has no previous link
    Given "python3" is available
    When I run "python3 -c 'from starlette.testclient import TestClient; from scripts.platform_server import app; r = TestClient(app).get("/guide/1"); assert "Previous" not in r.text'"
    Then exit code is 0

  @requires.platform_server
  Scenario: Guide chapter 8 has no next link
    Given "python3" is available
    When I run "python3 -c 'from starlette.testclient import TestClient; from scripts.platform_server import app; r = TestClient(app).get("/guide/8"); assert "Next" not in r.text and "Previous" in r.text'"
    Then exit code is 0

  @requires.platform_server
  Scenario: Guide chapter middle has both prev and next
    Given "python3" is available
    When I run "python3 -c 'from starlette.testclient import TestClient; from scripts.platform_server import app; r = TestClient(app).get("/guide/4"); assert "Previous" in r.text and "Next" in r.text'"
    Then exit code is 0

  @requires.platform_server
  Scenario: Guide chapter shows counter
    Given "python3" is available
    When I run "python3 -c 'from starlette.testclient import TestClient; from scripts.platform_server import app; r = TestClient(app).get("/guide/3"); assert "Ch 3/8" in r.text'"
    Then exit code is 0

  @requires.platform_server
  Scenario: Guide chapter 1 has clickable commands
    Given "python3" is available
    When I run "python3 -c 'from starlette.testclient import TestClient; from scripts.platform_server import app; r = TestClient(app).get("/guide/1"); assert "runCmd" in r.text and "run-btn" in r.text'"
    Then exit code is 0

  @requires.platform_server
  Scenario: Guide chapter 99 returns 404
    Given "python3" is available
    When I run "python3 -c 'from starlette.testclient import TestClient; from scripts.platform_server import app; r = TestClient(app).get("/guide/99"); assert r.status_code == 404'"
    Then exit code is 0

  # ── Labs ────────────────────────────────────────────────

  @requires.platform_server
  Scenario: Labs page returns 200 with placeholder
    Given "python3" is available
    When I run "python3 -c 'from starlette.testclient import TestClient; from scripts.platform_server import app; r = TestClient(app).get("/labs"); assert r.status_code == 200 and "future update" in r.text'"
    Then exit code is 0

  # ── WebSocket route ─────────────────────────────────────

  @requires.platform_server
  Scenario: Platform server has WebSocket route
    Given "python3" is available
    When I run "python3 -c 'from scripts.platform_server import app; routes = [r.path for r in app.routes]; assert any("ws/terminal" in r for r in routes)'"
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
