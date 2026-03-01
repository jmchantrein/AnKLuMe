Feature: WebSocket terminal
  WebSocket endpoint for xterm.js terminal sessions. Relays I/O between
  the browser and PTY sessions managed by PtyManager.

  Scenario: WebSocket terminal module has valid syntax
    Given "python3" is available
    When I run "python3 -m py_compile scripts/web/ws_terminal.py"
    Then exit code is 0

  Scenario: WebSocket terminal router has endpoint
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.ws_terminal import router; assert any(hasattr(r, "path") and "terminal" in getattr(r, "path", "") for r in router.routes)'"
    Then exit code is 0

  Scenario: WebSocket terminal get_manager returns PtyManager
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.ws_terminal import get_manager; from scripts.web.pty_manager import PtyManager; assert isinstance(get_manager(), PtyManager)'"
    Then exit code is 0

  Scenario: WebSocket terminal manager has correct limits
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.ws_terminal import get_manager; m = get_manager(); assert m.max_sessions == 4 and m.idle_timeout == 1800'"
    Then exit code is 0

  Scenario: PTY manager module has valid syntax
    Given "python3" is available
    When I run "python3 -m py_compile scripts/web/pty_manager.py"
    Then exit code is 0
