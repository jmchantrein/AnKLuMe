Feature: PTY manager
  Manages pseudo-terminal sessions that back the xterm.js WebSocket
  connections. Handles session creation, lifecycle, cleanup, and limits.

  # ── PtySession ──────────────────────────────────────────

  Scenario: PTY session creates valid process
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.pty_manager import PtySession; s = PtySession(cmd=["/bin/echo","hi"]); assert s.fd >= 0 and s.pid > 0; s.close()'"
    Then exit code is 0

  Scenario: PTY session defaults to bash
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.pty_manager import PtySession; s = PtySession(); assert s.cmd == ["/bin/bash"]; s.close()'"
    Then exit code is 0

  Scenario: PTY session accepts custom command
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.pty_manager import PtySession; s = PtySession(cmd=["/bin/cat"]); assert s.cmd == ["/bin/cat"]; s.close()'"
    Then exit code is 0

  Scenario: PTY session accepts custom dimensions
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.pty_manager import PtySession; s = PtySession(cols=120, rows=40); assert s.cols == 120 and s.rows == 40; s.close()'"
    Then exit code is 0

  Scenario: PTY session resize updates dimensions
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.pty_manager import PtySession; s = PtySession(cmd=["/bin/bash"]); s.resize(200, 50); assert s.cols == 200 and s.rows == 50; s.close()'"
    Then exit code is 0

  Scenario: PTY session write updates last_activity
    Given "python3" is available
    When I run "python3 -c 'import time; from scripts.web.pty_manager import PtySession; s = PtySession(cmd=["/bin/cat"]); t = s.last_activity; time.sleep(0.05); s.write(b"x"); assert s.last_activity > t; s.close()'"
    Then exit code is 0

  Scenario: PTY session close cleans up fd and pid
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.pty_manager import PtySession; s = PtySession(cmd=["/bin/bash"]); s.close(); assert s.fd == -1 and s.pid == 0'"
    Then exit code is 0

  Scenario: PTY session double close is safe
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.pty_manager import PtySession; s = PtySession(cmd=["/bin/echo","x"]); s.close(); s.close()'"
    Then exit code is 0

  Scenario: PTY session alive is true for running process
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.pty_manager import PtySession; s = PtySession(cmd=["/bin/bash"]); assert s.alive is True; s.close()'"
    Then exit code is 0

  Scenario: PTY session alive is false after close
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.pty_manager import PtySession; s = PtySession(cmd=["/bin/bash"]); s.close(); assert s.alive is False'"
    Then exit code is 0

  Scenario: PTY session alive is false for exited process
    Given "python3" is available
    When I run "python3 -c 'import time; from scripts.web.pty_manager import PtySession; s = PtySession(cmd=["/bin/true"]); time.sleep(0.2); alive = s.alive; s.close(); assert alive is False'"
    Then exit code is 0

  # ── PtyManager ──────────────────────────────────────────

  Scenario: PTY manager enforces max sessions
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.pty_manager import PtyManager; m = PtyManager(max_sessions=1); m.create("a"); failed = False; exec("try:\n m.create(chr(98))\nexcept RuntimeError:\n failed = True"); m.close_all(); assert failed'"
    Then exit code is 0

  Scenario: PTY manager create and get
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.pty_manager import PtyManager; m = PtyManager(); s = m.create("t"); assert m.get("t") is s; m.close_all()'"
    Then exit code is 0

  Scenario: PTY manager close removes session
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.pty_manager import PtyManager; m = PtyManager(); m.create("t"); m.close("t"); assert m.get("t") is None'"
    Then exit code is 0

  Scenario: PTY manager close nonexistent is safe
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.pty_manager import PtyManager; m = PtyManager(); m.close("nope")'"
    Then exit code is 0

  Scenario: PTY manager close_all empties sessions
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.pty_manager import PtyManager; m = PtyManager(max_sessions=4); m.create("a"); m.create("b"); m.close_all(); assert len(m.sessions) == 0'"
    Then exit code is 0

  Scenario: PTY manager recreate same sid replaces session
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.pty_manager import PtyManager; m = PtyManager(max_sessions=2); s1 = m.create("x"); s2 = m.create("x"); assert s1 is not s2 and len(m.sessions) == 1; m.close_all()'"
    Then exit code is 0

  Scenario: PTY manager idle cleanup removes timed-out sessions
    Given "python3" is available
    When I run "python3 -c 'import time; from scripts.web.pty_manager import PtyManager; m = PtyManager(max_sessions=4, idle_timeout=0); m.create("old", cmd=["/bin/bash"]); time.sleep(0.05); m._cleanup_idle(); assert len(m.sessions) == 0; m.close_all()'"
    Then exit code is 0

  Scenario: PTY manager cleans up dead processes
    Given "python3" is available
    When I run "python3 -c 'import time; from scripts.web.pty_manager import PtyManager; m = PtyManager(max_sessions=4, idle_timeout=3600); m.create("dead", cmd=["/bin/true"]); time.sleep(0.2); m._cleanup_idle(); assert len(m.sessions) == 0; m.close_all()'"
    Then exit code is 0

  Scenario: PTY manager get nonexistent returns None
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.pty_manager import PtyManager; m = PtyManager(); assert m.get("nope") is None'"
    Then exit code is 0

  Scenario: PTY blocking read returns None on closed fd
    Given "python3" is available
    When I run "python3 -c 'import time; from scripts.web.pty_manager import PtySession, PtyManager; s = PtySession(cmd=["/bin/true"]); time.sleep(0.2); s.close(); assert PtyManager._blocking_read(s) is None'"
    Then exit code is 0
