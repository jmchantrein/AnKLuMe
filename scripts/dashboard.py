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
import html
import json
import subprocess
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

sys.path.insert(0, str(Path(__file__).resolve().parent))

from colors import build_domain_map, extract_ipv4, infer_trust_level  # noqa: E402
from web.theme import BASE_CSS, DASHBOARD_CSS, RESOURCE_CSS, trust_css  # noqa: E402

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
    """Load infra.yml if available, return {} on failure."""
    try:
        from psot.io import load_infra
        return load_infra("infra.yml") or {}
    except (FileNotFoundError, OSError):
        return {}


def build_status():
    """Build complete status payload."""
    instances = fetch_instances()
    networks = fetch_networks()
    infra = load_infra_yml()

    # Enrich instances with domain info
    raw_map = build_domain_map(infra)
    domain_map = {}
    for mname, (dname, dconf) in raw_map.items():
        trust = infer_trust_level(dname, dconf)
        domain_map[mname] = {
            "domain": dname,
            "trust_level": trust,
            "colors": trust_css(trust),
        }

    enriched = []
    for inst in instances:
        name = inst.get("name", "")
        info = domain_map.get(name, {})
        ip = extract_ipv4(inst.get("state", {}))
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

HTML_TEMPLATE = (
    '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">\n'
    "<title>anklume Dashboard</title>\n"
    '<script src="https://unpkg.com/htmx.org@2.0.4"></script>\n'
    f"<style>{BASE_CSS}\n{DASHBOARD_CSS}\n{RESOURCE_CSS}</style>\n"
    "</head><body>\n"
    "<h1>anklume Dashboard</h1>\n"
    '<div id="content" hx-get="/api/html" hx-trigger="load, every 5s"'
    ' hx-swap="innerHTML">\n'
    '  <p class="empty">Loading...</p>\n'
    "</div>\n"
    '<p class="refresh-info">Auto-refresh every 5s via htmx</p>\n'
    "</body></html>"
)


def _fetch_resources_html():
    """Fetch host resources and render as HTML widget."""
    try:
        from host_resources import collect_all, render_dashboard_data
        data = collect_all()
        return render_dashboard_data(data)
    except (ImportError, OSError, ValueError):
        return ""


def render_status_html(status):
    """Render status as HTML fragment for htmx."""
    parts = []

    # Host resources widget
    res_html = _fetch_resources_html()
    if res_html:
        parts.append(res_html)

    # Instances
    parts.append("<h2>Instances</h2>")
    if status["instances"]:
        parts.append('<div class="grid">')
        for inst in sorted(status["instances"], key=lambda x: (x["domain"], x["name"])):
            status_class = "running" if inst["status"] == "Running" else "stopped"
            border_color = html.escape(inst.get("colors", {}).get("border", "#30363d"))
            badge_bg = html.escape(inst.get("colors", {}).get("border", "#30363d"))
            trust = html.escape(inst.get("trust_level", ""))
            name = html.escape(inst["name"])
            domain = html.escape(inst.get("domain", ""))
            ip = html.escape(inst["ip"] or "no IP")
            itype = html.escape(inst["type"])
            istatus = html.escape(inst["status"])
            project = html.escape(inst["project"])
            parts.append(
                f'<div class="card" style="border-left: 4px solid {border_color}">'
                f'<div><span class="status {status_class}"></span>'
                f'<span class="name">{name}</span>'
            )
            if trust:
                parts.append(
                    f'<span class="domain-badge" style="background:{badge_bg};color:#fff">'
                    f'{domain}</span>'
                )
            parts.append("</div>")
            parts.append(
                f'<div class="meta">{itype} | {istatus} | '
                f'{ip} | project: {project}</div>'
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
            subnet = html.escape(net.get("config", {}).get("ipv4.address", ""))
            net_name = html.escape(net["name"])
            parts.append(
                f'<div class="card net-card">'
                f'<span class="name">{net_name}</span>'
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
            desc = html.escape(str(pol.get("description", "")))
            src = html.escape(str(pol.get("from", "?")))
            dst = html.escape(str(pol.get("to", "?")))
            ports = pol.get("ports", "all")
            if isinstance(ports, list):
                ports = html.escape(", ".join(str(p) for p in ports))
            else:
                ports = html.escape(str(ports))
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


@app.middleware("http")
async def security_headers(request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' https://unpkg.com; style-src 'self' 'unsafe-inline'"
    )
    return response


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
    """Return parsed infra.yml as JSON (localhost only — no auth)."""
    infra = load_infra_yml()
    # Strip sensitive fields before exposing
    for _dname, dconf in infra.get("domains", {}).items():
        for _mname, mconf in (dconf.get("machines") or {}).items():
            mconf.pop("config", None)
    return infra


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
