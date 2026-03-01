"""HTML string builders for anklume web applications.

No template engine — plain Python string construction.
Shared between dashboard, guide, and learning platform.
"""

import html
import re

HTMX_CDN = "https://unpkg.com/htmx.org@2.0.4"
XTERM_CDN = "https://cdn.jsdelivr.net/npm/@xterm/xterm@5.5.0"
XTERM_ATTACH_CDN = "https://cdn.jsdelivr.net/npm/@xterm/addon-attach@0.11.0"
XTERM_FIT_CDN = "https://cdn.jsdelivr.net/npm/@xterm/addon-fit@0.10.0"


def page_wrap(
    title: str,
    body: str,
    extra_css: str = "",
    extra_js: str = "",
    *,
    xterm: bool = False,
) -> str:
    """Wrap body in a complete HTML page with theme CSS."""
    from scripts.web.theme import BASE_CSS

    xterm_head = ""
    if xterm:
        xterm_head = (
            f'<link rel="stylesheet" href="{XTERM_CDN}/css/xterm.css">\n'
            f'<script src="{XTERM_CDN}/lib/xterm.js"></script>\n'
            f'<script src="{XTERM_ATTACH_CDN}/lib/addon-attach.js"></script>\n'
            f'<script src="{XTERM_FIT_CDN}/lib/addon-fit.js"></script>\n'
        )
    return (
        f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">\n'
        f"<title>{html.escape(title)}</title>\n"
        f'<script src="{HTMX_CDN}"></script>\n'
        f"{xterm_head}"
        f"<style>{BASE_CSS}\n{extra_css}</style>\n"
        f"</head><body>\n{body}\n"
        f"{extra_js}</body></html>"
    )


def card(title: str, content: str, border_color: str | None = None) -> str:
    """Render a .card div with optional colored left border."""
    style = f' style="border-left: 4px solid {html.escape(border_color)}"' if border_color else ""
    return (
        f'<div class="card"{style}>'
        f"<h3>{html.escape(title)}</h3>"
        f"<div>{html.escape(content)}</div></div>"
    )


def nav_bar(items: list[tuple[str, str]]) -> str:
    """Render a navigation bar from (label, href) pairs."""
    links = " ".join(f'<a href="{href}">{html.escape(label)}</a>' for label, href in items)
    return f'<div class="nav">{links}</div>'


def command_block(cmd: str, *, clickable: bool = False) -> str:
    """Render a styled command block with optional run button."""
    escaped = html.escape(cmd)
    if clickable:
        return (
            f'<div class="cmd-block">'
            f"<code>{escaped}</code>"
            f'<button class="run-btn" onclick="runCmd(\'{escaped}\')">&#9654;</button>'
            f"</div>"
        )
    return f'<pre class="terminal">$ {escaped}</pre>'


def render_markdown(text: str) -> str:
    """Minimal markdown to HTML (headings, code blocks, lists, emphasis).

    Handles the subset needed for guide/lab content. Not a full parser.
    """
    lines = text.split("\n")
    out: list[str] = []
    in_code = False

    for line in lines:
        if line.startswith("```"):
            if in_code:
                out.append("</code></pre>")
                in_code = False
            else:
                out.append('<pre class="terminal"><code>')
                in_code = True
            continue
        if in_code:
            out.append(html.escape(line))
            continue
        # Headings
        if m := re.match(r"^(#{1,3})\s+(.+)", line):
            level = len(m.group(1))
            out.append(f"<h{level}>{html.escape(m.group(2))}</h{level}>")
            continue
        # Unordered list
        if m := re.match(r"^[-*]\s+(.+)", line):
            out.append(f"<li>{_inline(m.group(1))}</li>")
            continue
        # Emphasis
        if line.strip():
            out.append(f"<p>{_inline(line)}</p>")
        else:
            out.append("")

    if in_code:
        out.append("</code></pre>")
    return "\n".join(out)


def _inline(text: str) -> str:
    """Process inline markdown (bold, code, italic)."""
    text = html.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    return text
