"""Shared color mappings for AnKLuMe trust levels.

Used by desktop_config.py, console.py, and domain-exec.sh (via inline
references). Centralizes all trust-level → color mappings in one place.

Phase 29: Codebase Simplification
"""

# Trust level → hex color for borders (bright, visible on desktop)
TRUST_BORDER_COLORS = {
    "admin": "#3333ff",
    "trusted": "#33cc33",
    "semi-trusted": "#cccc33",
    "untrusted": "#cc3333",
    "disposable": "#cc33cc",
}

# Trust level → hex color for terminal backgrounds (dark, readable)
TRUST_BG_COLORS = {
    "admin": "#0a0a2a",
    "trusted": "#0a1a0a",
    "semi-trusted": "#1a1a0a",
    "untrusted": "#1a0a0a",
    "disposable": "#1a0a1a",
}

# Trust level → tmux 256-color codes (matching console.py)
TRUST_TMUX_COLORS = {
    "admin": "colour17",
    "trusted": "colour22",
    "semi-trusted": "colour58",
    "untrusted": "colour52",
    "disposable": "colour53",
}


def infer_trust_level(domain_name, domain_config):
    """Infer trust level from domain name and config.

    Checks 'trust_level' key first, then infers from domain name
    conventions: admin/anklume → admin, ephemeral → disposable,
    else trusted.
    """
    trust = domain_config.get("trust_level")
    if trust:
        return trust
    if "admin" in domain_name.lower() or "anklume" in domain_name.lower():
        return "admin"
    if domain_config.get("ephemeral", False):
        return "disposable"
    return "trusted"
