"""Tests pour cli/_gui.py — commandes GUI (kwin rules, couleurs trust)."""

from __future__ import annotations

import configparser
from pathlib import Path
from unittest.mock import MagicMock, patch

from anklume.cli._gui import (
    _TITLE_PREFIX_C,
    TRUST_COLORS_HEX,
    _ensure_color_scheme,
    _ensure_title_lib,
    _hex_to_rgb,
    _install_kwin_rule,
    _push_title_lib,
    _title_prefix,
    _trust_rgb,
)


class TestTitlePrefix:
    """Tests pour _title_prefix (majuscules simples)."""

    def test_uppercase_conversion(self):
        """Convertit en majuscules."""
        assert _title_prefix("firefox") == "FIREFOX"

    def test_preserves_hyphens(self):
        """Les tirets sont préservés."""
        assert _title_prefix("perso-firefox") == "PERSO-FIREFOX"

    def test_digits_preserved(self):
        """Les chiffres restent identiques."""
        assert _title_prefix("vm42") == "VM42"

    def test_already_upper(self):
        """MAJUSCULES déjà en entrée : idempotent."""
        assert _title_prefix("ABC") == _title_prefix("abc")


class TestTrustColors:
    """Tests pour le mapping trust level → couleur."""

    def test_all_trust_levels_have_color(self):
        """Chaque trust level a une couleur associée."""
        expected = {"admin", "trusted", "semi-trusted", "untrusted", "disposable"}
        assert set(TRUST_COLORS_HEX.keys()) == expected

    def test_untrusted_is_not_orange(self):
        """Untrusted est violet (colorblind-safe), pas orange."""
        assert TRUST_COLORS_HEX["untrusted"] != "#ff8700"
        assert TRUST_COLORS_HEX["untrusted"] == "#9B59B6"

    def test_colors_from_models(self):
        """Les couleurs hex viennent de models.TRUST_COLORS."""
        from anklume.engine.models import TRUST_COLORS

        for level, hex_color in TRUST_COLORS_HEX.items():
            assert hex_color == TRUST_COLORS[level].hex

    def test_hex_to_rgb_conversion(self):
        """_hex_to_rgb convertit correctement #RRGGBB en R,G,B."""
        assert _hex_to_rgb("#ff0000") == "255,0,0"
        assert _hex_to_rgb("#0060ff") == "0,96,255"
        assert _hex_to_rgb("#5f5f5f") == "95,95,95"

    def test_trust_rgb_returns_correct_values(self):
        """_trust_rgb dérive correctement les RGB depuis les hex."""
        assert _trust_rgb("admin") == "255,0,0"
        assert _trust_rgb("trusted") == "0,95,175"
        assert _trust_rgb("semi-trusted") == "255,215,0"

    def test_trust_rgb_unknown_defaults_to_yellow(self):
        """Trust level inconnu → jaune par défaut."""
        assert _trust_rgb("unknown") == "255,215,0"

    def test_colors_are_hex(self):
        """Toutes les couleurs sont au format #RRGGBB."""
        for level, color in TRUST_COLORS_HEX.items():
            assert color.startswith("#"), f"{level}: {color} ne commence pas par #"
            assert len(color) == 7, f"{level}: {color} ne fait pas 7 caractères"

    def test_rgb_format_from_hex(self):
        """Tous les RGB dérivés sont au format R,G,B valide."""
        for level, hex_color in TRUST_COLORS_HEX.items():
            rgb = _hex_to_rgb(hex_color)
            parts = rgb.split(",")
            assert len(parts) == 3, f"{level}: {rgb} n'a pas 3 composantes"
            for p in parts:
                assert 0 <= int(p) <= 255, f"{level}: composante {p} hors limites"

    def test_admin_is_red(self):
        """Admin = rouge (danger maximal)."""
        assert TRUST_COLORS_HEX["admin"] == "#ff0000"
        assert _trust_rgb("admin") == "255,0,0"

    def test_trusted_is_blue(self):
        """Trusted = bleu."""
        assert TRUST_COLORS_HEX["trusted"] == "#005faf"

    def test_disposable_is_grey(self):
        """Disposable = gris."""
        assert TRUST_COLORS_HEX["disposable"] == "#5f5f5f"


class TestEnsureColorScheme:
    """Tests pour _ensure_color_scheme."""

    def test_creates_color_scheme_file(self, tmp_path: Path):
        """Crée un fichier .colors dans le bon répertoire."""
        name = _ensure_color_scheme("trusted", tmp_path)

        assert name == "anklume-trusted"
        scheme_file = tmp_path / ".local" / "share" / "color-schemes" / "anklume-trusted.colors"
        assert scheme_file.exists()

    def test_color_scheme_has_wm_section(self, tmp_path: Path):
        """Le color scheme contient [WM] avec activeBackground."""
        _ensure_color_scheme("admin", tmp_path)

        scheme_file = tmp_path / ".local" / "share" / "color-schemes" / "anklume-admin.colors"
        cs = configparser.ConfigParser()
        cs.optionxform = str
        cs.read(str(scheme_file))

        assert "WM" in cs
        assert cs["WM"]["activeBackground"] == "255,0,0"

    def test_color_scheme_has_name(self, tmp_path: Path):
        """Le color scheme contient le nom dans [General]."""
        _ensure_color_scheme("semi-trusted", tmp_path)

        schemes = tmp_path / ".local" / "share" / "color-schemes"
        scheme_file = schemes / "anklume-semi-trusted.colors"
        cs = configparser.ConfigParser()
        cs.optionxform = str
        cs.read(str(scheme_file))

        assert "semi-trusted" in cs["General"]["Name"]

    def test_unknown_trust_defaults_to_yellow(self, tmp_path: Path):
        """Trust level inconnu → RGB jaune par défaut."""
        _ensure_color_scheme("unknown-level", tmp_path)

        schemes = tmp_path / ".local" / "share" / "color-schemes"
        scheme_file = schemes / "anklume-unknown-level.colors"
        cs = configparser.ConfigParser()
        cs.optionxform = str
        cs.read(str(scheme_file))

        assert cs["WM"]["activeBackground"] == "255,215,0"

    def test_color_scheme_key_matches_filename(self, tmp_path: Path):
        """ColorScheme= dans [General] doit correspondre au nom du fichier."""
        _ensure_color_scheme("trusted", tmp_path)

        scheme_file = tmp_path / ".local" / "share" / "color-schemes" / "anklume-trusted.colors"
        cs = configparser.ConfigParser()
        cs.optionxform = str
        cs.read(str(scheme_file))

        assert cs["General"]["ColorScheme"] == "anklume-trusted"

    def test_header_section_has_trust_color(self, tmp_path: Path):
        """[Colors:Header] BackgroundNormal contient la couleur trust."""
        _ensure_color_scheme("admin", tmp_path)

        scheme_file = tmp_path / ".local" / "share" / "color-schemes" / "anklume-admin.colors"
        cs = configparser.ConfigParser()
        cs.optionxform = str
        cs.read(str(scheme_file))

        assert cs["Colors:Header"]["BackgroundNormal"] == "255,0,0"

    def test_header_inactive_section(self, tmp_path: Path):
        """[Colors:Header][Inactive] a une couleur atténuée."""
        _ensure_color_scheme("trusted", tmp_path)

        scheme_file = tmp_path / ".local" / "share" / "color-schemes" / "anklume-trusted.colors"
        cs = configparser.ConfigParser()
        cs.optionxform = str
        cs.read(str(scheme_file))

        # Inactive doit être une version atténuée du bleu (0,96,255)
        inactive_bg = cs["Colors:Header][Inactive"]["BackgroundNormal"]
        parts = [int(x) for x in inactive_bg.split(",")]
        assert parts[0] < 10  # R atténué de 0
        assert parts[1] < 96  # G atténué de 96
        assert parts[2] < 255  # B atténué de 255

    def test_foreground_adapts_to_luminance(self, tmp_path: Path):
        """Couleurs sombres → foreground blanc, couleurs claires → noir."""
        # Admin = rouge (255,0,0) → luminance ~76 → foreground blanc
        _ensure_color_scheme("admin", tmp_path)
        scheme_file = tmp_path / ".local" / "share" / "color-schemes" / "anklume-admin.colors"
        cs = configparser.ConfigParser()
        cs.optionxform = str
        cs.read(str(scheme_file))
        assert cs["WM"]["activeForeground"] == "255,255,255"

        # Semi-trusted = jaune (255,215,0) → luminance ~203 → foreground noir
        _ensure_color_scheme("semi-trusted", tmp_path)
        schemes = tmp_path / ".local" / "share" / "color-schemes"
        scheme_file2 = schemes / "anklume-semi-trusted.colors"
        cs2 = configparser.ConfigParser()
        cs2.optionxform = str
        cs2.read(str(scheme_file2))
        assert cs2["WM"]["activeForeground"] == "0,0,0"


class TestInstallKwinRule:
    """Tests pour _install_kwin_rule."""

    def _call(self, tmp_path: Path, instance: str, trust: str, wmclass: str):
        """Helper pour appeler _install_kwin_rule avec les bons patches."""
        with (
            patch("anklume.cli._gui._gui_user_home", return_value=tmp_path),
            patch("anklume.cli._gui.subprocess.run"),
        ):
            _install_kwin_rule(instance, trust, wmclass, 1000)

    def test_creates_rule_file(self, tmp_path: Path):
        """Crée le fichier kwinrulesrc avec la règle."""
        self._call(tmp_path, "perso-firefox", "trusted", "firefox")

        kwin_rules = tmp_path / ".config" / "kwinrulesrc"
        assert kwin_rules.exists()

        config = configparser.ConfigParser()
        config.optionxform = str
        config.read(str(kwin_rules))

        section = "anklume-perso-firefox"
        assert section in config
        assert config[section]["wmclass"] == "firefox"
        assert config[section]["decocolor"] == "anklume-trusted"
        assert config[section]["decocolorrule"] == "2"
        assert "trusted" in config[section]["Description"]

    def test_creates_color_scheme(self, tmp_path: Path):
        """Crée le color scheme KDE correspondant."""
        self._call(tmp_path, "perso-firefox", "trusted", "firefox")

        scheme = tmp_path / ".local" / "share" / "color-schemes" / "anklume-trusted.colors"
        assert scheme.exists()

    def test_updates_general_count(self, tmp_path: Path):
        """Met à jour le compteur dans [General]."""
        self._call(tmp_path, "perso-firefox", "trusted", "firefox")

        kwin_rules = tmp_path / ".config" / "kwinrulesrc"
        config = configparser.ConfigParser()
        config.optionxform = str
        config.read(str(kwin_rules))

        assert config["General"]["count"] == "1"
        assert "anklume-perso-firefox" in config["General"]["rules"]

    def test_multiple_rules(self, tmp_path: Path):
        """Deux instances → deux règles, compteur incrémenté."""
        self._call(tmp_path, "perso-firefox", "trusted", "firefox")
        self._call(tmp_path, "pro-dev", "semi-trusted", "konsole")

        kwin_rules = tmp_path / ".config" / "kwinrulesrc"
        config = configparser.ConfigParser()
        config.optionxform = str
        config.read(str(kwin_rules))

        assert config["General"]["count"] == "2"
        rules = config["General"]["rules"].split(",")
        assert "anklume-perso-firefox" in rules
        assert "anklume-pro-dev" in rules

        assert config["anklume-perso-firefox"]["decocolor"] == "anklume-trusted"
        assert config["anklume-pro-dev"]["decocolor"] == "anklume-semi-trusted"

    def test_updates_existing_rule(self, tmp_path: Path):
        """Mise à jour d'une règle existante (même instance, trust changé)."""
        self._call(tmp_path, "perso-firefox", "trusted", "firefox")
        self._call(tmp_path, "perso-firefox", "admin", "firefox")

        kwin_rules = tmp_path / ".config" / "kwinrulesrc"
        config = configparser.ConfigParser()
        config.optionxform = str
        config.read(str(kwin_rules))

        # Compteur ne doit pas doubler
        assert config["General"]["count"] == "1"
        # Color scheme mis à jour
        assert config["anklume-perso-firefox"]["decocolor"] == "anklume-admin"

    def test_preserves_existing_rules(self, tmp_path: Path):
        """Les règles KDE existantes (non-anklume) sont préservées."""
        kwin_rules = tmp_path / ".config" / "kwinrulesrc"
        kwin_rules.parent.mkdir(parents=True)

        # Écrire une règle existante
        config = configparser.ConfigParser()
        config.optionxform = str
        config["General"] = {"count": "1", "rules": "my-custom-rule"}
        config["my-custom-rule"] = {"Description": "Ma règle perso", "wmclass": "firefox"}
        with open(kwin_rules, "w") as f:
            config.write(f)

        self._call(tmp_path, "perso-firefox", "trusted", "firefox")

        config2 = configparser.ConfigParser()
        config2.optionxform = str
        config2.read(str(kwin_rules))

        # Règle existante préservée
        assert "my-custom-rule" in config2
        assert config2["my-custom-rule"]["Description"] == "Ma règle perso"
        # Nouvelle règle ajoutée
        assert "anklume-perso-firefox" in config2
        assert config2["General"]["count"] == "2"

    def test_reloads_kwin(self, tmp_path: Path):
        """Appelle qdbus6 pour reconfigurer kwin."""
        with (
            patch("anklume.cli._gui._gui_user_home", return_value=tmp_path),
            patch("anklume.cli._gui.subprocess.run") as mock_run,
        ):
            _install_kwin_rule("test", "trusted", "firefox", 1000)

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "qdbus6" in cmd
        assert "org.kde.KWin.reconfigure" in cmd

    def test_description_contains_instance_and_trust(self, tmp_path: Path):
        """La description contient le nom de l'instance et le trust level."""
        self._call(tmp_path, "perso-firefox", "trusted", "firefox")

        kwin_rules = tmp_path / ".config" / "kwinrulesrc"
        config = configparser.ConfigParser()
        config.optionxform = str
        config.read(str(kwin_rules))

        desc = config["anklume-perso-firefox"]["Description"]
        assert "perso-firefox" in desc
        assert "trusted" in desc


class TestTitlePrefixLib:
    """Tests pour le mécanisme LD_PRELOAD de préfixe titre."""

    def test_c_source_contains_xdg_toplevel(self):
        """Le source C intercepte xdg_toplevel."""
        assert "xdg_toplevel" in _TITLE_PREFIX_C

    def test_c_source_intercepts_both_apis(self):
        """Intercepte marshal_array_flags (GTK4/Qt6) et marshal_array (GTK3)."""
        assert "wl_proxy_marshal_array_flags" in _TITLE_PREFIX_C
        assert "wl_proxy_marshal_array" in _TITLE_PREFIX_C

    def test_c_source_reads_env_var(self):
        """Lit ANKLUME_TITLE_PREFIX depuis l'environnement."""
        assert "ANKLUME_TITLE_PREFIX" in _TITLE_PREFIX_C

    def test_ensure_title_lib_compiles(self, tmp_path: Path):
        """Compile la lib .so si gcc est disponible."""
        with patch(
            "anklume.cli._gui.Path.home", return_value=tmp_path,
        ):
            result = _ensure_title_lib()

        if result is not None:
            assert result.exists()
            assert result.suffix == ".so"
        # Si gcc absent, result est None (acceptable)

    def test_ensure_title_lib_caches(self, tmp_path: Path):
        """Ne recompile pas si le .so existe déjà."""
        lib_dir = tmp_path / ".local" / "share" / "anklume"
        lib_dir.mkdir(parents=True)
        lib_file = lib_dir / "libtitle-prefix.so"
        lib_file.write_bytes(b"fake-elf")

        with patch(
            "anklume.cli._gui.Path.home", return_value=tmp_path,
        ):
            result = _ensure_title_lib()

        assert result == lib_file
        assert result.read_bytes() == b"fake-elf"  # pas recompilé

    def test_push_sends_base64_to_container(self):
        """Pousse le .so dans le conteneur via base64."""
        import tempfile

        driver = MagicMock()
        with tempfile.NamedTemporaryFile(suffix=".so", delete=False) as f:
            f.write(b"\x7fELF-fake-content")
            lib_path = Path(f.name)
        try:
            result = _push_title_lib(driver, "inst", "proj", lib_path)
        finally:
            lib_path.unlink()

        assert result is True
        driver.instance_exec.assert_called_once()
        cmd = driver.instance_exec.call_args[0][2]
        assert cmd[0] == "sh"
        script = cmd[2]
        assert "base64 -d" in script
        assert "/usr/local/lib/libanklume-title.so" in script

    def test_push_failure_returns_false(self):
        """Erreur push retourne False (non-fatal)."""
        import tempfile

        driver = MagicMock()
        driver.instance_exec.side_effect = RuntimeError("push failed")
        with tempfile.NamedTemporaryFile(suffix=".so", delete=False) as f:
            f.write(b"content")
            lib_path = Path(f.name)
        try:
            result = _push_title_lib(driver, "inst", "proj", lib_path)
        finally:
            lib_path.unlink()

        assert result is False
