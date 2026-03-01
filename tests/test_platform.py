"""Tests for scripts/platform_server.py — learning platform."""

import shutil

import pytest

fastapi = pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")

from starlette.testclient import TestClient  # noqa: E402

from scripts.web.ws_terminal import manager  # noqa: E402


@pytest.fixture()
def client():
    """Create a test client for the platform server."""
    from scripts import platform_server
    with TestClient(platform_server.app) as c:
        yield c
    manager.close_all()


class TestLandingPage:
    def test_landing_returns_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_landing_contains_guide_link(self, client):
        resp = client.get("/")
        assert "/guide" in resp.text

    def test_landing_contains_labs_link(self, client):
        resp = client.get("/")
        assert "/labs" in resp.text

    def test_landing_has_html_structure(self, client):
        resp = client.get("/")
        assert "<!DOCTYPE html>" in resp.text
        assert "</html>" in resp.text

    def test_landing_has_title(self, client):
        resp = client.get("/")
        assert "anklume Learn" in resp.text

    def test_landing_has_chapter_cards(self, client):
        resp = client.get("/")
        assert "ch-card" in resp.text

    def test_landing_has_capability_tour(self, client):
        resp = client.get("/")
        assert "Capability Tour" in resp.text

    def test_landing_response_is_html(self, client):
        resp = client.get("/")
        assert "text/html" in resp.headers["content-type"]


class TestGuideIndex:
    def test_guide_returns_200(self, client):
        resp = client.get("/guide")
        assert resp.status_code == 200

    def test_guide_lists_8_chapters(self, client):
        resp = client.get("/guide")
        assert "ch-card" in resp.text
        for i in range(1, 9):
            assert f"/guide/{i}" in resp.text

    def test_guide_has_title(self, client):
        resp = client.get("/guide")
        assert "Capability Tour" in resp.text

    def test_guide_has_chapter_titles(self, client):
        resp = client.get("/guide")
        assert "ch-title" in resp.text

    def test_guide_has_descriptions(self, client):
        resp = client.get("/guide")
        assert "ch-desc" in resp.text


class TestGuideChapter:
    def test_chapter_1_returns_200(self, client):
        resp = client.get("/guide/1")
        assert resp.status_code == 200

    def test_chapter_has_split_pane(self, client):
        resp = client.get("/guide/1")
        assert "learn-layout" in resp.text
        assert "learn-content" in resp.text
        assert "learn-terminal" in resp.text

    def test_chapter_has_xterm(self, client):
        resp = client.get("/guide/1")
        assert "xterm.js" in resp.text

    def test_chapter_has_navigation(self, client):
        resp = client.get("/guide/1")
        assert "All chapters" in resp.text
        assert "Next" in resp.text

    def test_chapter_1_no_previous(self, client):
        resp = client.get("/guide/1")
        assert "Previous" not in resp.text

    def test_chapter_99_returns_404(self, client):
        resp = client.get("/guide/99")
        assert resp.status_code == 404

    def test_chapter_0_returns_404(self, client):
        resp = client.get("/guide/0")
        assert resp.status_code == 404

    def test_chapter_has_clickable_commands(self, client):
        resp = client.get("/guide/1")
        assert "runCmd" in resp.text

    def test_last_chapter_no_next(self, client):
        resp = client.get("/guide/8")
        assert "Previous" in resp.text
        assert "/guide/9" not in resp.text

    def test_middle_chapter_has_both_nav(self, client):
        resp = client.get("/guide/4")
        assert "Previous" in resp.text
        assert "Next" in resp.text

    def test_chapter_shows_counter(self, client):
        resp = client.get("/guide/3")
        assert "Ch 3/8" in resp.text

    def test_chapter_has_terminal_js(self, client):
        resp = client.get("/guide/1")
        assert "window.runCmd" in resp.text

    def test_chapter_has_terminal_div(self, client):
        resp = client.get("/guide/1")
        assert 'id="terminal"' in resp.text

    def test_all_chapters_return_200(self, client):
        for i in range(1, 9):
            resp = client.get(f"/guide/{i}")
            assert resp.status_code == 200, f"Chapter {i} failed"


class TestLabsPlaceholder:
    def test_labs_returns_200(self, client):
        resp = client.get("/labs")
        assert resp.status_code == 200

    def test_labs_shows_placeholder(self, client):
        resp = client.get("/labs")
        assert "future update" in resp.text.lower()

    def test_labs_has_title(self, client):
        resp = client.get("/labs")
        assert "Labs" in resp.text


class TestNotFound:
    def test_invalid_route_returns_404(self, client):
        resp = client.get("/nonexistent")
        assert resp.status_code == 404


class TestWebSocket:
    @pytest.mark.skipif(
        not shutil.which("bash"),
        reason="bash not available",
    )
    def test_websocket_connects(self, client):
        with client.websocket_connect("/ws/terminal/test-ws") as ws:
            ws.send_text("echo hello\r")
            data = ws.receive_bytes()
            assert len(data) > 0

    @pytest.mark.skipif(
        not shutil.which("bash"),
        reason="bash not available",
    )
    def test_websocket_receives_output(self, client):
        with client.websocket_connect("/ws/terminal/test-output") as ws:
            ws.send_text("echo MARKER_42\r")
            # Read multiple chunks until we find the output
            received = b""
            for _ in range(20):
                try:
                    data = ws.receive_bytes()
                    received += data
                    if b"MARKER_42" in received:
                        break
                except Exception:
                    break
            assert b"MARKER_42" in received

    @pytest.mark.skipif(
        not shutil.which("bash"),
        reason="bash not available",
    )
    def test_websocket_resize(self, client):
        import json
        with client.websocket_connect("/ws/terminal/test-resize") as ws:
            resize_msg = json.dumps({"type": "resize", "cols": 120, "rows": 40})
            ws.send_text(resize_msg)
            # Resize shouldn't crash; send a command to verify session is alive
            ws.send_text("echo alive\r")
            data = ws.receive_bytes()
            assert len(data) > 0

    @pytest.mark.skipif(
        not shutil.which("bash"),
        reason="bash not available",
    )
    def test_websocket_binary_input(self, client):
        with client.websocket_connect("/ws/terminal/test-binary") as ws:
            ws.send_bytes(b"echo binary_test\r")
            received = b""
            for _ in range(20):
                try:
                    data = ws.receive_bytes()
                    received += data
                    if b"binary_test" in received:
                        break
                except Exception:
                    break
            assert b"binary_test" in received
