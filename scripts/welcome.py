#!/usr/bin/env python3
"""anklume Welcome Guide — First boot setup wizard and feature tour.

Two interfaces:
  --tui   Terminal UI via rich (default)
  --web   Web UI via stdlib http.server + htmx

Usage:
  python3 scripts/welcome.py --tui
  python3 scripts/welcome.py --web --port 8080
  anklume guide               # Makefile alias
"""

from __future__ import annotations

import argparse
import os
import random
import subprocess
from pathlib import Path

# ── Constants ──

WELCOME_DONE = Path.home() / ".anklume" / "welcome-done"
QUOTES_FILE = Path("/opt/anklume/host/boot/desktop/quotes.txt")
# Fallback for development (running from repo root)
QUOTES_FILE_DEV = Path(__file__).resolve().parent.parent / "host/boot/desktop/quotes.txt"
KEYBINDINGS_FILE = Path("/opt/anklume/host/boot/desktop/KEYBINDINGS.txt")
KEYBINDINGS_DEV = (
    Path(__file__).resolve().parent.parent / "host/boot/desktop/KEYBINDINGS.txt"
)


def get_quote() -> str:
    """Return a random quote from quotes.txt."""
    qfile = QUOTES_FILE if QUOTES_FILE.exists() else QUOTES_FILE_DEV
    if not qfile.exists():
        return ""
    lines = [line.strip() for line in qfile.read_text().splitlines() if line.strip()]
    return random.choice(lines) if lines else ""


def get_keybindings() -> str:
    """Return keybindings text."""
    kfile = KEYBINDINGS_FILE if KEYBINDINGS_FILE.exists() else KEYBINDINGS_DEV
    if kfile.exists():
        return kfile.read_text()
    return "(keybindings file not found)"


def mark_done() -> None:
    """Create the welcome-done flag file."""
    WELCOME_DONE.parent.mkdir(parents=True, exist_ok=True)
    WELCOME_DONE.touch()


def is_done() -> bool:
    """Check if the welcome guide has been dismissed."""
    return WELCOME_DONE.exists()


def run_cmd(cmd: str, check: bool = False) -> tuple[int, str]:
    """Run a shell command, return (returncode, output)."""
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, timeout=120
    )
    return result.returncode, result.stdout + result.stderr


# ── TUI Mode (rich) ──


def tui_main() -> None:
    """Terminal UI welcome guide using rich."""
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.prompt import Prompt
        from rich.text import Text
    except ImportError:
        print("rich library not available. Install with: pip install rich")
        print("Falling back to plain text mode.\n")
        plain_main()
        return

    console = Console()

    # Header
    console.print()
    header = Text()
    header.append("     _    _  _ _  ___    _   _ __  __ ___\n", style="bold magenta")
    header.append(
        "    / \\  | \\| | |/ / |  | | | |  \\/  | __|\n", style="bold magenta"
    )
    header.append(
        "   / _ \\ | .` | ' <| |__| |_| | |\\/| | _|\n", style="bold magenta"
    )
    header.append(
        "  /_/ \\_\\|_|\\_|_|\\_\\____|\\___/|_|  |_|___|\n", style="bold magenta"
    )
    console.print(header)

    # Quote
    quote = get_quote()
    if quote:
        console.print(Panel(f"[italic]{quote}[/italic]", border_style="dim"))

    console.print()

    while True:
        console.print("[bold cyan]Welcome to anklume[/bold cyan]")
        console.print()
        console.print("  [bold]1.[/bold] Configure persistence (encrypted disk)")
        console.print("  [bold]2.[/bold] Mount existing data disk")
        console.print("  [bold]3.[/bold] Tour of features")
        console.print("  [bold]4.[/bold] Show keybindings")
        console.print("  [bold]5.[/bold] Skip (I know what I'm doing)")
        console.print()

        choice = Prompt.ask(
            "[cyan]Choose an option[/cyan]", choices=["1", "2", "3", "4", "5"]
        )

        if choice == "1":
            tui_persistence(console)
        elif choice == "2":
            tui_mount_existing(console)
        elif choice == "3":
            tui_tour(console)
        elif choice == "4":
            tui_keybindings(console)
        elif choice == "5":
            mark_done()
            console.print(
                "\n[green]Welcome guide dismissed.[/green] "
                "Run [bold]anklume guide[/bold] to return here.\n"
            )
            break


def tui_persistence(console) -> None:
    """Guide: configure persistence on encrypted disk."""
    from rich.prompt import Confirm

    console.print("\n[bold]Configure Persistence[/bold]\n")
    console.print(
        "This will set up an encrypted data disk for persistent storage."
    )
    console.print("Your containers, data, and Incus pools will survive reboots.\n")

    # Check if first-boot script exists
    fb_script = Path("/opt/anklume/scripts/first-boot.sh")
    if not fb_script.exists():
        console.print(
            "[yellow]first-boot.sh not found at /opt/anklume/scripts/.[/yellow]"
        )
        console.print("This step requires the anklume live OS environment.\n")
        return

    # List block devices
    rc, output = run_cmd("lsblk -d -o NAME,SIZE,MODEL,TRAN -n 2>/dev/null")
    if rc == 0 and output.strip():
        console.print("[bold]Available disks:[/bold]")
        console.print(output)
    else:
        console.print("[yellow]Could not list block devices.[/yellow]\n")
        return

    if Confirm.ask("Run first-boot setup now?", default=False):
        console.print("[dim]Running first-boot.sh --interactive...[/dim]\n")
        os.system("/opt/anklume/scripts/first-boot.sh --interactive")
    else:
        console.print(
            "\nSkipped. Run manually: "
            "[bold]sudo /opt/anklume/scripts/first-boot.sh --interactive[/bold]\n"
        )


def tui_mount_existing(console) -> None:
    """Guide: mount an existing encrypted data disk."""
    console.print("\n[bold]Mount Existing Data Disk[/bold]\n")

    pool_conf = Path("/mnt/anklume-persist/pool.conf")
    if pool_conf.exists():
        console.print(f"[green]Found pool config: {pool_conf}[/green]")
        console.print(pool_conf.read_text())
        console.print("\nData disk should auto-mount on boot.")
        console.print(
            "If not, run: [bold]sudo /opt/anklume/scripts/mount-data.sh[/bold]\n"
        )
    else:
        console.print(
            "[yellow]No pool.conf found.[/yellow] "
            "Run option 1 first to configure persistence.\n"
        )


def tui_tour(console) -> None:
    """Interactive tour of anklume features."""
    from rich.prompt import Confirm

    steps = [
        (
            "Generate Ansible files",
            "anklume sync (or make sync-dry for preview)",
            "make sync-dry",
        ),
        (
            "Apply infrastructure",
            "anklume domain apply creates networks, projects, and instances",
            None,
        ),
        (
            "Open the console",
            "anklume console launches a tmux session with domain-colored panes",
            None,
        ),
        (
            "Take a snapshot",
            "anklume snapshot create saves the state of all instances",
            None,
        ),
        (
            "Network isolation",
            "anklume network rules generates nftables rules for inter-domain isolation",
            None,
        ),
    ]

    console.print("\n[bold]Tour of Features[/bold]\n")
    for i, (title, desc, cmd) in enumerate(steps, 1):
        console.print(f"  [bold cyan]Step {i}/{len(steps)}:[/bold cyan] {title}")
        console.print(f"  {desc}\n")
        if cmd:
            if Confirm.ask(f"  Run [bold]{cmd}[/bold] now?", default=False):
                console.print(f"  [dim]$ {cmd}[/dim]")
                rc, output = run_cmd(cmd)
                if output.strip():
                    for line in output.strip().splitlines()[:20]:
                        console.print(f"  {line}")
                status = "[green]OK[/green]" if rc == 0 else "[red]FAILED[/red]"
                console.print(f"  Result: {status}\n")
            else:
                console.print()
        else:
            console.print()

    console.print("[green]Tour complete![/green] Explore more with [bold]anklume --help[/bold]\n")


def tui_keybindings(console) -> None:
    """Display keybindings reference."""
    console.print()
    console.print(get_keybindings())
    console.print()


# ── Plain text fallback ──


def plain_main() -> None:
    """Plain text welcome guide (no rich dependency)."""
    quote = get_quote()
    print("\n  anklume Welcome Guide\n")
    if quote:
        print(f"  {quote}\n")
    print("  1. Configure persistence (encrypted disk)")
    print("  2. Mount existing data disk")
    print("  3. Tour of features")
    print("  4. Show keybindings")
    print("  5. Skip\n")

    while True:
        choice = input("  Choose [1-5]: ").strip()
        if choice == "5":
            mark_done()
            print("\n  Welcome guide dismissed. Run 'anklume guide' to return.\n")
            break
        if choice == "4":
            print(get_keybindings())
        elif choice in ("1", "2", "3"):
            print(f"\n  (Option {choice} requires 'rich' library for full experience)")
            print("  Install with: pip install rich\n")
        else:
            print("  Invalid choice.\n")


# ── Web Mode ──


def web_main(port: int, host: str) -> None:
    """Web UI welcome guide using stdlib http.server + htmx."""
    import http.server
    from urllib.parse import urlparse

    quote = get_quote().replace('"', "&quot;").replace("<", "&lt;")
    keybindings_html = (
        get_keybindings().replace("&", "&amp;").replace("<", "&lt;").replace("\n", "<br>")
    )

    html_page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>anklume Welcome Guide</title>
<script src="https://unpkg.com/htmx.org@1.9.12"></script>
<style>
  body {{ font-family: monospace; background: #1a1a2e; color: #e0e0e0;
         max-width: 800px; margin: 2em auto; padding: 0 1em; }}
  h1 {{ color: #bd93f9; }}
  .quote {{ font-style: italic; color: #8be9fd; margin: 1em 0;
            padding: 1em; border-left: 3px solid #6272a4; }}
  .menu a {{ display: block; padding: 0.5em 1em; margin: 0.3em 0;
             color: #50fa7b; text-decoration: none; border: 1px solid #4d4d6e;
             border-radius: 4px; }}
  .menu a:hover {{ background: #4d4d6e; }}
  #content {{ margin-top: 1em; padding: 1em; border: 1px solid #4d4d6e;
              border-radius: 4px; min-height: 200px; }}
  pre {{ white-space: pre-wrap; }}
  .ok {{ color: #50fa7b; }}
  .warn {{ color: #f1fa8c; }}
</style>
</head>
<body>
<h1>anklume</h1>
<div class="quote">{quote}</div>
<div class="menu">
  <a hx-get="/step/persistence" hx-target="#content">1. Configure persistence</a>
  <a hx-get="/step/mount" hx-target="#content">2. Mount existing data disk</a>
  <a hx-get="/step/tour" hx-target="#content">3. Tour of features</a>
  <a hx-get="/step/keybindings" hx-target="#content">4. Keybindings</a>
  <a hx-get="/step/skip" hx-target="#content">5. Skip</a>
</div>
<div id="content"><p>Choose an option above to get started.</p></div>
<p style="color:#6272a4; font-size:0.9em">
  Run <code>anklume guide</code> to return here anytime.
</p>
</body></html>"""

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._respond(200, "text/html", html_page)
            elif parsed.path == "/step/persistence":
                self._respond(
                    200,
                    "text/html",
                    "<h3>Configure Persistence</h3>"
                    "<p>Run in terminal:</p>"
                    "<pre>sudo /opt/anklume/scripts/first-boot.sh --interactive</pre>"
                    "<p>This sets up LUKS encryption + ZFS/BTRFS on your data disk.</p>",
                )
            elif parsed.path == "/step/mount":
                self._respond(
                    200,
                    "text/html",
                    "<h3>Mount Existing Disk</h3>"
                    "<p>If you already configured persistence:</p>"
                    "<pre>sudo /opt/anklume/scripts/mount-data.sh</pre>"
                    "<p>Data auto-mounts on boot if pool.conf exists.</p>",
                )
            elif parsed.path == "/step/tour":
                self._respond(
                    200,
                    "text/html",
                    "<h3>Feature Tour</h3>"
                    "<ol>"
                    "<li><code>anklume sync</code> — Generate Ansible files</li>"
                    "<li><code>anklume domain apply</code> — Create infrastructure</li>"
                    "<li><code>anklume console</code> — Tmux domain console</li>"
                    "<li><code>anklume snapshot create</code> — Save state</li>"
                    "<li><code>anklume network rules</code> — nftables isolation</li>"
                    "</ol>"
                    "<p>Run <code>anklume --help</code> for all commands.</p>",
                )
            elif parsed.path == "/step/keybindings":
                self._respond(
                    200,
                    "text/html",
                    f"<h3>Keybindings</h3><pre>{keybindings_html}</pre>",
                )
            elif parsed.path == "/step/skip":
                mark_done()
                self._respond(
                    200,
                    "text/html",
                    '<p class="ok">Welcome guide dismissed.</p>'
                    "<p>Run <code>anklume guide</code> to return.</p>",
                )
            else:
                self._respond(404, "text/html", "<p>Not found</p>")

        def _respond(self, code: int, content_type: str, body: str):
            self.send_response(code)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.end_headers()
            self.wfile.write(body.encode())

        def log_message(self, format, *args):
            pass  # Silence request logs

    server = http.server.HTTPServer((host, port), Handler)
    print(f"anklume Welcome Guide: http://{host}:{port}")
    print("Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


# ── Entry point ──


def main() -> None:
    parser = argparse.ArgumentParser(description="anklume Welcome Guide")
    parser.add_argument(
        "--tui", action="store_true", default=True, help="Terminal UI (default)"
    )
    parser.add_argument("--web", action="store_true", help="Web UI (htmx)")
    parser.add_argument("--port", type=int, default=8080, help="Web UI port")
    parser.add_argument("--host", default="127.0.0.1", help="Web UI bind address")
    args = parser.parse_args()

    if args.web:
        web_main(args.port, args.host)
    else:
        tui_main()


if __name__ == "__main__":
    main()
