"""PTY session manager for the web terminal.

Manages pseudo-terminal sessions that back the xterm.js WebSocket
connections. Each session wraps a pty.fork() child process.
"""

from __future__ import annotations

import asyncio
import contextlib
import fcntl
import os
import pty
import signal
import struct
import termios
import time


class PtySession:
    """A single PTY + child process."""

    def __init__(self, cmd: list[str] | None = None, cols: int = 80, rows: int = 24):
        self.cmd = cmd or ["/bin/bash"]
        self.cols = cols
        self.rows = rows
        self.last_activity = time.monotonic()
        self.pid: int = 0
        self.fd: int = -1
        self._start()

    def _start(self) -> None:
        pid, fd = pty.openpty()
        child_pid = os.fork()
        if child_pid == 0:
            # Child process
            os.close(pid)
            os.setsid()
            fcntl.ioctl(fd, termios.TIOCSWINSZ,
                        struct.pack("HHHH", self.rows, self.cols, 0, 0))
            os.dup2(fd, 0)
            os.dup2(fd, 1)
            os.dup2(fd, 2)
            if fd > 2:
                os.close(fd)
            os.execvp(self.cmd[0], self.cmd)
        else:
            # Parent process
            os.close(fd)
            self.pid = child_pid
            self.fd = pid
            self.resize(self.cols, self.rows)

    def write(self, data: bytes) -> None:
        """Write data to the PTY."""
        self.last_activity = time.monotonic()
        os.write(self.fd, data)

    def resize(self, cols: int, rows: int) -> None:
        """Send TIOCSWINSZ to resize the terminal."""
        self.cols = cols
        self.rows = rows
        fcntl.ioctl(self.fd, termios.TIOCSWINSZ,
                     struct.pack("HHHH", rows, cols, 0, 0))

    def close(self) -> None:
        """Kill child and close fd."""
        if self.fd >= 0:
            with contextlib.suppress(OSError):
                os.close(self.fd)
            self.fd = -1
        if self.pid > 0:
            try:
                os.kill(self.pid, signal.SIGTERM)
                os.waitpid(self.pid, os.WNOHANG)
            except (OSError, ChildProcessError):
                pass
            self.pid = 0

    @property
    def alive(self) -> bool:
        """Check if the child process is still running."""
        if self.pid <= 0:
            return False
        try:
            pid, _ = os.waitpid(self.pid, os.WNOHANG)
            return pid == 0
        except ChildProcessError:
            return False


class PtyManager:
    """Manages multiple PTY sessions with limits and timeouts."""

    def __init__(self, max_sessions: int = 4, idle_timeout: int = 1800):
        self.sessions: dict[str, PtySession] = {}
        self.max_sessions = max_sessions
        self.idle_timeout = idle_timeout

    def create(
        self,
        sid: str,
        cmd: list[str] | None = None,
        cols: int = 80,
        rows: int = 24,
    ) -> PtySession:
        """Create a new PTY session, closing old one if sid exists."""
        if sid in self.sessions:
            self.close(sid)
        self._cleanup_idle()
        if len(self.sessions) >= self.max_sessions:
            msg = f"Max sessions ({self.max_sessions}) reached"
            raise RuntimeError(msg)
        session = PtySession(cmd=cmd, cols=cols, rows=rows)
        self.sessions[sid] = session
        return session

    def get(self, sid: str) -> PtySession | None:
        """Get a session by ID."""
        return self.sessions.get(sid)

    def close(self, sid: str) -> None:
        """Close and remove a session."""
        session = self.sessions.pop(sid, None)
        if session:
            session.close()

    def close_all(self) -> None:
        """Close all sessions."""
        for sid in list(self.sessions):
            self.close(sid)

    def _cleanup_idle(self) -> None:
        """Remove sessions idle beyond timeout."""
        now = time.monotonic()
        stale = [
            sid for sid, s in self.sessions.items()
            if now - s.last_activity > self.idle_timeout or not s.alive
        ]
        for sid in stale:
            self.close(sid)

    async def read_loop(self, sid: str, callback) -> None:
        """Async read loop: calls callback(data) for each PTY output chunk."""
        session = self.sessions.get(sid)
        if not session:
            return
        loop = asyncio.get_event_loop()
        try:
            while session.alive and session.fd >= 0:
                data = await loop.run_in_executor(
                    None, self._blocking_read, session,
                )
                if data is None:
                    break
                session.last_activity = time.monotonic()
                await callback(data)
        except (OSError, asyncio.CancelledError):
            pass

    @staticmethod
    def _blocking_read(session: PtySession) -> bytes | None:
        """Blocking read from PTY fd. Returns None on EOF/error."""
        try:
            return os.read(session.fd, 4096)
        except OSError:
            return None
