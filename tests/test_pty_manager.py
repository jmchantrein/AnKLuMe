"""Tests for scripts/web/pty_manager.py — PTY session management."""

import asyncio
import contextlib
import os
import time

import pytest

from scripts.web.pty_manager import PtyManager, PtySession


class TestPtySession:
    def test_session_starts_with_valid_fd(self):
        session = PtySession(cmd=["/bin/echo", "hello"])
        try:
            assert session.fd >= 0
            assert session.pid > 0
        finally:
            session.close()

    def test_write_and_read(self):
        session = PtySession(cmd=["/bin/cat"])
        try:
            session.write(b"hello\n")
            time.sleep(0.1)
            data = os.read(session.fd, 1024)
            assert b"hello" in data
        finally:
            session.close()

    def test_write_updates_last_activity(self):
        session = PtySession(cmd=["/bin/cat"])
        try:
            before = session.last_activity
            time.sleep(0.05)
            session.write(b"x")
            assert session.last_activity > before
        finally:
            session.close()

    def test_resize(self):
        session = PtySession(cmd=["/bin/bash"])
        try:
            session.resize(120, 40)
            assert session.cols == 120
            assert session.rows == 40
        finally:
            session.close()

    def test_resize_small(self):
        session = PtySession(cmd=["/bin/bash"])
        try:
            session.resize(1, 1)
            assert session.cols == 1
            assert session.rows == 1
        finally:
            session.close()

    def test_initial_dimensions(self):
        session = PtySession(cmd=["/bin/bash"], cols=100, rows=50)
        try:
            assert session.cols == 100
            assert session.rows == 50
        finally:
            session.close()

    def test_close_cleans_up(self):
        session = PtySession(cmd=["/bin/bash"])
        pid = session.pid
        session.close()
        assert session.fd == -1
        assert session.pid == 0
        # Process should be terminated
        try:
            os.kill(pid, 0)
            time.sleep(0.1)
            os.waitpid(pid, os.WNOHANG)
        except (OSError, ChildProcessError):
            pass  # Expected: process already gone

    def test_double_close_safe(self):
        session = PtySession(cmd=["/bin/echo", "x"])
        session.close()
        session.close()  # Should not raise

    def test_alive_true_for_running_process(self):
        session = PtySession(cmd=["/bin/bash"])
        try:
            assert session.alive is True
        finally:
            session.close()

    def test_alive_false_after_close(self):
        session = PtySession(cmd=["/bin/bash"])
        session.close()
        assert session.alive is False

    def test_alive_false_for_exited_process(self):
        session = PtySession(cmd=["/bin/true"])
        time.sleep(0.2)  # Let process exit
        alive = session.alive
        session.close()
        assert alive is False

    def test_custom_cmd(self):
        session = PtySession(cmd=["/bin/echo", "custom"])
        try:
            assert session.cmd == ["/bin/echo", "custom"]
        finally:
            session.close()

    def test_default_cmd_is_bash(self):
        session = PtySession()
        try:
            assert session.cmd == ["/bin/bash"]
        finally:
            session.close()


class TestPtyManager:
    def test_create_and_get(self):
        mgr = PtyManager(max_sessions=4)
        try:
            session = mgr.create("test-1")
            assert mgr.get("test-1") is session
        finally:
            mgr.close_all()

    def test_close_removes_session(self):
        mgr = PtyManager(max_sessions=4)
        mgr.create("test-1")
        mgr.close("test-1")
        assert mgr.get("test-1") is None

    def test_close_nonexistent_is_safe(self):
        mgr = PtyManager()
        mgr.close("nonexistent")  # Should not raise

    def test_close_all(self):
        mgr = PtyManager(max_sessions=4)
        try:
            mgr.create("a")
            mgr.create("b")
            assert len(mgr.sessions) == 2
        finally:
            mgr.close_all()
        assert len(mgr.sessions) == 0

    def test_close_all_empty(self):
        mgr = PtyManager()
        mgr.close_all()  # Should not raise

    def test_max_sessions_enforced(self):
        mgr = PtyManager(max_sessions=2)
        try:
            mgr.create("a")
            mgr.create("b")
            with pytest.raises(RuntimeError, match="Max sessions"):
                mgr.create("c")
        finally:
            mgr.close_all()

    def test_recreate_same_sid(self):
        mgr = PtyManager(max_sessions=2)
        try:
            s1 = mgr.create("x")
            s2 = mgr.create("x")
            assert s1 is not s2
            assert len(mgr.sessions) == 1
        finally:
            mgr.close_all()

    def test_idle_cleanup(self):
        mgr = PtyManager(max_sessions=4, idle_timeout=0)
        try:
            mgr.create("old", cmd=["/bin/bash"])
            time.sleep(0.05)
            mgr._cleanup_idle()
            assert len(mgr.sessions) == 0
        finally:
            mgr.close_all()

    def test_idle_cleanup_keeps_active(self):
        mgr = PtyManager(max_sessions=4, idle_timeout=3600)
        try:
            mgr.create("active", cmd=["/bin/bash"])
            mgr._cleanup_idle()
            assert len(mgr.sessions) == 1
        finally:
            mgr.close_all()

    def test_cleanup_dead_processes(self):
        mgr = PtyManager(max_sessions=4, idle_timeout=3600)
        try:
            mgr.create("dead", cmd=["/bin/true"])
            time.sleep(0.2)  # Let process exit
            mgr._cleanup_idle()
            assert len(mgr.sessions) == 0
        finally:
            mgr.close_all()

    def test_get_nonexistent_returns_none(self):
        mgr = PtyManager()
        assert mgr.get("nope") is None

    def test_create_with_custom_cmd(self):
        mgr = PtyManager()
        try:
            session = mgr.create("s", cmd=["/bin/cat"])
            assert session.cmd == ["/bin/cat"]
        finally:
            mgr.close_all()

    def test_create_with_custom_size(self):
        mgr = PtyManager()
        try:
            session = mgr.create("s", cols=200, rows=60)
            assert session.cols == 200
            assert session.rows == 60
        finally:
            mgr.close_all()


class TestPtyManagerReadLoop:
    def test_read_loop_receives_data(self):
        async def _run():
            mgr = PtyManager()
            try:
                mgr.create("rl", cmd=["/bin/echo", "hello-from-pty"])
                received = []

                async def collect(data):
                    received.append(data)

                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(
                        mgr.read_loop("rl", collect),
                        timeout=2.0,
                    )
                return b"".join(received)
            finally:
                mgr.close_all()

        data = asyncio.run(_run())
        assert b"hello-from-pty" in data

    def test_read_loop_nonexistent_sid(self):
        async def _run():
            mgr = PtyManager()
            await mgr.read_loop("nope", lambda d: None)

        asyncio.run(_run())  # Should complete without error

    def test_blocking_read_returns_none_on_closed_fd(self):
        session = PtySession(cmd=["/bin/true"])
        time.sleep(0.2)
        session.close()
        result = PtyManager._blocking_read(session)
        assert result is None
