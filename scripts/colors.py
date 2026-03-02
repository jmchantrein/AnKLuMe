"""Shared color mappings for anklume trust levels.

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

# Trust level → Rich markup styles (for CLI tables)
TRUST_RICH_STYLES = {
    "admin": "bold blue",
    "trusted": "bold green",
    "semi-trusted": "bold yellow",
    "untrusted": "bold red",
    "disposable": "bold magenta",
}


def extract_ipv4(state: dict, default: str = "") -> str:
    """Extract first global IPv4 from Incus instance state (skipping lo)."""
    for nic, net in (state.get("network") or {}).items():
        if nic == "lo":
            continue
        for addr in net.get("addresses", []):
            if addr.get("family") == "inet" and addr.get("scope") == "global":
                return addr["address"]
    return default


def build_domain_map(infra: dict) -> dict:
    """Build machine_name -> (domain_name, domain_config) mapping from infra.yml."""
    result = {}
    for dname, dconf in (infra.get("domains") or {}).items():
        for mname in (dconf.get("machines") or {}):
            result[mname] = (dname, dconf)
    return result


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


def resolve_colors(trust_level):
    """Return {border, bg, tmux} using the active accessibility palette.

    Falls back to the hardcoded dicts above if accessibility module
    is not available or palette is 'default'.
    """
    try:
        from scripts.accessibility import get_trust_colors, load_accessibility
        settings = load_accessibility()
        if settings["color_palette"] != "default":
            return get_trust_colors(trust_level, settings["color_palette"])
    except (ImportError, KeyError, OSError):
        pass
    return {
        "border": TRUST_BORDER_COLORS.get(trust_level, "#30363d"),
        "bg": TRUST_BG_COLORS.get(trust_level, "#161b22"),
        "tmux": TRUST_TMUX_COLORS.get(trust_level, "default"),
    }
