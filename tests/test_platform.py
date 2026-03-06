"""Tests for scripts/platform_server.py — learning platform."""

import pytest

fastapi = pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")

from starlette.testclient import TestClient  # noqa: E402


@pytest.fixture()
def client(monkeypatch):
    """Create a test client for the platform server.

    Patches ttyd startup since it's not available in test env.
    """
    from scripts import platform_server
    monkeypatch.setattr(platform_server, "_start_ttyd", lambda port=7681: None)
    monkeypatch.setattr(platform_server, "_stop_ttyd", lambda: None)
    with TestClient(platform_server.app) as c:
        yield c


class TestLandingPage:
    def test_landing_returns_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_landing_contains_labs_link(self, client):
        resp = client.get("/")
        assert "/labs" in resp.text

    def test_landing_has_html_structure(self, client):
        resp = client.get("/")
        assert "<!DOCTYPE html>" in resp.text
        assert "</html>" in resp.text

    def test_landing_has_title(self, client):
        resp = client.get("/")
        assert "anklume" in resp.text

    def test_landing_has_action_cards(self, client):
        resp = client.get("/")
        assert "home-card" in resp.text
        assert "/setup" in resp.text
        assert "/guide" in resp.text

    def test_landing_lang_switch(self, client):
        resp = client.get("/?lang=en")
        assert "Configure" in resp.text
        resp_fr = client.get("/?lang=fr")
        assert "Configurer" in resp_fr.text

    def test_landing_response_is_html(self, client):
        resp = client.get("/")
        assert "text/html" in resp.headers["content-type"]


class TestSetupPage:
    def test_setup_returns_200(self, client):
        resp = client.get("/setup")
        assert resp.status_code == 200

    def test_setup_has_terminal(self, client):
        resp = client.get("/setup")
        assert 'id="terminal"' in resp.text
        assert "xterm.js" in resp.text or "xterm" in resp.text

    def test_setup_has_launch_button(self, client):
        resp = client.get("/setup")
        assert "start.sh" in resp.text

    def test_explore_mode(self, client):
        resp = client.get("/setup?mode=explore")
        assert resp.status_code == 200
        assert "--yes --backend dir" in resp.text

    def test_setup_has_home_link(self, client):
        resp = client.get("/setup")
        assert 'href="/"' in resp.text


class TestLabsPlaceholder:
    def test_labs_returns_200(self, client):
        resp = client.get("/labs")
        assert resp.status_code == 200

    def test_labs_shows_placeholder(self, client):
        resp = client.get("/labs?lang=en")
        assert "future update" in resp.text.lower()

    def test_labs_has_title(self, client):
        resp = client.get("/labs?lang=en")
        assert "Practice" in resp.text


class TestGuideIndex:
    def test_guide_index_returns_200(self, client):
        resp = client.get("/guide")
        assert resp.status_code == 200

    def test_guide_index_has_chapter_links(self, client):
        resp = client.get("/guide")
        assert "ch-card" in resp.text

    def test_guide_index_has_title(self, client):
        resp = client.get("/guide?lang=en")
        assert "Getting Started" in resp.text


class TestGuideChapter:
    def test_chapter_1_returns_200(self, client):
        resp = client.get("/guide/1")
        assert resp.status_code == 200

    def test_chapter_has_terminal(self, client):
        resp = client.get("/guide/1")
        assert 'id="terminal"' in resp.text
        assert "xterm" in resp.text

    def test_chapter_has_navigation(self, client):
        resp = client.get("/guide/1?lang=en")
        assert "Next" in resp.text

    def test_invalid_chapter_returns_404(self, client):
        resp = client.get("/guide/999")
        assert resp.status_code == 404


class TestPoolConf:
    def test_pool_conf_404_when_missing(self, client):
        resp = client.get("/pool-conf")
        assert resp.status_code == 404

    def test_pool_conf_returns_content(self, client, monkeypatch, tmp_path):
        conf = tmp_path / "pool.conf"
        conf.write_text("POOL_NAME=test\nPOOL_BACKEND=zfs\n")
        from scripts import platform_server
        monkeypatch.setattr(platform_server, "POOL_CONF_PATH", conf)
        resp = client.get("/pool-conf")
        assert resp.status_code == 200
        assert "POOL_NAME=test" in resp.text

    def test_setup_page_has_conf_button_when_exists(self, client, monkeypatch, tmp_path):
        conf = tmp_path / "pool.conf"
        conf.write_text("POOL_NAME=test\n")
        from scripts import platform_server
        monkeypatch.setattr(platform_server, "POOL_CONF_PATH", conf)
        resp = client.get("/setup")
        assert "showPoolConf" in resp.text


class TestCreateInfraYml:
    def test_create_infra_yml_no_prod_dir(self, client, monkeypatch):
        from scripts import platform_server
        monkeypatch.setattr(platform_server, "_production_anklume_dir", lambda: None)
        resp = client.post("/create-infra-yml")
        assert resp.status_code == 400

    def test_create_infra_yml_success(self, client, monkeypatch, tmp_path):
        prod_dir = tmp_path / "anklume"
        prod_dir.mkdir()
        from scripts import platform_server
        monkeypatch.setattr(platform_server, "_production_anklume_dir", lambda: str(prod_dir))
        resp = client.post("/create-infra-yml")
        assert resp.status_code == 200
        assert "Created" in resp.text
        assert (prod_dir / "infra.yml").exists()

    def test_create_infra_yml_already_exists(self, client, monkeypatch, tmp_path):
        prod_dir = tmp_path / "anklume"
        prod_dir.mkdir()
        (prod_dir / "infra.yml").write_text("existing")
        from scripts import platform_server
        monkeypatch.setattr(platform_server, "_production_anklume_dir", lambda: str(prod_dir))
        resp = client.post("/create-infra-yml")
        assert resp.status_code == 200
        assert "already exists" in resp.text


class TestNotFound:
    def test_invalid_route_returns_404(self, client):
        resp = client.get("/nonexistent")
        assert resp.status_code == 404
