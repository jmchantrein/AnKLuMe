"""Tests for scripts/web/theme.py — shared CSS theme."""

from scripts.web.theme import (
    BASE_CSS,
    DASHBOARD_CSS,
    GUIDE_CSS,
    TERMINAL_CSS,
    trust_css,
)


class TestBaseCSS:
    def test_contains_root_variables(self):
        assert ":root" in BASE_CSS
        assert "--bg" in BASE_CSS
        assert "--fg" in BASE_CSS
        assert "--card" in BASE_CSS

    def test_contains_accent_and_success(self):
        assert "--accent" in BASE_CSS
        assert "--success" in BASE_CSS

    def test_contains_muted_and_dim(self):
        assert "--muted" in BASE_CSS
        assert "--dim" in BASE_CSS

    def test_contains_body_styles(self):
        assert "body" in BASE_CSS
        assert "font-family" in BASE_CSS

    def test_contains_card_class(self):
        assert ".card" in BASE_CSS
        assert "border-radius" in BASE_CSS

    def test_contains_btn_class(self):
        assert ".btn" in BASE_CSS

    def test_contains_grid_class(self):
        assert ".grid" in BASE_CSS
        assert "grid-template-columns" in BASE_CSS

    def test_contains_nav_class(self):
        assert ".nav" in BASE_CSS

    def test_contains_terminal_pre(self):
        assert "pre.terminal" in BASE_CSS

    def test_contains_empty_class(self):
        assert ".empty" in BASE_CSS

    def test_is_string(self):
        assert isinstance(BASE_CSS, str)
        assert len(BASE_CSS) > 100


class TestTerminalCSS:
    def test_has_layout(self):
        assert ".learn-layout" in TERMINAL_CSS
        assert ".learn-content" in TERMINAL_CSS
        assert ".learn-terminal" in TERMINAL_CSS

    def test_has_cmd_block(self):
        assert ".cmd-block" in TERMINAL_CSS

    def test_has_run_btn(self):
        assert ".run-btn" in TERMINAL_CSS

    def test_has_nav(self):
        assert ".learn-nav" in TERMINAL_CSS

    def test_is_string(self):
        assert isinstance(TERMINAL_CSS, str)


class TestDashboardCSS:
    def test_has_status(self):
        assert ".status" in DASHBOARD_CSS
        assert ".running" in DASHBOARD_CSS
        assert ".stopped" in DASHBOARD_CSS

    def test_has_name(self):
        assert ".name" in DASHBOARD_CSS

    def test_has_meta(self):
        assert ".meta" in DASHBOARD_CSS

    def test_has_domain_badge(self):
        assert ".domain-badge" in DASHBOARD_CSS

    def test_has_net_card(self):
        assert ".net-card" in DASHBOARD_CSS

    def test_has_policy(self):
        assert ".policy" in DASHBOARD_CSS

    def test_has_refresh_info(self):
        assert ".refresh-info" in DASHBOARD_CSS


class TestGuideCSS:
    def test_has_chapters(self):
        assert ".chapters" in GUIDE_CSS
        assert ".ch-card" in GUIDE_CSS

    def test_has_ch_num(self):
        assert ".ch-num" in GUIDE_CSS

    def test_has_ch_title(self):
        assert ".ch-title" in GUIDE_CSS

    def test_has_ch_desc(self):
        assert ".ch-desc" in GUIDE_CSS


class TestTrustCSS:
    def test_admin_colors(self):
        colors = trust_css("admin")
        assert "border" in colors
        assert "bg" in colors
        assert colors["border"] == "#3333ff"

    def test_trusted_colors(self):
        colors = trust_css("trusted")
        assert colors["border"] == "#33cc33"
        assert colors["bg"] == "#0a1a0a"

    def test_semi_trusted_colors(self):
        colors = trust_css("semi-trusted")
        assert colors["border"] == "#cccc33"

    def test_untrusted_colors(self):
        colors = trust_css("untrusted")
        assert colors["border"] == "#cc3333"

    def test_disposable_colors(self):
        colors = trust_css("disposable")
        assert colors["border"] == "#cc33cc"

    def test_all_levels_have_colors(self):
        levels = ["admin", "trusted", "semi-trusted", "untrusted", "disposable"]
        for level in levels:
            colors = trust_css(level)
            assert colors["border"] != "#30363d", f"{level} uses fallback"
            assert colors["bg"] != "#161b22", f"{level} bg uses fallback"

    def test_unknown_level_returns_fallback(self):
        colors = trust_css("unknown")
        assert colors["border"] == "#30363d"
        assert colors["bg"] == "#161b22"

    def test_empty_string_returns_fallback(self):
        colors = trust_css("")
        assert colors["border"] == "#30363d"

    def test_returns_dict_with_two_keys(self):
        colors = trust_css("admin")
        assert set(colors.keys()) == {"border", "bg"}

    def test_no_duplication_with_dashboard(self):
        """Dashboard should import from theme, not duplicate colors."""
        import scripts.dashboard as dash
        assert not hasattr(dash, "TRUST_COLORS"), (
            "dashboard.py still has inline TRUST_COLORS — should import from theme"
        )


class TestWebInit:
    def test_create_app_returns_fastapi(self):
        from scripts.web import create_app
        app = create_app("Test App")
        assert app.title == "Test App"

    def test_create_app_default_title(self):
        from scripts.web import create_app
        app = create_app()
        assert app.title == "anklume"

    def test_create_app_is_fastapi_instance(self):
        from fastapi import FastAPI

        from scripts.web import create_app
        app = create_app()
        assert isinstance(app, FastAPI)
