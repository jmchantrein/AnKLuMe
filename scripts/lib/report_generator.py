"""HTML screenshot report generator for GUI tests.

Generates an index.html in the screenshot directory with:
- Thumbnail grid of all screenshots (chronological order)
- Test results table with PASS/FAIL/SKIP status
- Click-to-enlarge inline image viewer
"""

from __future__ import annotations

import html
import os
from pathlib import Path


def generate_report(
    screenshot_dir: str,
    results: list[tuple[str, str, str]],
    title: str = "anklume GUI Test Report",
) -> str:
    """Generate an HTML report in the screenshot directory.

    Args:
        screenshot_dir: Directory containing screenshot PNGs.
        results: List of (test_name, status, detail) tuples.
        title: Report title.

    Returns:
        Path to the generated index.html.
    """
    screenshots = sorted(
        f for f in os.listdir(screenshot_dir)
        if f.lower().endswith(".png")
    )

    passed = sum(1 for _, s, _ in results if s in ("PASS", "INFO"))
    failed = sum(1 for _, s, _ in results if s in ("FAIL", "TIMEOUT"))
    skipped = sum(1 for _, s, _ in results if s in ("SKIP", "WARN"))

    status_colors = {
        "PASS": "#22c55e", "FAIL": "#ef4444", "SKIP": "#a1a1aa",
        "WARN": "#f59e0b", "INFO": "#3b82f6", "TIMEOUT": "#ef4444",
    }

    thumbs_html = "\n".join(
        f'<div class="thumb" onclick="show(\'{html.escape(s)}\')">'
        f'<img src="{html.escape(s)}" loading="lazy" alt="{html.escape(s)}">'
        f'<span>{html.escape(s[:-4])}</span></div>'
        for s in screenshots
    )

    rows_html = "\n".join(
        f'<tr><td style="color:{status_colors.get(status, "#fff")}">'
        f'{html.escape(status)}</td>'
        f'<td>{html.escape(name)}</td>'
        f'<td>{html.escape(detail[:200])}</td></tr>'
        for name, status, detail in results
    )

    report_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
body {{ background: #1a1a2e; color: #e0e0e0; font-family: monospace; margin: 20px; }}
h1 {{ color: #00d4ff; }}
.summary {{ display: flex; gap: 20px; margin: 15px 0; font-size: 1.2em; }}
.summary span {{ padding: 4px 12px; border-radius: 4px; }}
.pass {{ background: #22c55e20; color: #22c55e; }}
.fail {{ background: #ef444420; color: #ef4444; }}
.skip {{ background: #a1a1aa20; color: #a1a1aa; }}
.grid {{ display: flex; flex-wrap: wrap; gap: 10px; margin: 20px 0; }}
.thumb {{ cursor: pointer; text-align: center; }}
.thumb img {{ width: 180px; height: 120px; object-fit: cover; border: 2px solid #333;
  border-radius: 4px; transition: border-color 0.2s; }}
.thumb img:hover {{ border-color: #00d4ff; }}
.thumb span {{ display: block; font-size: 0.75em; color: #888; margin-top: 3px;
  max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
th, td {{ padding: 6px 12px; text-align: left; border-bottom: 1px solid #333; }}
th {{ color: #00d4ff; }}
#viewer {{ display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
  background: rgba(0,0,0,0.9); z-index: 100; cursor: pointer;
  justify-content: center; align-items: center; }}
#viewer img {{ max-width: 95vw; max-height: 95vh; }}
</style>
</head>
<body>
<h1>{html.escape(title)}</h1>
<div class="summary">
  <span class="pass">{passed} passed</span>
  <span class="fail">{failed} failed</span>
  <span class="skip">{skipped} skipped</span>
</div>

<h2>Screenshots ({len(screenshots)})</h2>
<div class="grid">{thumbs_html}</div>

<h2>Test Results</h2>
<table>
<tr><th>Status</th><th>Test</th><th>Detail</th></tr>
{rows_html}
</table>

<div id="viewer" onclick="this.style.display='none'">
  <img id="viewer-img" src="" alt="enlarged">
</div>

<script>
function show(src) {{
  document.getElementById('viewer-img').src = src;
  document.getElementById('viewer').style.display = 'flex';
}}
document.addEventListener('keydown', e => {{
  if (e.key === 'Escape') document.getElementById('viewer').style.display = 'none';
}});
</script>
</body>
</html>"""

    output_path = os.path.join(screenshot_dir, "index.html")
    Path(output_path).write_text(report_html)
    return output_path
