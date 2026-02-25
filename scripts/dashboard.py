#!/usr/bin/env python3
"""anklume web dashboard — live infrastructure status.

Single-file web dashboard using FastAPI and htmx (loaded from CDN) for
reactive updates.

Endpoints:
    GET /           — Main dashboard page
    GET /api/status — JSON: instances, networks, projects
    GET /api/html   — HTML fragment for htmx polling
    GET /api/infra  — JSON: parsed infra.yml

Usage:
    python3 scripts/dashboard.py [--port 8888] [--host 0.0.0.0]
    make dashboard

Phase 21: Desktop Integration
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

sys.path.insert(0, str(Path(__file__).resolve().parent))

# ── Trust level colors (shared with console.py, desktop-config.py) ──

TRUST_COLORS = {
    "admin": {"border": "#3333ff", "bg": "#0a0a2a", "label": "blue"},
    "trusted": {"border": "#33cc33", "bg": "#0a1a0a", "label": "green"},
    "semi-trusted": {"border": "#cccc33", "bg": "#1a1a0a", "label": "yellow"},
    "untrusted": {"border": "#cc3333", "bg": "#1a0a0a", "label": "red"},
    "disposable": {"border": "#cc33cc", "bg": "#1a0a1a", "label": "magenta"},
}


# ── Data fetchers ────────────────────────────────────────────────


def fetch_instances():
    """Fetch all instances from Incus."""
    result = subprocess.run(
        ["incus", "list", "--all-projects", "--format", "json"],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        return []
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return []


def fetch_networks():
    """Fetch anklume networks from Incus."""
    result = subprocess.run(
        ["incus", "network", "list", "--format", "json"],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        return []
    try:
        nets = json.loads(result.stdout)
        return [n for n in nets if n.get("name", "").startswith("net-")]
    except json.JSONDecodeError:
        return []


def fetch_projects():
    """Fetch Incus projects."""
    result = subprocess.run(
        ["incus", "project", "list", "--format", "json"],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        return []
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return []


def load_infra_yml():
    """Load infra.yml if available."""
    for path in [Path("infra.yml"), Path("infra/base.yml")]:
        if path.exists():
            import yaml
            with open(path) as f:
                return yaml.safe_load(f) or {}
    return {}


def infer_trust_level(domain_name, domain_config):
    """Infer trust level (same logic as console.py)."""
    trust = domain_config.get("trust_level")
    if trust:
        return trust
    if "admin" in domain_name.lower() or "anklume" in domain_name.lower():
        return "admin"
    if domain_config.get("ephemeral", False):
        return "disposable"
    return "trusted"


def build_status():
    """Build complete status payload."""
    instances = fetch_instances()
    networks = fetch_networks()
    infra = load_infra_yml()

    # Enrich instances with domain info
    domain_map = {}
    for dname, dconfig in infra.get("domains", {}).items():
        trust = infer_trust_level(dname, dconfig)
        for mname in dconfig.get("machines", {}):
            domain_map[mname] = {
                "domain": dname,
                "trust_level": trust,
                "colors": TRUST_COLORS.get(trust, TRUST_COLORS["trusted"]),
            }

    enriched = []
    for inst in instances:
        name = inst.get("name", "")
        info = domain_map.get(name, {})
        # Extract first non-lo IPv4
        ip = ""
        for net_name, net in inst.get("state", {}).get("network", {}).items():
            if net_name == "lo":
                continue
            for addr in net.get("addresses", []):
                if addr.get("family") == "inet":
                    ip = addr["address"]
                    break
            if ip:
                break
        enriched.append({
            "name": name,
            "status": inst.get("status", "Unknown"),
            "type": inst.get("type", ""),
            "project": inst.get("project", "default"),
            "ip": ip,
            "domain": info.get("domain", inst.get("project", "")),
            "trust_level": info.get("trust_level", ""),
            "colors": info.get("colors", {}),
        })

    return {
        "instances": enriched,
        "networks": [
            {"name": n.get("name", ""), "type": n.get("type", ""),
             "config": {k: v for k, v in n.get("config", {}).items()
                        if k.startswith("ipv4")}}
            for n in networks
        ],
        "policies": infra.get("network_policies", []),
        "project_name": infra.get("project_name", ""),
    }


# ── HTML template ────────────────────────────────────────────────

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>anklume Dashboard</title>
<script src="https://unpkg.com/htmx.org@2.0.4"></script>
<style>
  :root { --bg: #0d1117; --fg: #c9d1d9; --card: #161b22; --border: #30363d; }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', monospace;
         background: var(--bg); color: var(--fg); padding: 20px; }
  h1 { color: #58a6ff; margin-bottom: 20px; }
  h2 { color: #8b949e; margin: 20px 0 10px; font-size: 14px; text-transform: uppercase; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
  .card { background: var(--card); border: 2px solid var(--border); border-radius: 8px;
          padding: 16px; transition: border-color 0.2s; }
  .card:hover { border-color: #58a6ff; }
  .status { display: inline-block; width: 8px; height: 8px; border-radius: 50%;
            margin-right: 6px; }
  .status.running { background: #3fb950; }
  .status.stopped { background: #f85149; }
  .name { font-weight: bold; font-size: 16px; }
  .meta { color: #8b949e; font-size: 12px; margin-top: 4px; }
  .domain-badge { display: inline-block; padding: 2px 8px; border-radius: 4px;
                  font-size: 11px; font-weight: bold; margin-left: 8px; }
  .net-card { display: flex; justify-content: space-between; align-items: center; }
  .policy { background: var(--card); border: 1px solid var(--border); border-radius: 6px;
            padding: 8px 12px; margin: 4px 0; font-size: 13px; }
  .policy .arrow { color: #58a6ff; margin: 0 8px; }
  .refresh-info { color: #484f58; font-size: 11px; text-align: right; margin-top: 8px; }
  .empty { color: #484f58; font-style: italic; padding: 20px; }
</style>
</head>
<body>
<h1>anklume Dashboard</h1>
<div id="content" hx-get="/api/html" hx-trigger="load, every 5s" hx-swap="innerHTML">
  <p class="empty">Loading...</p>
</div>
<p class="refresh-info">Auto-refresh every 5s via htmx</p>
</body>
</html>
"""


def render_status_html(status):
    """Render status as HTML fragment for htmx."""
    parts = []

    # Instances
    parts.append("<h2>Instances</h2>")
    if status["instances"]:
        parts.append('<div class="grid">')
        for inst in sorted(status["instances"], key=lambda x: (x["domain"], x["name"])):
            status_class = "running" if inst["status"] == "Running" else "stopped"
            border_color = inst.get("colors", {}).get("border", "#30363d")
            badge_bg = inst.get("colors", {}).get("border", "#30363d")
            trust = inst.get("trust_level", "")
            parts.append(
                f'<div class="card" style="border-left: 4px solid {border_color}">'
                f'<div><span class="status {status_class}"></span>'
                f'<span class="name">{inst["name"]}</span>'
            )
            if trust:
                parts.append(
                    f'<span class="domain-badge" style="background:{badge_bg};color:#fff">'
                    f'{inst["domain"]}</span>'
                )
            parts.append("</div>")
            parts.append(
                f'<div class="meta">{inst["type"]} | {inst["status"]} | '
                f'{inst["ip"] or "no IP"} | project: {inst["project"]}</div>'
            )
            parts.append("</div>")
        parts.append("</div>")
    else:
        parts.append('<p class="empty">No instances found</p>')

    # Networks
    parts.append("<h2>Networks</h2>")
    if status["networks"]:
        parts.append('<div class="grid">')
        for net in status["networks"]:
            subnet = net.get("config", {}).get("ipv4.address", "")
            parts.append(
                f'<div class="card net-card">'
                f'<span class="name">{net["name"]}</span>'
                f'<span class="meta">{subnet}</span>'
                f"</div>"
            )
        parts.append("</div>")
    else:
        parts.append('<p class="empty">No anklume networks found</p>')

    # Network Policies
    parts.append("<h2>Network Policies</h2>")
    policies = status.get("policies", [])
    if policies:
        for pol in policies:
            desc = pol.get("description", "")
            src = pol.get("from", "?")
            dst = pol.get("to", "?")
            ports = pol.get("ports", "all")
            if isinstance(ports, list):
                ports = ", ".join(str(p) for p in ports)
            parts.append(
                f'<div class="policy">'
                f'{desc}: <strong>{src}</strong>'
                f'<span class="arrow">&rarr;</span>'
                f'<strong>{dst}</strong> (ports: {ports})'
                f"</div>"
            )
    else:
        parts.append('<p class="empty">No network policies (all inter-domain traffic blocked)</p>')

    return "\n".join(parts)


# ── FastAPI application ──────────────────────────────────────────

app = FastAPI(title="anklume Dashboard")


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve main dashboard page."""
    return HTML_TEMPLATE


@app.get("/api/status")
async def api_status():
    """Return full status as JSON."""
    return build_status()


@app.get("/api/html", response_class=HTMLResponse)
async def api_html():
    """Return status as HTML fragment for htmx polling."""
    return render_status_html(build_status())


@app.get("/api/infra")
async def api_infra():
    """Return parsed infra.yml as JSON."""
    return load_infra_yml()


# ── Entry point ──────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="anklume web dashboard")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8888, help="Port (default: 8888)")
    args = parser.parse_args()

    print(f"anklume Dashboard: http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
