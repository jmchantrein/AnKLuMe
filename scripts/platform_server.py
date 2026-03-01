#!/usr/bin/env python3
"""anklume learning platform — unified web server.

Split-pane: guide content left, xterm.js terminal right. Clickable
commands inject into the terminal. Replaces the old guide-server.py.

Routes: / (landing), /guide (chapters), /guide/{n} (split-pane),
/labs (placeholder), /ws/terminal/{id} (WebSocket).

Usage: python3 scripts/platform_server.py [--port 8890]
"""

import argparse
import html
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

sys.path.insert(0, str(Path(__file__).resolve().parent))

from web.content import load_guide_sections  # noqa: E402
from web.html import command_block, nav_bar, page_wrap  # noqa: E402
from web.theme import GUIDE_CSS, TERMINAL_CSS  # noqa: E402
from web.ws_terminal import get_manager  # noqa: E402
from web.ws_terminal import router as ws_router


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator:
    yield
    get_manager().close_all()


app = FastAPI(title="anklume Learn", lifespan=lifespan)
app.include_router(ws_router)

_sections = load_guide_sections()
_guide = _sections[0]

# ── JS for xterm.js + runCmd ────────────────────────────────

TERMINAL_JS = """\
<script>
(function() {
  var sid = 'guide-' + location.pathname.split('/').pop();
  var term = new window.Terminal({cursorBlink: true, fontSize: 14});
  var fitAddon = new window.FitAddon.FitAddon();
  term.loadAddon(fitAddon);
  term.open(document.getElementById('terminal'));
  fitAddon.fit();
  var proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  var ws = new WebSocket(proto + '//' + location.host + '/ws/terminal/' + sid);
  ws.binaryType = 'arraybuffer';
  ws.onmessage = function(e) {
    if (e.data instanceof ArrayBuffer) {
      term.write(new Uint8Array(e.data));
    } else {
      term.write(e.data);
    }
  };
  term.onData(function(data) { ws.send(data); });
  window.addEventListener('resize', function() { fitAddon.fit(); });
  term.onResize(function(size) {
    ws.send(JSON.stringify({type:'resize', cols:size.cols, rows:size.rows}));
  });
  window.runCmd = function(cmd) {
    ws.send(cmd + '\\r');
  };
})();
</script>
"""


# ── Routes ──────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def landing():
    """Landing page with links to guide and labs."""
    body = (
        "<h1>anklume Learning Platform</h1>"
        '<p class="subtitle">Interactive learning with a live terminal</p>'
        '<div class="chapters">'
        '<a class="ch-card" href="/guide">'
        '<div class="ch-title">Capability Tour</div>'
        '<div class="ch-desc">Discover what anklume can do '
        '(8 chapters)</div></a>'
        '<a class="ch-card" href="/labs">'
        '<div class="ch-title">Educational Labs</div>'
        '<div class="ch-desc">Guided exercises (coming soon)</div></a>'
        "</div>"
    )
    return page_wrap("anklume Learn", body, extra_css=GUIDE_CSS)


@app.get("/guide", response_class=HTMLResponse)
async def guide_index():
    """Chapter overview listing all 8 chapters."""
    parts = [
        "<h1>anklume Capability Tour</h1>",
        '<p class="subtitle">Discover what anklume can do</p>',
        '<div class="chapters">',
    ]
    for page in _guide.pages:
        cid = page.id.split("-")[1]
        title = html.escape(page.title.get("en", ""))
        desc_blocks = [b for b in page.blocks if b.type == "text"]
        desc = html.escape(desc_blocks[0].text[:80]) if desc_blocks else ""
        parts.append(
            f'<a class="ch-card" href="/guide/{cid}">'
            f'<div><span class="ch-num">{cid}.</span>'
            f'<span class="ch-title">{title}</span></div>'
            f'<div class="ch-desc">{desc}</div></a>'
        )
    parts.append("</div>")
    return page_wrap("anklume Guide", "\n".join(parts), extra_css=GUIDE_CSS)


@app.get("/guide/{chapter_id}", response_class=HTMLResponse)
async def guide_chapter(chapter_id: int):
    """Chapter page with split-pane: content left, terminal right."""
    page_id = f"guide-{chapter_id}"
    page = next((p for p in _guide.pages if p.id == page_id), None)
    if not page:
        raise HTTPException(status_code=404, detail="Chapter not found")

    total = len(_guide.pages)
    title = html.escape(page.title.get("en", ""))

    # Build content pane
    content_parts = [f"<h1>{chapter_id}. {title}</h1>"]
    for block in page.blocks:
        if block.type == "text":
            content_parts.append(f"<p>{html.escape(block.text)}</p>")
        elif block.type == "command":
            content_parts.append(
                command_block(block.text, clickable=block.clickable),
            )

    # Navigation
    nav_items = [("All chapters", "/guide")]
    if chapter_id > 1:
        nav_items.append(("Previous", f"/guide/{chapter_id - 1}"))
    if chapter_id < total:
        nav_items.append(("Next", f"/guide/{chapter_id + 1}"))

    body = (
        '<div class="learn-layout">'
        '<div class="learn-content">'
        + "\n".join(content_parts)
        + "</div>"
        '<div class="learn-terminal">'
        '<div id="terminal" class="xterm"></div>'
        "</div></div>"
        + '<div class="learn-nav">'
        + nav_bar(nav_items)
        + f'<span>Ch {chapter_id}/{total}</span>'
        + "</div>"
    )
    css = GUIDE_CSS + "\n" + TERMINAL_CSS
    return page_wrap(
        f"Guide — {title}", body,
        extra_css=css, extra_js=TERMINAL_JS, xterm=True,
    )


@app.get("/labs", response_class=HTMLResponse)
async def labs_index():
    """Labs placeholder page."""
    body = (
        "<h1>Educational Labs</h1>"
        '<p class="subtitle">Guided exercises for learning '
        "system administration</p>"
        '<p class="empty">Labs will be available in a future update.</p>'
    )
    return page_wrap("anklume Labs", body)


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
