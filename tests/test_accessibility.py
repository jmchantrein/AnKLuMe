"""Tests for scripts/accessibility.py — palettes and settings."""



class TestPalettes:
    def test_all_palettes_have_all_trust_levels(self):
        from scripts.accessibility import PALETTES

        trust_levels = ("admin", "trusted", "semi-trusted", "untrusted", "disposable")
        for name, pal in PALETTES.items():
            for trust in trust_levels:
                assert trust in pal, f"Palette '{name}' missing trust level '{trust}'"

    def test_all_palettes_have_required_keys(self):
        from scripts.accessibility import PALETTES

        for name, pal in PALETTES.items():
            for trust, colors in pal.items():
                assert "border" in colors, f"{name}/{trust} missing 'border'"
                assert "bg" in colors, f"{name}/{trust} missing 'bg'"
                assert "tmux" in colors, f"{name}/{trust} missing 'tmux'"

    def test_border_colors_are_hex(self):
        import re

        from scripts.accessibility import PALETTES
        for name, pal in PALETTES.items():
            for trust, colors in pal.items():
                assert re.match(r"^#[0-9a-fA-F]{6}$", colors["border"]), (
                    f"{name}/{trust} border '{colors['border']}' is not valid hex"
                )

    def test_default_palette_matches_colors_py(self):
        from scripts.accessibility import PALETTES
        from scripts.colors import TRUST_BORDER_COLORS

        for trust, expected in TRUST_BORDER_COLORS.items():
            assert PALETTES["default"][trust]["border"] == expected

    def test_colorblind_palettes_differ_from_default(self):
        from scripts.accessibility import PALETTES

        for name in ("colorblind-deutan", "colorblind-protan", "colorblind-tritan"):
            pal = PALETTES[name]
            default = PALETTES["default"]
            # At least one trust level must differ
            differs = any(
                pal[t]["border"] != default[t]["border"]
                for t in ("admin", "trusted", "semi-trusted", "untrusted", "disposable")
            )
            assert differs, f"Palette '{name}' is identical to default"


class TestWCAGContrast:
    @staticmethod
    def _luminance(hex_color):
        """Calculate relative luminance (WCAG 2.0)."""
        r, g, b = (int(hex_color[i:i+2], 16) / 255 for i in (1, 3, 5))
        def linearize(c):
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b)

    def _contrast_ratio(self, c1, c2):
        l1 = self._luminance(c1)
        l2 = self._luminance(c2)
        lighter = max(l1, l2)
        darker = min(l1, l2)
        return (lighter + 0.05) / (darker + 0.05)

    def test_border_on_bg_minimum_contrast(self):
        """Border colors must have at least 2.5:1 contrast against their bg.

        WCAG AA large text requires 3:1, but decorative borders on dark
        backgrounds are not text. 2.5:1 ensures visual distinction.
        """
        from scripts.accessibility import PALETTES

        for name, pal in PALETTES.items():
            for trust, colors in pal.items():
                ratio = self._contrast_ratio(colors["border"], colors["bg"])
                assert ratio >= 2.5, (
                    f"{name}/{trust}: border/bg contrast {ratio:.1f} < 2.5 "
                    f"(border={colors['border']}, bg={colors['bg']})"
                )


class TestSettings:
    def test_load_default(self, tmp_path, monkeypatch):
        monkeypatch.setattr("scripts.accessibility._SETTINGS_PATH", tmp_path / "missing.yml")
        from scripts.accessibility import load_accessibility
        settings = load_accessibility()
        assert settings["color_palette"] == "default"
        assert settings["tmux_coloring"] == "full"
        assert settings["dyslexia_mode"] is False

    def test_roundtrip(self, tmp_path, monkeypatch):
        settings_path = tmp_path / "accessibility.yml"
        monkeypatch.setattr("scripts.accessibility._SETTINGS_PATH", settings_path)
        from scripts.accessibility import load_accessibility, save_accessibility

        settings = {"color_palette": "colorblind-deutan", "tmux_coloring": "title-only", "dyslexia_mode": True}
        save_accessibility(settings)
        loaded = load_accessibility()
        assert loaded["color_palette"] == "colorblind-deutan"
        assert loaded["tmux_coloring"] == "title-only"
        assert loaded["dyslexia_mode"] is True

    def test_get_trust_colors_default(self):
        from scripts.accessibility import get_trust_colors
        colors = get_trust_colors("admin", "default")
        assert colors["border"] == "#3333ff"

    def test_get_trust_colors_colorblind(self):
        from scripts.accessibility import get_trust_colors
        colors = get_trust_colors("admin", "colorblind-deutan")
        assert colors["border"] == "#0077bb"

    def test_get_trust_colors_unknown(self):
        from scripts.accessibility import get_trust_colors
        colors = get_trust_colors("unknown-level", "default")
        assert "border" in colors  # fallback


class TestDyslexiaCSS:
    def test_css_includes_opendyslexic(self):
        from scripts.accessibility import get_dyslexia_css
        css = get_dyslexia_css()
        assert "OpenDyslexic" in css
        assert "line-height" in css
        assert "letter-spacing" in css
