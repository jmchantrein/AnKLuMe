"""i18n — internationalisation anklume (§32)."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

_current_locale: str = ""
_catalogs: dict[str, dict] = {}

SUPPORTED_LOCALES = ("fr", "en")
DEFAULT_LOCALE = "fr"

_I18N_DIR = Path(__file__).resolve().parent


def get_locale() -> str:
    """Détecte la locale courante.

    Priorité : set_locale() > ANKLUME_LANG > LANG > fr.
    """
    if _current_locale:
        return _current_locale

    # ANKLUME_LANG
    env_lang = os.environ.get("ANKLUME_LANG", "")
    if env_lang:
        if env_lang in SUPPORTED_LOCALES:
            return env_lang
        return DEFAULT_LOCALE

    # LANG (ex: fr_FR.UTF-8 → fr)
    sys_lang = os.environ.get("LANG", "")
    if sys_lang:
        code = sys_lang.split("_")[0].split(".")[0]
        if code in SUPPORTED_LOCALES:
            return code

    return DEFAULT_LOCALE


def set_locale(locale: str) -> None:
    """Force la locale pour la session. Vide = reset."""
    global _current_locale
    _current_locale = locale


def _load_catalog(locale: str) -> dict:
    """Charge le YAML de traduction."""
    if locale in _catalogs:
        return _catalogs[locale]

    path = _I18N_DIR / f"{locale}.yml"
    if not path.is_file():
        return {}

    data = yaml.safe_load(path.read_text()) or {}
    _catalogs[locale] = data
    return data


def _resolve(catalog: dict, key: str) -> str | None:
    """Résout une clé pointée (ex: 'cli.init.created')."""
    parts = key.split(".")
    current = catalog
    for part in parts:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    if isinstance(current, str):
        return current
    return None


def t(key: str, **kwargs: object) -> str:
    """Traduit une clé avec interpolation.

    Clé absente → retourne la clé brute.
    Interpolation via str.format(**kwargs).
    """
    locale = get_locale()
    catalog = _load_catalog(locale)
    value = _resolve(catalog, key)
    if value is None:
        return key
    if kwargs:
        return value.format(**kwargs)
    return value


def _reset() -> None:
    """Réinitialise l'état interne (locale + cache). Usage tests."""
    global _current_locale
    _current_locale = ""
    _catalogs.clear()
