"""Shared CSS theme for anklume web applications.

Single source of truth for the dark theme used by dashboard, guide,
and learning platform. Extracted from dashboard.py and the former guide-server.py
to eliminate duplication.
"""

from scripts.colors import resolve_colors

# ── Base CSS (shared across all web apps) ───────────────────

BASE_CSS = """\
:root {
  --bg: #0d1117; --fg: #c9d1d9; --card: #161b22;
  --border: #30363d; --accent: #58a6ff; --success: #3fb950;
  --muted: #8b949e; --dim: #484f58;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', monospace;
  background: var(--bg); color: var(--fg); padding: 20px;
}
h1 { color: var(--accent); margin-bottom: 8px; }
h2 {
  color: var(--muted); margin: 16px 0 8px;
  font-size: 14px; text-transform: uppercase;
}
.subtitle { color: var(--dim); margin-bottom: 20px; }
.card {
  background: var(--card); border: 2px solid var(--border);
  border-radius: 8px; padding: 16px; transition: border-color 0.2s;
}
.card:hover { border-color: var(--accent); }
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}
.nav { display: flex; gap: 12px; margin: 16px 0; }
.nav a { color: var(--accent); text-decoration: none; }
.nav a:hover { text-decoration: underline; }
.btn {
  background: #21262d; border: 1px solid var(--border); color: var(--fg);
  padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 13px;
}
.btn:hover { background: #30363d; }
pre.terminal {
  background: #010409; border: 1px solid var(--border);
  border-radius: 6px; padding: 12px; font-size: 13px;
  overflow-x: auto; white-space: pre-wrap;
}
.progress { background: #21262d; border-radius: 4px; height: 6px; margin: 16px 0; }
.progress-bar { background: var(--success); height: 6px; border-radius: 4px; }
.content {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 8px; padding: 20px; margin: 16px 0;
}
.empty { color: var(--dim); font-style: italic; padding: 20px; }
"""

# ── Terminal split-pane CSS (learning platform) ─────────────

TERMINAL_CSS = """\
.learn-layout {
  display: flex; height: calc(100vh - 120px); gap: 0;
}
.learn-content {
  flex: 1; overflow-y: auto; padding: 20px;
  border-right: 1px solid var(--border);
}
.learn-terminal {
  flex: 1; min-width: 400px; background: #000;
  display: flex; flex-direction: column;
}
.learn-terminal .xterm { flex: 1; }
.cmd-block {
  display: flex; align-items: center; gap: 8px;
  background: #010409; border: 1px solid var(--border);
  border-radius: 6px; padding: 8px 12px; margin: 8px 0;
  font-family: monospace; font-size: 13px;
}
.cmd-block code { flex: 1; color: var(--success); }
.cmd-block .run-btn {
  background: none; border: 1px solid var(--border); color: var(--accent);
  border-radius: 4px; padding: 2px 8px; cursor: pointer; font-size: 12px;
}
.cmd-block .run-btn:hover { background: #21262d; }
.learn-nav {
  display: flex; justify-content: space-between; align-items: center;
  padding: 8px 20px; border-top: 1px solid var(--border);
  background: var(--card);
}
"""

# ── Dashboard-specific CSS ──────────────────────────────────

DASHBOARD_CSS = """\
.status { display: inline-block; width: 8px; height: 8px; border-radius: 50%;
          margin-right: 6px; }
.status.running { background: var(--success); }
.status.stopped { background: #f85149; }
.name { font-weight: bold; font-size: 16px; }
.meta { color: var(--muted); font-size: 12px; margin-top: 4px; }
.domain-badge { display: inline-block; padding: 2px 8px; border-radius: 4px;
                font-size: 11px; font-weight: bold; margin-left: 8px; }
.net-card { display: flex; justify-content: space-between; align-items: center; }
.policy { background: var(--card); border: 1px solid var(--border); border-radius: 6px;
          padding: 8px 12px; margin: 4px 0; font-size: 13px; }
.policy .arrow { color: var(--accent); margin: 0 8px; }
.refresh-info { color: var(--dim); font-size: 11px; text-align: right; margin-top: 8px; }
"""

# ── Resource monitoring CSS ───────────────────────────────────

RESOURCE_CSS = """\
.resource-widget {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 8px; padding: 16px; margin-bottom: 16px;
}
.resource-bar {
  display: flex; align-items: center; gap: 12px; margin: 6px 0;
}
.resource-label {
  min-width: 100px; font-size: 13px; color: var(--fg);
}
.resource-track {
  flex: 1; background: #21262d; border-radius: 4px; height: 8px;
}
.resource-fill {
  height: 8px; border-radius: 4px; transition: width 0.3s;
}
.resource-models {
  margin-top: 8px; display: flex; gap: 8px; flex-wrap: wrap;
}
.resource-model {
  background: #21262d; border: 1px solid var(--border);
  border-radius: 4px; padding: 2px 8px; font-size: 12px; color: var(--muted);
}
"""

# ── Guide-specific CSS (chapter cards) ──────────────────────

GUIDE_CSS = """\
.chapters { display: grid; gap: 10px; }
.ch-card {
  background: var(--card); border: 2px solid var(--border);
  border-radius: 8px; padding: 16px; text-decoration: none;
  color: var(--fg); transition: border-color 0.2s; display: block;
}
.ch-card:hover { border-color: var(--accent); }
.ch-num { color: var(--accent); font-weight: bold; margin-right: 8px; }
.ch-title { font-weight: bold; font-size: 16px; }
.ch-desc { color: var(--muted); font-size: 13px; margin-top: 4px; }
"""


def trust_css(level: str, palette: str | None = None) -> dict[str, str]:
    """Return border/bg colors for a trust level, with palette support.

    Delegates to colors.resolve_colors() which handles accessibility
    palette loading. The ``palette`` parameter is accepted for backward
    compatibility but ignored (resolve_colors auto-detects the active
    palette from user settings).
    """
    colors = resolve_colors(level)
    return {"border": colors["border"], "bg": colors["bg"]}


def accessible_css(settings: dict | None = None) -> str:
    """Return extra CSS for accessibility (dyslexia, high-contrast)."""
    if settings is None:
        try:
            from scripts.accessibility import load_accessibility
            settings = load_accessibility()
        except (ImportError, OSError):
            return ""
    parts = []
    if settings.get("dyslexia_mode"):
        try:
            from scripts.accessibility import get_dyslexia_css
            parts.append(get_dyslexia_css())
        except (ImportError, KeyError):
            pass
    if settings.get("color_palette") == "high-contrast":
        parts.append(":root { --bg: #000; --fg: #fff; --card: #111;\n"
                     "  --border: #666; --muted: #ccc; }\n")
    return "\n".join(parts)
