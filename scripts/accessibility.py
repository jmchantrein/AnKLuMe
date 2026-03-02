"""Accessibility color palettes and settings for anklume.

Provides colorblind-safe palettes, dyslexia mode, and high-contrast options.
Settings persist in ~/.anklume/accessibility.yml.
"""

from pathlib import Path

import yaml

# ── Palettes ──────────────────────────────────────────────
# Each palette maps trust_level -> {border, bg, tmux}

PALETTES = {
    "default": {
        "admin": {"border": "#3333ff", "bg": "#0a0a2a", "tmux": "colour17"},
        "trusted": {"border": "#33cc33", "bg": "#0a1a0a", "tmux": "colour22"},
        "semi-trusted": {"border": "#cccc33", "bg": "#1a1a0a", "tmux": "colour58"},
        "untrusted": {"border": "#cc3333", "bg": "#1a0a0a", "tmux": "colour52"},
        "disposable": {"border": "#cc33cc", "bg": "#1a0a1a", "tmux": "colour53"},
    },
    "colorblind-deutan": {
        "admin": {"border": "#0077bb", "bg": "#001a33", "tmux": "colour25"},
        "trusted": {"border": "#009988", "bg": "#001a1a", "tmux": "colour30"},
        "semi-trusted": {"border": "#ee7733", "bg": "#1a0f00", "tmux": "colour208"},
        "untrusted": {"border": "#cc3311", "bg": "#1a0500", "tmux": "colour160"},
        "disposable": {"border": "#ee3377", "bg": "#1a0011", "tmux": "colour161"},
    },
    "colorblind-protan": {
        "admin": {"border": "#0077bb", "bg": "#001a33", "tmux": "colour25"},
        "trusted": {"border": "#33bbee", "bg": "#001a2a", "tmux": "colour74"},
        "semi-trusted": {"border": "#ee7733", "bg": "#1a0f00", "tmux": "colour208"},
        "untrusted": {"border": "#cc3311", "bg": "#1a0500", "tmux": "colour160"},
        "disposable": {"border": "#ee3377", "bg": "#1a0011", "tmux": "colour161"},
    },
    "colorblind-tritan": {
        "admin": {"border": "#0077bb", "bg": "#001a33", "tmux": "colour25"},
        "trusted": {"border": "#009988", "bg": "#001a1a", "tmux": "colour30"},
        "semi-trusted": {"border": "#ddaa33", "bg": "#1a1200", "tmux": "colour178"},
        "untrusted": {"border": "#cc3311", "bg": "#1a0500", "tmux": "colour160"},
        "disposable": {"border": "#aa3377", "bg": "#1a0011", "tmux": "colour127"},
    },
    "high-contrast": {
        "admin": {"border": "#4444ff", "bg": "#000000", "tmux": "colour21"},
        "trusted": {"border": "#00ff00", "bg": "#000000", "tmux": "colour46"},
        "semi-trusted": {"border": "#ffff00", "bg": "#000000", "tmux": "colour226"},
        "untrusted": {"border": "#ff0000", "bg": "#000000", "tmux": "colour196"},
        "disposable": {"border": "#ff00ff", "bg": "#000000", "tmux": "colour201"},
    },
}

DEFAULT_SETTINGS = {
    "color_palette": "default",
    "tmux_coloring": "full",
    "dyslexia_mode": False,
}

_SETTINGS_PATH = Path.home() / ".anklume" / "accessibility.yml"


def load_accessibility() -> dict:
    """Load accessibility settings from ~/.anklume/accessibility.yml."""
    settings = dict(DEFAULT_SETTINGS)
    try:
        data = yaml.safe_load(_SETTINGS_PATH.read_text()) or {}
        for key in DEFAULT_SETTINGS:
            if key in data:
                settings[key] = data[key]
    except FileNotFoundError:
        pass
    return settings


def save_accessibility(settings: dict) -> None:
    """Save accessibility settings to ~/.anklume/accessibility.yml."""
    _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SETTINGS_PATH.write_text(yaml.dump(settings, default_flow_style=False))


def get_trust_colors(trust_level: str, palette: str | None = None) -> dict:
    """Return {border, bg, tmux} for a trust level using the active palette."""
    if palette is None:
        palette = load_accessibility()["color_palette"]
    pal = PALETTES.get(palette, PALETTES["default"])
    return pal.get(trust_level, {"border": "#30363d", "bg": "#161b22", "tmux": "default"})


def get_dyslexia_css() -> str:
    """Return CSS overrides for dyslexia-friendly rendering."""
    return (
        "@import url('https://fonts.googleapis.com/css2?family=OpenDyslexic&display=swap');\n"
        "body { font-family: 'OpenDyslexic', sans-serif !important;\n"
        "  line-height: 1.6 !important; letter-spacing: 0.05em !important; }\n"
        "pre, code { font-family: 'OpenDyslexic Mono', monospace !important; }\n"
    )
