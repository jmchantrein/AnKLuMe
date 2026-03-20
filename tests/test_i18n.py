"""Tests i18n — internationalisation (§32)."""

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

import yaml

# ---------------------------------------------------------------------------
# Fichiers de catalogue
# ---------------------------------------------------------------------------

I18N_DIR = Path(__file__).resolve().parent.parent / "src" / "anklume" / "i18n"


class TestCatalogFiles:
    """Vérifie que les fichiers de traduction existent et sont valides."""

    def test_fr_yml_exists(self) -> None:
        assert (I18N_DIR / "fr.yml").is_file()

    def test_en_yml_exists(self) -> None:
        assert (I18N_DIR / "en.yml").is_file()

    def test_fr_yml_valid_yaml(self) -> None:
        data = yaml.safe_load((I18N_DIR / "fr.yml").read_text())
        assert isinstance(data, dict)

    def test_en_yml_valid_yaml(self) -> None:
        data = yaml.safe_load((I18N_DIR / "en.yml").read_text())
        assert isinstance(data, dict)

    def test_catalogs_same_keys(self) -> None:
        """fr.yml et en.yml doivent avoir les mêmes clés."""
        fr = yaml.safe_load((I18N_DIR / "fr.yml").read_text())
        en = yaml.safe_load((I18N_DIR / "en.yml").read_text())

        def _collect_keys(d: dict, prefix: str = "") -> set[str]:
            keys: set[str] = set()
            for k, v in d.items():
                full = f"{prefix}.{k}" if prefix else k
                if isinstance(v, dict):
                    keys.update(_collect_keys(v, full))
                else:
                    keys.add(full)
            return keys

        fr_keys = _collect_keys(fr)
        en_keys = _collect_keys(en)
        assert fr_keys == en_keys, f"Clés manquantes : {fr_keys ^ en_keys}"


# ---------------------------------------------------------------------------
# Module i18n
# ---------------------------------------------------------------------------


class TestGetLocale:
    """Détection automatique de la locale."""

    def test_default_is_fr(self) -> None:
        from anklume.i18n import get_locale, set_locale

        set_locale("")  # reset
        with mock.patch.dict(os.environ, {}, clear=True):
            # Enlever ANKLUME_LANG et LANG
            os.environ.pop("ANKLUME_LANG", None)
            os.environ.pop("LANG", None)
            assert get_locale() == "fr"

    def test_anklume_lang_env(self) -> None:
        from anklume.i18n import get_locale, set_locale

        set_locale("")
        with mock.patch.dict(os.environ, {"ANKLUME_LANG": "en"}):
            assert get_locale() == "en"

    def test_lang_env_extraction(self) -> None:
        from anklume.i18n import get_locale, set_locale

        set_locale("")
        with mock.patch.dict(os.environ, {"LANG": "fr_FR.UTF-8"}, clear=True):
            os.environ.pop("ANKLUME_LANG", None)
            assert get_locale() == "fr"

    def test_lang_env_en(self) -> None:
        from anklume.i18n import get_locale, set_locale

        set_locale("")
        with mock.patch.dict(os.environ, {"LANG": "en_US.UTF-8"}, clear=True):
            os.environ.pop("ANKLUME_LANG", None)
            assert get_locale() == "en"

    def test_unknown_locale_fallback_fr(self) -> None:
        from anklume.i18n import get_locale, set_locale

        set_locale("")
        with mock.patch.dict(os.environ, {"ANKLUME_LANG": "de"}):
            assert get_locale() == "fr"


class TestSetLocale:
    """Forçage de la locale."""

    def test_set_locale_overrides_env(self) -> None:
        from anklume.i18n import get_locale, set_locale

        set_locale("en")
        with mock.patch.dict(os.environ, {"ANKLUME_LANG": "fr"}):
            assert get_locale() == "en"
        set_locale("")  # cleanup

    def test_set_locale_empty_resets(self) -> None:
        from anklume.i18n import get_locale, set_locale

        set_locale("en")
        set_locale("")
        with mock.patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ANKLUME_LANG", None)
            os.environ.pop("LANG", None)
            assert get_locale() == "fr"


class TestTranslate:
    """Fonction t() — traduction et interpolation."""

    def test_simple_key_fr(self) -> None:
        from anklume.i18n import set_locale, t

        set_locale("fr")
        result = t("cli.init.created", directory="/home/test")
        assert "/home/test" in result
        assert "Projet" in result or "créé" in result

    def test_simple_key_en(self) -> None:
        from anklume.i18n import set_locale, t

        set_locale("en")
        result = t("cli.init.created", directory="/home/test")
        assert "/home/test" in result
        assert "Project" in result or "created" in result

    def test_missing_key_returns_key(self) -> None:
        from anklume.i18n import set_locale, t

        set_locale("fr")
        assert t("cle.totalement.inexistante") == "cle.totalement.inexistante"

    def test_interpolation_with_kwargs(self) -> None:
        from anklume.i18n import set_locale, t

        set_locale("fr")
        result = t("errors.domain_not_found", name="test-domain")
        assert "test-domain" in result

    def test_key_without_interpolation(self) -> None:
        from anklume.i18n import set_locale, t

        set_locale("fr")
        result = t("cli.apply.done", count=3)
        assert "3" in result

    def test_nested_key_resolution(self) -> None:
        from anklume.i18n import set_locale, t

        set_locale("fr")
        result = t("cli.apply.deploying", domain="test")
        assert isinstance(result, str)
        assert len(result) > 0
        assert result != "cli.apply.deploying"  # résolu

    def test_version_key(self) -> None:
        from anklume.i18n import set_locale, t

        set_locale("fr")
        result = t("cli.version", version="1.0.0")
        assert "1.0.0" in result

    def test_locale_switch_changes_output(self) -> None:
        from anklume.i18n import set_locale, t

        set_locale("fr")
        fr_result = t("cli.status.ok")
        set_locale("en")
        en_result = t("cli.status.ok")
        assert fr_result != en_result

    def test_t_no_kwargs_no_placeholders(self) -> None:
        from anklume.i18n import set_locale, t

        set_locale("fr")
        result = t("cli.destroy.done")
        assert isinstance(result, str)
        assert "{" not in result  # pas de placeholder non résolu


class TestLoadCatalog:
    """Chargement interne des catalogues."""

    def test_load_fr(self) -> None:
        from anklume.i18n import _load_catalog

        catalog = _load_catalog("fr")
        assert "cli" in catalog
        assert "errors" in catalog

    def test_load_en(self) -> None:
        from anklume.i18n import _load_catalog

        catalog = _load_catalog("en")
        assert "cli" in catalog
        assert "errors" in catalog

    def test_load_unknown_returns_empty(self) -> None:
        from anklume.i18n import _load_catalog

        catalog = _load_catalog("xx")
        assert catalog == {}


class TestResolve:
    """Résolution de clés pointées."""

    def test_resolve_simple(self) -> None:
        from anklume.i18n import _resolve

        catalog = {"a": {"b": {"c": "value"}}}
        assert _resolve(catalog, "a.b.c") == "value"

    def test_resolve_missing(self) -> None:
        from anklume.i18n import _resolve

        catalog = {"a": {"b": "val"}}
        assert _resolve(catalog, "a.c") is None

    def test_resolve_top_level(self) -> None:
        from anklume.i18n import _resolve

        catalog = {"key": "val"}
        assert _resolve(catalog, "key") == "val"
