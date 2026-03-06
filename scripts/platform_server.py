#!/usr/bin/env python3
"""anklume learning platform — unified web server.

Split-pane: content left, ttyd terminal right (iframe). Clickable
commands inject into the terminal via ttyd's built-in WebSocket.

Routes: / (landing), /setup (persistence setup), /guide (chapters),
/guide/{n} (split-pane), /labs (placeholder).

Terminal: ttyd runs as a subprocess on a dedicated port; pages embed
it in an iframe. No custom PTY/WebSocket code needed.

Usage: python3 scripts/platform_server.py [--port 8890]
"""

import argparse
import html
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse

sys.path.insert(0, str(Path(__file__).resolve().parent))

from web.content import load_guide_sections  # noqa: E402
from web.html import command_block, nav_bar, page_wrap  # noqa: E402
from web.theme import GUIDE_CSS, TERMINAL_CSS  # noqa: E402

# ── ttyd management ──────────────────────────────────────────

TTYD_PORT = 7681
_ttyd_proc: subprocess.Popen | None = None


def _start_ttyd(port: int = TTYD_PORT) -> subprocess.Popen | None:
    """Start ttyd as a subprocess if not already running."""
    ttyd_bin = shutil.which("ttyd")
    if not ttyd_bin:
        print("WARNING: ttyd not found, terminal will not work")
        return None
    proc = subprocess.Popen(
        [ttyd_bin, "--port", str(port), "--writable",
         "--base-path", "/ttyd", "bash", "-l"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    # Wait briefly and verify ttyd is alive
    time.sleep(0.5)
    if proc.poll() is not None:
        print(f"ERROR: ttyd exited immediately (rc={proc.returncode})")
        return None
    print(f"ttyd started on port {port} (PID {proc.pid})")
    return proc


def _stop_ttyd() -> None:
    """Stop the ttyd subprocess."""
    global _ttyd_proc
    if _ttyd_proc and _ttyd_proc.poll() is None:
        _ttyd_proc.send_signal(signal.SIGTERM)
        _ttyd_proc.wait(timeout=5)
        print("ttyd stopped")
    _ttyd_proc = None


# ── FastAPI app ──────────────────────────────────────────────

from collections.abc import AsyncGenerator  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator:
    global _ttyd_proc
    _ttyd_proc = _start_ttyd()
    yield
    _stop_ttyd()


app = FastAPI(title="anklume Learn", lifespan=lifespan)


def _detect_lang() -> str:
    """Detect system language: 'fr' or 'en'."""
    # Check LANG, LC_ALL, then keyboard layout as fallback
    for var in ("LANG", "LC_ALL", "LC_MESSAGES", "LANGUAGE"):
        val = os.environ.get(var, "")
        if val and val not in ("C", "POSIX"):
            return "fr" if val.startswith("fr") else "en"
    # Fallback: check keyboard layout (live ISO sets KEYMAP=fr)
    try:
        vconsole = Path("/etc/vconsole.conf").read_text()
        if "KEYMAP=fr" in vconsole:
            return "fr"
    except OSError:
        pass
    return "en"


def get_lang(request: Request) -> str:
    """Get language from ?lang= query param, cookie, or system default."""
    override = request.query_params.get("lang", "")
    if override in ("fr", "en"):
        return override
    cookie = request.cookies.get("lang", "")
    if cookie in ("fr", "en"):
        return cookie
    return _detect_lang()


@app.middleware("http")
async def lang_cookie(request, call_next):
    """Persist language choice in a cookie."""
    response = await call_next(request)
    lang = request.query_params.get("lang", "")
    if lang in ("fr", "en"):
        response.set_cookie("lang", lang, max_age=86400 * 365, httponly=True)
    elif not request.cookies.get("lang"):
        # First visit: set cookie from system detection
        response.set_cookie("lang", _detect_lang(), max_age=86400 * 365, httponly=True)
    return response


@app.middleware("http")
async def security_headers(request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "connect-src 'self' ws://localhost:*"
    )
    return response

_sections = load_guide_sections()
_guide = _sections[0] if _sections else None

# ── JS: xterm.js ↔ ttyd WebSocket bridge ────────────────────

TTYD_TERMINAL_JS = (
    "<script>\n"
    "(function() {\n"
    "  var el = document.getElementById('terminal');\n"
    "  if (!el) return;\n"
    "  var term = new Terminal({\n"
    "    cursorBlink: true, fontSize: 14,\n"
    "    fontFamily: \"'JetBrains Mono','Fira Code','Cascadia Code',monospace\",\n"
    "    theme: {background:'#0d1117', foreground:'#c9d1d9', cursor:'#58a6ff'}\n"
    "  });\n"
    "  var fitAddon = new FitAddon.FitAddon();\n"
    "  term.loadAddon(fitAddon);\n"
    "  term.open(el);\n"
    "  setTimeout(function(){ fitAddon.fit(); }, 200);\n"
    "  term.write('\\x1b[33mConnecting to terminal...\\x1b[0m\\r\\n');\n"
    "\n"
    "  var enc = new TextEncoder();\n"
    "  var ws, attempts = 0, maxAttempts = 60;\n"
    "\n"
    "  function connect() {\n"
    "    attempts++;\n"
    f"    ws = new WebSocket('ws://'+location.hostname+':{TTYD_PORT}/ttyd/ws',['tty']);\n"
    "    ws.binaryType = 'arraybuffer';\n"
    "\n"
    "    ws.onopen = function() {\n"
    "      var d = fitAddon.proposeDimensions();\n"
    "      ws.send(JSON.stringify({\n"
    "        AuthToken:'', columns: d?d.cols:80, rows: d?d.rows:24\n"
    "      }));\n"
    "    };\n"
    "    ws.onmessage = function(ev) {\n"
    "      var data = new Uint8Array(ev.data);\n"
    "      if (String.fromCharCode(data[0])==='0') term.write(data.slice(1));\n"
    "    };\n"
    "    ws.onerror = function() {};\n"
    "    ws.onclose = function(ev) {\n"
    "      if (attempts < maxAttempts && ev.code !== 1000) {\n"
    "        term.write('\\x1b[33mRetrying ('+attempts+'/'+maxAttempts+')...\\x1b[0m\\r\\n');\n"
    "        setTimeout(connect, 3000);\n"
    "      } else if (attempts >= maxAttempts) {\n"
    "        term.write('\\r\\n\\x1b[31mTerminal connection failed after '+maxAttempts+' attempts.\\x1b[0m\\r\\n');\n"
    "        term.write('\\x1b[33mTerminal will reconnect after setup completes.\\x1b[0m\\r\\n');\n"
    "      }\n"
    "    };\n"
    "  }\n"
    "  connect();\n"
    "\n"
    "  term.onData(function(data) {\n"
    "    if (ws && ws.readyState===1) ws.send(enc.encode('0'+data));\n"
    "  });\n"
    "  term.onResize(function(s) {\n"
    "    if (ws && ws.readyState===1) ws.send(enc.encode('1'+JSON.stringify({columns:s.cols,rows:s.rows})));\n"
    "  });\n"
    "  window.addEventListener('resize', function(){ fitAddon.fit(); });\n"
    "  new ResizeObserver(function(){ fitAddon.fit(); }).observe(el);\n"
    "\n"
    "  window.runCmd = function(cmd) {\n"
    "    if (ws && ws.readyState===1) ws.send(enc.encode('0'+cmd+'\\r'));\n"
    "  };\n"
    "})();\n"
    "</script>"
)

# ── JS: draggable split handle + fullscreen toggle ──────────

SPLIT_FULLSCREEN_JS = (
    "<script>\n"
    "(function() {\n"
    "  var handle = document.querySelector('.split-handle');\n"
    "  var layout = document.querySelector('.learn-layout');\n"
    "  var content = document.querySelector('.learn-content');\n"
    "  var terminal = document.querySelector('.learn-terminal');\n"
    "  if (!handle || !layout) return;\n"
    "\n"
    "  // ── Draggable splitter ──\n"
    "  var dragging = false;\n"
    "  handle.addEventListener('mousedown', function(e) {\n"
    "    e.preventDefault(); dragging = true;\n"
    "    handle.classList.add('dragging');\n"
    "    document.body.style.cursor = 'col-resize';\n"
    "    document.body.style.userSelect = 'none';\n"
    "  });\n"
    "  document.addEventListener('mousemove', function(e) {\n"
    "    if (!dragging) return;\n"
    "    var rect = layout.getBoundingClientRect();\n"
    "    var pct = ((e.clientX - rect.left) / rect.width) * 100;\n"
    "    pct = Math.max(15, Math.min(85, pct));\n"
    "    content.style.width = pct + '%';\n"
    "    content.style.flex = 'none';\n"
    "    window.dispatchEvent(new Event('resize'));\n"
    "  });\n"
    "  document.addEventListener('mouseup', function() {\n"
    "    if (!dragging) return;\n"
    "    dragging = false;\n"
    "    handle.classList.remove('dragging');\n"
    "    document.body.style.cursor = '';\n"
    "    document.body.style.userSelect = '';\n"
    "  });\n"
    "\n"
    "  // ── Fullscreen toggle ──\n"
    "  window.toggleFs = function(target) {\n"
    "    var el = target === 'content' ? content : terminal;\n"
    "    if (el.classList.contains('fullscreen')) {\n"
    "      el.classList.remove('fullscreen');\n"
    "      var btn = document.querySelector('.fs-close');\n"
    "      if (btn) btn.remove();\n"
    "      window.dispatchEvent(new Event('resize'));\n"
    "      return;\n"
    "    }\n"
    "    el.classList.add('fullscreen');\n"
    "    var close = document.createElement('button');\n"
    "    close.className = 'fs-close';\n"
    "    close.textContent = '\\u2715 ESC';\n"
    "    close.onclick = function() { toggleFs(target); };\n"
    "    document.body.appendChild(close);\n"
    "    window.dispatchEvent(new Event('resize'));\n"
    "  };\n"
    "  document.addEventListener('keydown', function(e) {\n"
    "    if (e.key === 'Escape') {\n"
    "      var fs = document.querySelector('.fullscreen');\n"
    "      if (fs) {\n"
    "        fs.classList.remove('fullscreen');\n"
    "        var btn = document.querySelector('.fs-close');\n"
    "        if (btn) btn.remove();\n"
    "        window.dispatchEvent(new Event('resize'));\n"
    "      }\n"
    "    }\n"
    "  });\n"
    "\n"
    "  // ── Browser native fullscreen (both panels) ──\n"
    "  window.toggleFsBoth = function() {\n"
    "    if (document.fullscreenElement) {\n"
    "      document.exitFullscreen();\n"
    "    } else {\n"
    "      layout.requestFullscreen().catch(function(){});\n"
    "    }\n"
    "    setTimeout(function(){ window.dispatchEvent(new Event('resize')); }, 200);\n"
    "  };\n"
    "})();\n"
    "</script>"
)


POOL_CONF_JS = (
    "<script>\n"
    "function showPoolConf() {\n"
    "  var m = document.getElementById('confModal');\n"
    "  m.classList.add('show');\n"
    "  fetch('/pool-conf').then(function(r){\n"
    "    if(!r.ok) throw new Error(r.status);\n"
    "    return r.text();\n"
    "  }).then(function(t){\n"
    "    document.getElementById('confContent').textContent = t;\n"
    "  }).catch(function(){\n"
    "    document.getElementById('confContent').textContent = 'Not found';\n"
    "  });\n"
    "}\n"
    "function hidePoolConf() {\n"
    "  document.getElementById('confModal').classList.remove('show');\n"
    "}\n"
    "document.addEventListener('keydown', function(e) {\n"
    "  if (e.key === 'Escape') hidePoolConf();\n"
    "});\n"
    "</script>"
)

INFRA_YML_JS = (
    "<script>\n"
    "function createInfraYml() {\n"
    "  var btn = event.target;\n"
    "  btn.disabled = true; btn.textContent = '...';\n"
    "  fetch('/create-infra-yml', {method:'POST'}).then(function(r){\n"
    "    return r.text();\n"
    "  }).then(function(t){\n"
    "    btn.textContent = t;\n"
    "    btn.style.borderColor = 'var(--success)';\n"
    "    btn.style.color = 'var(--success)';\n"
    "  }).catch(function(e){\n"
    "    btn.textContent = 'Error: ' + e;\n"
    "    btn.disabled = false;\n"
    "  });\n"
    "}\n"
    "</script>"
)

# ── Routes ──────────────────────────────────────────────────


LANDING_CSS = """\
.welcome-msg {
  color: var(--muted); font-size: 15px; margin-bottom: 24px;
  max-width: 600px; line-height: 1.5;
}
.home-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 12px;
  max-width: 600px;
}
.home-card {
  background: var(--card); border: 2px solid var(--border);
  border-radius: 8px; padding: 20px; text-decoration: none;
  color: var(--fg); transition: border-color 0.2s; display: block;
}
.home-card:hover { border-color: var(--accent); }
.home-card .card-title { font-weight: bold; font-size: 16px; margin-bottom: 6px; }
.home-card .card-desc { color: var(--muted); font-size: 13px; }
.home-card.primary { border-color: var(--accent); }
"""

SETUP_CSS = """\
.setup-info { padding: 20px; line-height: 1.6; }
.setup-info h2 { color: var(--accent); margin: 16px 0 8px; font-size: 18px;
  text-transform: none; }
.setup-info p { margin-bottom: 12px; }
.setup-info .warn {
  background: #2d1b00; border: 1px solid #d29922; border-radius: 6px;
  padding: 12px; margin: 12px 0; color: #d29922;
}
.setup-info .success {
  background: #0d2818; border: 1px solid var(--success); border-radius: 6px;
  padding: 12px; margin: 12px 0; color: var(--success);
}
.launch-btn {
  display: inline-block; background: var(--accent); color: #0d1117;
  border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer;
  font-size: 14px; font-weight: bold; margin: 12px 0;
}
.launch-btn:hover { opacity: 0.9; }
.view-conf-btn {
  display: inline-block; background: var(--card); color: var(--fg);
  border: 1px solid var(--border); padding: 8px 16px; border-radius: 6px;
  cursor: pointer; font-size: 13px; margin: 8px 8px 8px 0;
}
.view-conf-btn:hover { border-color: var(--accent); }
.conf-modal {
  display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
  background: rgba(0,0,0,0.7); z-index: 9999; align-items: center;
  justify-content: center;
}
.conf-modal.show { display: flex; }
.conf-modal-body {
  background: var(--bg); border: 1px solid var(--border); border-radius: 8px;
  padding: 20px; max-width: 600px; width: 90%; max-height: 80vh;
  overflow-y: auto;
}
.conf-modal-body pre {
  background: var(--card); padding: 12px; border-radius: 6px;
  font-size: 13px; overflow-x: auto; white-space: pre-wrap;
}
.conf-modal-close {
  float: right; background: none; border: none; color: var(--muted);
  font-size: 20px; cursor: pointer;
}
"""


_STRINGS = {
    "fr": {
        "welcome": (
            "Vos activit\u00e9s isol\u00e9es dans des compartiments "
            "\u00e9tanches \u2014 comme QubesOS, sur n\u2019importe quel Linux."
        ),
        "setup_title": "Configurer",
        "setup_desc": "Persistance &amp; stockage chiffr\u00e9",
        "explore_title": "Explorer",
        "explore_desc": "Tout dispara\u00eet \u00e0 l\u2019arr\u00eat",
        "guide_title": "D\u00e9couvrir",
        "guide_desc": "Tour guid\u00e9, 8 chapitres",
        "labs_title": "Pratiquer",
        "labs_desc": "Labs &amp; exercices (bient\u00f4t)",
        "lang_switch": "English",
        "lang_param": "en",
        "home": "Accueil",
        "setup_h2": "Persistance &amp; stockage chiffr\u00e9",
        "setup_intro": (
            "Cette \u00e9tape configure un espace de stockage persistant "
            "sur votre disque. Vos donn\u00e9es survivront aux "
            "red\u00e9marrages."
        ),
        "setup_backend": (
            "<strong>Backend</strong> : ZFS (recommand\u00e9), BTRFS, "
            "ou r\u00e9pertoire simple."
        ),
        "setup_luks": (
            "<strong>Chiffrement</strong> : LUKS optionnel pour "
            "prot\u00e9ger vos donn\u00e9es."
        ),
        "setup_launch": "Lancer la configuration",
        "setup_after": (
            "Apr\u00e8s configuration, passez au "
            '<a href="/guide" style="color:var(--success)">tour '
            "guid\u00e9</a> pour d\u00e9couvrir anklume."
        ),
        "explore_h2": "Mode exploration",
        "explore_intro": (
            "Tout fonctionne en RAM. Aucune donn\u00e9e ne sera "
            "sauvegard\u00e9e \u00e0 l\u2019arr\u00eat."
        ),
        "explore_warn": (
            "\u26a0 Les fichiers cr\u00e9\u00e9s seront perdus au "
            "red\u00e9marrage."
        ),
        "explore_launch": "Lancer",
        "explore_after": (
            "Apr\u00e8s configuration, explorez librement. "
            'Revenez pour le <a href="/guide" '
            'style="color:var(--success)">tour guid\u00e9</a>.'
        ),
        "resume_title": "Reprendre",
        "resume_desc": "Charger la configuration existante",
        "resume_h2": "Configuration existante d\u00e9tect\u00e9e",
        "resume_intro": (
            "Une installation anklume a \u00e9t\u00e9 trouv\u00e9e sur le "
            "disque persistant. Montez-la pour reprendre votre travail."
        ),
        "resume_launch": "Charger",
        "resume_after": (
            "Apr\u00e8s chargement, tout bascule vers anklume-instance. "
            "Le guide et les outils sont accessibles depuis le conteneur."
        ),
        "labs_empty": "Les labs seront disponibles dans une prochaine mise \u00e0 jour.",
    },
    "en": {
        "welcome": (
            "Your activities isolated in sealed compartments "
            "\u2014 like QubesOS, on any Linux."
        ),
        "setup_title": "Configure",
        "setup_desc": "Persistence &amp; encrypted storage",
        "explore_title": "Explore",
        "explore_desc": "Everything vanishes on shutdown",
        "guide_title": "Discover",
        "guide_desc": "Guided tour, 8 chapters",
        "labs_title": "Practice",
        "labs_desc": "Labs &amp; exercises (coming soon)",
        "lang_switch": "Fran\u00e7ais",
        "lang_param": "fr",
        "home": "Home",
        "setup_h2": "Persistence &amp; encrypted storage",
        "setup_intro": (
            "This step sets up persistent storage on your disk. "
            "Your data will survive reboots."
        ),
        "setup_backend": (
            "<strong>Backend</strong>: ZFS (recommended), BTRFS, "
            "or plain directory."
        ),
        "setup_luks": (
            "<strong>Encryption</strong>: optional LUKS to protect "
            "your data."
        ),
        "setup_launch": "Launch setup",
        "setup_after": (
            "After setup, proceed to the "
            '<a href="/guide" style="color:var(--success)">guided tour'
            "</a> to discover anklume."
        ),
        "explore_h2": "Explore mode",
        "explore_intro": (
            "Everything runs in RAM. No data will be saved "
            "on shutdown."
        ),
        "explore_warn": (
            "\u26a0 Files created will be lost on reboot."
        ),
        "explore_launch": "Launch",
        "explore_after": (
            "After setup, explore freely. Come back for the "
            '<a href="/guide" style="color:var(--success)">guided tour'
            "</a>."
        ),
        "resume_title": "Resume",
        "resume_desc": "Load existing configuration",
        "resume_h2": "Existing configuration detected",
        "resume_intro": (
            "An anklume installation was found on the persistent disk. "
            "Load it to resume your work."
        ),
        "resume_launch": "Load",
        "resume_after": (
            "After loading, everything switches to anklume-instance. "
            "The guide and tools are accessible from the container."
        ),
        "labs_empty": "Labs will be available in a future update.",
    },
}


POOL_CONF_PATH = Path("/mnt/anklume-persist/pool.conf")


def _is_live_iso() -> bool:
    """Detect if running from an anklume live ISO."""
    try:
        return "boot=anklume" in Path("/proc/cmdline").read_text()
    except OSError:
        return False


def _read_pool_conf() -> dict[str, str]:
    """Read pool.conf and return key-value pairs."""
    result: dict[str, str] = {}
    if not POOL_CONF_PATH.exists():
        return result
    for line in POOL_CONF_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip()
    return result


def _production_anklume_dir() -> str | None:
    """Return the production anklume directory if it exists, else None.

    Persistent storage is mounted on /home/anklume/data (ZFS dataset or
    BTRFS subvolume). For dir backend, /opt/anklume is used directly.
    """
    conf = _read_pool_conf()
    backend = conf.get("POOL_BACKEND", "")

    if backend in ("zfs", "btrfs"):
        d = "/home/anklume/data"
    else:
        return None  # dir backend uses /opt/anklume

    if Path(d).is_dir():
        return d
    return None


def _is_shell_command(line: str) -> bool:
    """Detect if an indented line is a shell command (vs YAML/config snippet)."""
    stripped = line.strip()
    if not stripped:
        return False
    # Shell commands start with known prefixes
    cmd_prefixes = (
        "anklume ", "incus ", "cat ", "sudo ", "cd ", "ls ", "grep ",
        "echo ", "bash ", "sh ", "curl ", "pip ", "apt ", "make ",
        "git ", "docker ", "systemctl ", "journalctl ",
    )
    return stripped.startswith(cmd_prefixes)


def _render_guide_text(text: str) -> str:
    """Render guide text with paragraph breaks and inline code blocks.

    - Splits on blank lines (\\n\\n) to create <p> paragraphs
    - Indented lines that look like shell commands → clickable command blocks
    - Indented lines that look like YAML/config → <pre> code blocks
    - Lines starting with '- ' or '• ' are rendered as list items
    """
    paragraphs = text.split("\n\n")
    parts: list[str] = []
    for para in paragraphs:
        if not para.strip():
            continue
        lines = para.split("\n")
        # Strip only trailing whitespace, preserve leading indentation
        lines = [line.rstrip() for line in lines]
        # Remove empty leading/trailing lines
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        if not lines:
            continue
        # Check if all lines are indented (code/config block)
        if all(line.startswith("  ") for line in lines):
            # If all are shell commands, render as clickable
            if all(_is_shell_command(line) for line in lines if line.strip()):
                for line in lines:
                    cmd = line.strip()
                    if cmd:
                        parts.append(command_block(cmd, clickable=True))
            else:
                # YAML/config block → render as <pre>
                code = "\n".join(html.escape(line[2:].rstrip()) for line in lines if line.strip())
                parts.append(f'<pre class="terminal">{code}</pre>')
            continue
        # Mixed content: process line by line
        buf: list[str] = []
        code_buf: list[str] = []
        for line in lines:
            if line.startswith("  ") and line.strip():
                if buf:
                    parts.append(f"<p>{' '.join(buf)}</p>")
                    buf = []
                if _is_shell_command(line):
                    if code_buf:
                        parts.append(f'<pre class="terminal">{chr(10).join(code_buf)}</pre>')
                        code_buf = []
                    parts.append(command_block(line.strip(), clickable=True))
                else:
                    code_buf.append(html.escape(line[2:].rstrip()))
            elif line.startswith("- ") or line.startswith("\u2022 "):
                if buf:
                    parts.append(f"<p>{' '.join(buf)}</p>")
                    buf = []
                if code_buf:
                    parts.append(f'<pre class="terminal">{chr(10).join(code_buf)}</pre>')
                    code_buf = []
                parts.append(f"<li>{html.escape(line[2:])}</li>")
            else:
                if code_buf:
                    parts.append(f'<pre class="terminal">{chr(10).join(code_buf)}</pre>')
                    code_buf = []
                buf.append(html.escape(line))
        if buf:
            parts.append(f"<p>{' '.join(buf)}</p>")
        if code_buf:
            parts.append(f'<pre class="terminal">{chr(10).join(code_buf)}</pre>')
    return "\n".join(parts)


def _terminal_div() -> str:
    """Return the terminal container div (xterm.js renders here)."""
    return '<div id="terminal"></div>'


def _has_existing_config() -> bool:
    """Check if an anklume configuration already exists (pool.conf present)."""
    return POOL_CONF_PATH.exists()


@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    """Landing page — adapts to whether a config already exists."""
    lang = get_lang(request)
    s = _STRINGS[lang]
    other = s["lang_param"]
    has_config = _has_existing_config()

    # Build the primary card based on state
    if has_config:
        # Existing config found → primary action is "Resume"
        primary_card = (
            f'<a class="home-card primary" href="/setup?mode=resume&lang={lang}">'
            f'<div class="card-title">{s["resume_title"]}</div>'
            f'<div class="card-desc">{s["resume_desc"]}</div></a>'
        )
    else:
        # Fresh install → primary action is "Configure"
        primary_card = (
            f'<a class="home-card primary" href="/setup?lang={lang}">'
            f'<div class="card-title">{s["setup_title"]}</div>'
            f'<div class="card-desc">{s["setup_desc"]}</div></a>'
        )

    body = (
        "<h1>anklume</h1>"
        f'<p class="welcome-msg">{s["welcome"]}</p>'
        f'<div style="margin-bottom:16px"><a href="/?lang={other}" '
        f'style="color:var(--muted);font-size:12px">{s["lang_switch"]}</a></div>'
        '<div class="home-grid">'
        + primary_card
        + f'<a class="home-card" href="/setup?mode=explore&lang={lang}">'
        f'<div class="card-title">{s["explore_title"]}</div>'
        f'<div class="card-desc">{s["explore_desc"]}</div></a>'
        f'<a class="home-card" href="/guide?lang={lang}">'
        f'<div class="card-title">{s["guide_title"]}</div>'
        f'<div class="card-desc">{s["guide_desc"]}</div></a>'
        f'<a class="home-card" href="/labs?lang={lang}">'
        f'<div class="card-title">{s["labs_title"]}</div>'
        f'<div class="card-desc">{s["labs_desc"]}</div></a>'
        "</div>"
    )
    return page_wrap(
        "anklume", body, extra_css=GUIDE_CSS + "\n" + LANDING_CSS,
        lang=lang,
    )


@app.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request, mode: str = "setup"):
    """Setup page: split-pane with instructions left, ttyd terminal right."""
    lang = get_lang(request)
    s = _STRINGS[lang]
    is_explore = mode == "explore"
    is_resume = mode == "resume"

    # pool.conf viewer button (shown if file exists)
    conf_btn = ""
    if POOL_CONF_PATH.exists():
        conf_label = (
            "Voir la configuration"
            if lang == "fr" else "View configuration"
        )
        conf_btn = (
            f'<button class="view-conf-btn" onclick="showPoolConf()">'
            f'{conf_label}</button>'
        )

    # Pool.conf modal (always rendered, shown by JS)
    conf_modal = (
        '<div class="conf-modal" id="confModal">'
        '<div class="conf-modal-body">'
        '<button class="conf-modal-close" onclick="hidePoolConf()">'
        '&times;</button>'
        '<h3>pool.conf</h3>'
        '<pre id="confContent">Loading...</pre>'
        '</div></div>'
    )

    if is_resume:
        info_html = (
            '<div class="setup-info">'
            f"<h2>{s['resume_h2']}</h2>"
            f"<p>{s['resume_intro']}</p>"
            + conf_btn
            + '<button class="launch-btn" '
            "onclick=\"runCmd('sudo /opt/anklume/scripts/start.sh --yes')\">"
            f"{s['resume_launch']}</button>"
            + f'<div class="success" style="margin-top:16px">'
            f'{s["resume_after"]}</div>'
            + conf_modal
            + "</div>"
        )
    elif is_explore:
        info_html = (
            '<div class="setup-info">'
            f"<h2>{s['explore_h2']}</h2>"
            f"<p>{s['explore_intro']}</p>"
            f'<div class="warn">{s["explore_warn"]}</div>'
            '<button class="launch-btn" '
            "onclick=\"runCmd('sudo /opt/anklume/scripts/start.sh "
            "--yes --backend dir')\">"
            f"{s['explore_launch']}</button>"
            + conf_btn
            + f'<div class="success" style="margin-top:16px">'
            f'{s["explore_after"]}</div>'
            + conf_modal
            + "</div>"
        )
    else:
        info_html = (
            '<div class="setup-info">'
            f"<h2>{s['setup_h2']}</h2>"
            f"<p>{s['setup_intro']}</p>"
            f"<p>{s['setup_backend']}</p>"
            f"<p>{s['setup_luks']}</p>"
            '<button class="launch-btn" '
            "onclick=\"runCmd('sudo /opt/anklume/scripts/start.sh')\">"
            f"{s['setup_launch']}</button>"
            + conf_btn
            + f'<div class="success" style="margin-top:16px">'
            f'{s["setup_after"]}</div>'
            + conf_modal
            + "</div>"
        )

    if is_resume:
        title = s["resume_title"]
    elif is_explore:
        title = s["explore_title"]
    else:
        title = s["setup_title"]
    nav_items = [(s["home"], "/")]
    body = (
        '<div class="split-wrapper">'
        '<div class="learn-layout">'
        '<div class="learn-content">'
        + info_html
        + "</div>"
        '<div class="split-handle"></div>'
        '<div class="learn-terminal">'
        + _terminal_div()
        + "</div></div>"
        '<div class="learn-nav">'
        + nav_bar(nav_items)
        + '<div class="fullscreen-bar">'
        + '<button class="fs-btn" onclick="toggleFs(\'content\')">'
        + "\u2922 Content</button>"
        + '<button class="fs-btn" onclick="toggleFs(\'terminal\')">'
        + "\u2922 Terminal</button>"
        + '<button class="fs-btn" onclick="toggleFsBoth()">'
        + "\u2922 Fullscreen</button>"
        + "</div>"
        + f"<span>{html.escape(title)}</span>"
        + "</div></div>"
    )
    css = GUIDE_CSS + "\n" + SETUP_CSS + "\n" + TERMINAL_CSS
    return page_wrap(
        f"anklume \u2014 {title}", body,
        extra_css=css,
        extra_js=(
            TTYD_TERMINAL_JS + "\n" + SPLIT_FULLSCREEN_JS
            + "\n" + POOL_CONF_JS
        ),
        xterm=True, lang=lang,
    )


@app.get("/pool-conf", response_class=PlainTextResponse)
async def pool_conf():
    """Return pool.conf content (non-sensitive, no LUKS passphrase)."""
    if not POOL_CONF_PATH.exists():
        raise HTTPException(status_code=404, detail="pool.conf not found")
    return POOL_CONF_PATH.read_text()


@app.post("/create-infra-yml", response_class=PlainTextResponse)
async def create_infra_yml(request: Request):
    """Create a starter infra.yml on the production anklume directory."""
    prod_dir = _production_anklume_dir()
    if not prod_dir:
        raise HTTPException(
            status_code=400,
            detail="No production anklume directory found. Run setup first.",
        )
    infra_path = Path(prod_dir) / "infra.yml"
    if infra_path.exists():
        return f"infra.yml already exists at {infra_path}"

    lang = get_lang(request)
    if lang == "fr":
        content = (
            "# infra.yml — Source de verite de votre infrastructure\n"
            "# Modifiez ce fichier puis: anklume sync && anklume domain apply\n\n"
            "project_name: mon-infra\n\n"
            "global:\n"
            "  addressing:\n"
            "    base_octet: 10\n"
            "    zone_base: 100\n"
            '  default_os_image: "images:debian/13"\n\n'
            "domains:\n"
            "  pro:\n"
            '    description: "Espace professionnel"\n'
            "    trust_level: semi-trusted\n"
            "    machines:\n"
            "      pro-dev:\n"
            '        description: "Developpement"\n'
            "        type: lxc\n"
            "        roles: [base_system]\n\n"
            "  perso:\n"
            '    description: "Espace personnel"\n'
            "    trust_level: trusted\n"
            "    machines:\n"
            "      perso-desktop:\n"
            '        description: "Bureau personnel"\n'
            "        type: lxc\n"
            "        roles: [base_system]\n"
        )
    else:
        content = (
            "# infra.yml — Source of truth for your infrastructure\n"
            "# Edit this file then: anklume sync && anklume domain apply\n\n"
            "project_name: my-infra\n\n"
            "global:\n"
            "  addressing:\n"
            "    base_octet: 10\n"
            "    zone_base: 100\n"
            '  default_os_image: "images:debian/13"\n\n'
            "domains:\n"
            "  work:\n"
            '    description: "Professional workspace"\n'
            "    trust_level: semi-trusted\n"
            "    machines:\n"
            "      work-dev:\n"
            '        description: "Development"\n'
            "        type: lxc\n"
            "        roles: [base_system]\n\n"
            "  personal:\n"
            '    description: "Personal space"\n'
            "    trust_level: trusted\n"
            "    machines:\n"
            "      personal-desktop:\n"
            '        description: "Personal desktop"\n'
            "        type: lxc\n"
            "        roles: [base_system]\n"
        )
    infra_path.write_text(content)
    return f"Created {infra_path}"


_GUIDE_STRINGS = {
    "fr": {
        "index_title": "Prise en main d'anklume",
        "index_sub": "Déployez votre première infrastructure",
        "all_chapters": "Tous les chapitres",
        "previous": "Pr\u00e9c\u00e9dent",
        "next": "Suivant",
    },
    "en": {
        "index_title": "Getting Started with anklume",
        "index_sub": "Deploy your first infrastructure",
        "all_chapters": "All chapters",
        "previous": "Previous",
        "next": "Next",
    },
}


@app.get("/guide", response_class=HTMLResponse)
async def guide_index(request: Request):
    """Chapter overview."""
    if _guide is None:
        raise HTTPException(status_code=404, detail="Guide not available")
    lang = get_lang(request)
    gs = _GUIDE_STRINGS[lang]
    parts = [
        f"<h1>{html.escape(gs['index_title'])}</h1>",
        f'<p class="subtitle">{html.escape(gs["index_sub"])}</p>',
        '<div class="chapters">',
    ]
    for page in _guide.pages:
        cid = page.id.split("-")[1]
        title = html.escape(page.title.get(lang, page.title.get("en", "")))
        blocks = getattr(page, "_blocks_by_lang", {}).get(lang, page.blocks)
        desc_blocks = [b for b in blocks if b.type == "text"]
        desc = html.escape(desc_blocks[0].text[:80]) if desc_blocks else ""
        parts.append(
            f'<a class="ch-card" href="/guide/{cid}?lang={lang}">'
            f'<div><span class="ch-num">{cid}.</span>'
            f'<span class="ch-title">{title}</span></div>'
            f'<div class="ch-desc">{desc}</div></a>'
        )
    parts.append("</div>")
    return page_wrap(gs["index_title"], "\n".join(parts), extra_css=GUIDE_CSS, lang=lang)


@app.get("/guide/{chapter_id}", response_class=HTMLResponse)
async def guide_chapter(chapter_id: int, request: Request):
    """Chapter page with split-pane: content left, ttyd terminal right."""
    if _guide is None:
        raise HTTPException(status_code=404, detail="Guide not available")
    lang = get_lang(request)
    gs = _GUIDE_STRINGS[lang]
    page_id = f"guide-{chapter_id}"
    page = next((p for p in _guide.pages if p.id == page_id), None)
    if not page:
        raise HTTPException(status_code=404, detail="Chapter not found")

    total = len(_guide.pages)
    title = html.escape(page.title.get(lang, page.title.get("en", "")))
    blocks = getattr(page, "_blocks_by_lang", {}).get(lang, page.blocks)

    # Build content pane
    content_parts = [f"<h1>{chapter_id}. {title}</h1>"]

    # Chapter 1: guide user into anklume-instance
    if chapter_id == 1:
        is_iso = _is_live_iso()
        if is_iso:
            # On live ISO, start.sh already created anklume-instance
            enter_msg = (
                "L&#39;instance anklume est pr&ecirc;te. "
                "Entrez dedans pour commencer :"
                if lang == "fr"
                else "The anklume instance is ready. "
                "Enter it to get started:"
            )
            content_parts.append(
                f'<div class="setup-info"><div class="success">'
                f'{enter_msg}</div></div>'
            )
        else:
            # Existing install: hint to run setup first if no instance
            setup_msg = (
                "Configurez d&#39;abord le stockage dans "
                if lang == "fr"
                else "Set up storage first in "
            )
            content_parts.append(
                f'<div class="setup-info"><div class="warn">'
                f'{setup_msg}'
                f'<a href="/setup?lang={lang}" style="color:#d29922">'
                f'Setup</a></div></div>'
            )

    for block in blocks:
        if block.type == "text":
            content_parts.append(_render_guide_text(block.text))
        elif block.type == "command":
            content_parts.append(
                command_block(block.text, clickable=block.clickable),
            )

    # Navigation
    nav_items = [(gs["all_chapters"], f"/guide?lang={lang}")]
    if chapter_id > 1:
        nav_items.append((gs["previous"], f"/guide/{chapter_id - 1}?lang={lang}"))
    if chapter_id < total:
        nav_items.append((gs["next"], f"/guide/{chapter_id + 1}?lang={lang}"))

    body = (
        '<div class="split-wrapper">'
        '<div class="learn-layout">'
        '<div class="learn-content">'
        + "\n".join(content_parts)
        + "</div>"
        '<div class="split-handle"></div>'
        '<div class="learn-terminal">'
        + _terminal_div()
        + "</div></div>"
        '<div class="learn-nav">'
        + nav_bar(nav_items)
        + '<div class="fullscreen-bar">'
        + '<button class="fs-btn" onclick="toggleFs(\'content\')">'
        + "\u2922 Content</button>"
        + '<button class="fs-btn" onclick="toggleFs(\'terminal\')">'
        + "\u2922 Terminal</button>"
        + '<button class="fs-btn" onclick="toggleFsBoth()">'
        + "\u2922 Fullscreen</button>"
        + "</div>"
        + f'<span>Ch {chapter_id}/{total}</span>'
        + "</div></div>"
    )
    css = GUIDE_CSS + "\n" + SETUP_CSS + "\n" + TERMINAL_CSS
    extra_js = TTYD_TERMINAL_JS + "\n" + SPLIT_FULLSCREEN_JS
    return page_wrap(
        f"Guide \u2014 {title}", body,
        extra_css=css,
        extra_js=extra_js,
        xterm=True, lang=lang,
    )


@app.get("/labs", response_class=HTMLResponse)
async def labs_index(request: Request):
    """Labs placeholder page."""
    lang = get_lang(request)
    s = _STRINGS[lang]
    body = (
        f"<h1>{s['labs_title']}</h1>"
        f'<p class="empty">{s["labs_empty"]}</p>'
    )
    return page_wrap(f"anklume \u2014 {s['labs_title']}", body, lang=lang)


README_CSS = """\
.readme-content {
  max-width: 700px; margin: 0 auto; padding: 20px; line-height: 1.6;
}
.readme-content table { border-collapse: collapse; margin: 12px 0; }
.readme-content td { padding: 4px 12px; border: 1px solid var(--border); }
.readme-content code {
  background: var(--card); padding: 2px 6px; border-radius: 3px;
  font-size: 13px;
}
.readme-content pre {
  background: var(--card); padding: 12px; border-radius: 6px;
  overflow-x: auto;
}
"""

_README_PATH = Path(__file__).resolve().parent.parent / "host/boot/desktop/README-anklume.md"


@app.get("/readme", response_class=HTMLResponse)
async def readme_page():
    """Display the desktop README content."""
    text = _README_PATH.read_text() if _README_PATH.exists() else ""
    # Minimal markdown→html for the README
    lines = []
    in_code = False
    for line in text.splitlines():
        if line.startswith("```"):
            if in_code:
                lines.append("</pre>")
            else:
                lines.append("<pre>")
            in_code = not in_code
            continue
        if in_code:
            lines.append(html.escape(line))
            continue
        if line.startswith("# "):
            lines.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            lines.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("| "):
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if all(c.startswith("-") for c in cells):
                continue
            row = "".join(f"<td>{c}</td>" for c in cells)
            lines.append(f"<tr>{row}</tr>")
        elif line.strip() == "":
            lines.append("")
        else:
            # Inline code
            out = html.escape(line)
            out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
            out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
            lines.append(f"<p>{out}</p>")
    body_html = "\n".join(lines)
    # Wrap table rows
    body_html = body_html.replace("<tr>", "<table><tr>", 1)
    body = f'<div class="readme-content">{body_html}</div>'
    return page_wrap("anklume - README", body, extra_css=README_CSS)


# ── Entry point ─────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="anklume learning platform")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8890)
    args = parser.parse_args()
    print(f"anklume Learn: http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
