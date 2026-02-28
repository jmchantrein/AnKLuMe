#!/usr/bin/env python3
"""anklume Welcome Guide — French-first bilingual first-boot wizard."""

from __future__ import annotations

import contextlib
import os
import random
import shutil
import subprocess
from pathlib import Path

from welcome_strings import STRINGS

WELCOME_DONE = Path.home() / ".anklume" / "welcome-done"
POOL_CONF = Path("/mnt/anklume-persist/pool.conf")
FIRST_BOOT = Path("/opt/anklume/scripts/first-boot.sh")
BASE = Path("/opt/anklume/host/boot/desktop")
BASE_DEV = Path(__file__).resolve().parent.parent / "host/boot/desktop"
# Project root for explore mode
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BANNER = (
    "     _    _  _ _  ___    _   _ __  __ ___\n"
    "    / \\  | \\| | |/ / |  | | | |  \\/  | __|\n"
    "   / _ \\ | .` | ' <| |__| |_| | |\\/| | _|\n"
    "  /_/ \\_\\|_|\\_|_|\\_\\____|\\___/|_|  |_|___|\n"
)


def detect_lang() -> str:
    return "en" if os.environ.get("LANG", "").startswith("en") else "fr"

def _resolve(name: str) -> Path:
    prod = BASE / name
    return prod if prod.exists() else (BASE_DEV / name)

def _read_localized(basename: str, ext: str, lang: str) -> str:
    suffix = f".{lang}" if lang != "en" else ""
    f = _resolve(f"{basename}{suffix}{ext}")
    if not f.exists():
        f = _resolve(f"{basename}{ext}")
    return f.read_text() if f.exists() else ""


def get_quote(lang: str) -> str:
    text = _read_localized("quotes", ".txt", lang)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return random.choice(lines) if lines else ""

def get_keybindings_excerpt(lang: str) -> list[str]:
    text = _read_localized("KEYBINDINGS", ".txt", lang)
    if not text:
        return []
    out: list[str] = []
    in_block = False
    for line in text.splitlines():
        if not in_block and ":" in line and not line.startswith(" "):
            in_block = True
        elif in_block and line.strip() and line.startswith("  "):
            out.append(line)
            if len(out) >= 5:
                break
        elif in_block and out:
            break
    return out

def mark_done() -> None:
    WELCOME_DONE.parent.mkdir(parents=True, exist_ok=True)
    WELCOME_DONE.touch()

def has_extra_disks() -> tuple[bool, str]:
    r = subprocess.run(["lsblk", "-d", "-o", "NAME,SIZE,MODEL,TRAN", "-n"],
                       capture_output=True, text=True, timeout=10)
    if r.returncode != 0:
        return False, ""
    real = [ln for ln in r.stdout.strip().splitlines()
            if ln.strip() and not ln.strip().startswith("loop")]
    return len(real) > 1, r.stdout.strip()

KEYBOARD_LAYOUTS = [
    ("fr", "Francais (AZERTY)"),
    ("us", "English (QWERTY)"),
    ("de", "Deutsch (QWERTZ)"),
    ("es", "Espanol"),
    ("it", "Italiano"),
    ("pt", "Portugues"),
    ("gb", "English UK"),
]


def is_live_os() -> bool:
    """Detect if running on anklume Live OS."""
    try:
        return "boot=anklume" in Path("/proc/cmdline").read_text()
    except OSError:
        return False


def do_keyboard(s: dict) -> None:
    """Let the user choose a keyboard layout."""
    if not is_live_os():
        return  # Only relevant on live OS

    print(f"  {s['keyboard_title']}\n")
    for i, (code, label) in enumerate(KEYBOARD_LAYOUTS, 1):
        marker = " *" if code == "fr" else ""
        print(f"  [{i}] {label} ({code}){marker}")
    print()

    while True:
        choice = input(f"  {s['keyboard_choice']} [1-{len(KEYBOARD_LAYOUTS)}]: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(KEYBOARD_LAYOUTS):
            break
        print(f"  (1-{len(KEYBOARD_LAYOUTS)})")

    code = KEYBOARD_LAYOUTS[int(choice) - 1][0]
    label = KEYBOARD_LAYOUTS[int(choice) - 1][1]

    # Apply keyboard layout
    subprocess.run(["loadkeys", code], check=False, capture_output=True)
    # Update vconsole.conf for persistence within this session
    with contextlib.suppress(OSError):
        Path("/etc/vconsole.conf").write_text(f"KEYMAP={code}\n")
    # Update /etc/default/keyboard for Wayland compositors
    with contextlib.suppress(OSError):
        Path("/etc/default/keyboard").write_text(
            f'XKBMODEL="pc105"\nXKBLAYOUT="{code}"\nXKBVARIANT=""\nXKBOPTIONS=""\n'
        )
    print(f"  {s['keyboard_set']} {label}")


def do_explore(s: dict) -> None:
    """Auto-provision minimal infrastructure for explore mode (no persistence)."""
    print(f"  {s['explore_init']}")

    # Step 1: Initialize Incus if not already done
    r = subprocess.run(
        ["incus", "profile", "show", "default"],
        capture_output=True, text=True, timeout=10,
    )
    if r.returncode != 0 or "eth0" not in r.stdout:
        print(f"  {s['explore_incus']}")
        subprocess.run(
            ["incus", "admin", "init", "--minimal"],
            timeout=60, check=False,
        )

    # Step 2: Copy starter infra.yml if not present
    infra_dst = PROJECT_ROOT / "infra.yml"
    infra_example = PROJECT_ROOT / "infra.yml.example"
    if not infra_dst.exists() and infra_example.exists():
        shutil.copy2(infra_example, infra_dst)
        print(f"  {s['explore_infra']}")

    # Step 3: Generate and apply infrastructure
    if infra_dst.exists():
        print(f"  {s['explore_sync']}")
        subprocess.run(
            ["python3", str(PROJECT_ROOT / "scripts" / "generate.py"), str(infra_dst)],
            cwd=str(PROJECT_ROOT), timeout=60, check=False,
        )
        print(f"  {s['explore_apply']}")
        subprocess.run(
            ["ansible-playbook", "site.yml"],
            cwd=str(PROJECT_ROOT), timeout=300, check=False,
        )

    print(f"  {s['explore_done']}")


def do_persistence(s: dict) -> None:
    fb = FIRST_BOOT if FIRST_BOOT.exists() else Path("scripts/first-boot.sh")
    if not fb.exists():
        return print(f"  {s['persist_no_script']}")
    found, disk_output = has_extra_disks()
    if not found:
        return print(f"  {s['persist_no_disk']}")
    print(f"  {s['disks']}\n{disk_output}\n")
    answer = input(f"  {s['persist_confirm']} [{s['yes']}/n] ").strip().lower()
    if answer in (s["yes"], "y", "o", ""):
        print(f"  {s['persist_running']}")
        os.system(f"sudo {fb}")
    else:
        print(f"  {s['persist_skip']}")

def show_tour(s: dict) -> None:
    for i, (title, desc) in enumerate(s["tour_steps"], 1):
        print(f"  {i}. {title}")
        for line in desc.splitlines():
            print(f"     {line}")
        print()

def show_next_steps(s: dict, lang: str) -> None:
    kb = get_keybindings_excerpt(lang)
    if kb:
        print(f"  {s['next_keys_label']}")
        for line in kb:
            print(f"  {line}")
        print()
    print(f"  {s['next_guide']}")
    print(f"  {s['next_help']}")
    print(f"  {s['next_console']}")
    if "next_labs" in s:
        print(f"  {s['next_labs']}")

# ── TUI (rich) ──
def tui_main() -> None:
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.prompt import Prompt
        from rich.text import Text
    except ImportError:
        plain_main()
        return
    lang, s, c = detect_lang(), STRINGS[detect_lang()], Console()
    # Page 1: Welcome
    txt = Text()
    for line in BANNER.splitlines(keepends=True):
        txt.append(line, style="bold magenta")
    c.print(txt)
    quote = get_quote(lang)
    if quote:
        c.print(Panel(f"[italic]{quote}[/italic]", border_style="dim"))
    c.print(f"\n[bold cyan]{s['welcome_title']}[/bold cyan]\n")
    c.print(s["welcome_what"])
    input(f"\n  [{s['start']}] ")
    # Page 1b: Keyboard layout (live OS only)
    do_keyboard(s)
    # Page 2: Situation
    c.print(f"\n[bold cyan]{s['situation_title']}[/bold cyan]\n")
    if POOL_CONF.exists():
        c.print(f"[green]{s['returning']}[/green]\n")
    else:
        c.print(f"  [bold]1.[/bold] {s['opt_persist']}")
        c.print(f"     [dim]{s.get('opt_persist_desc', '')}[/dim]")
        c.print(f"  [bold]2.[/bold] {s['opt_explore']}")
        c.print(f"     [dim]{s.get('opt_explore_desc', '')}[/dim]")
        c.print(f"  [bold]3.[/bold] {s['opt_skip']}\n")
        choice = Prompt.ask(f"[cyan]{s['choice']}[/cyan]", choices=["1", "2", "3"])
        if choice == "1":
            c.print(f"\n[bold cyan]{s['persist_title']}[/bold cyan]")
            c.print(f"{s['persist_explain']}\n")
            do_persistence(s)
        elif choice == "2":
            c.print(f"\n[bold cyan]{s['explore_title']}[/bold cyan]\n")
            do_explore(s)
            if "explore_warn" in s:
                c.print(f"\n[bold yellow]{s['explore_warn']}[/bold yellow]\n")
        elif choice == "3":
            mark_done()
            c.print(f"\n[dim]{s['next_guide']}[/dim]\n")
            return
    # Page 4-5: Tour + Next steps
    c.print(f"\n[bold cyan]{s['tour_title']}[/bold cyan]\n")
    show_tour(s)
    input(f"  [{s['continue']}] ")
    c.print(f"\n[bold cyan]{s['next_title']}[/bold cyan]\n")
    show_next_steps(s, lang)
    input(f"\n  [{s['finish']}] ")
    mark_done()

# ── Plain text fallback ──
def plain_main() -> None:
    lang, s = detect_lang(), STRINGS[detect_lang()]
    print(f"\n{BANNER}")
    quote = get_quote(lang)
    if quote:
        print(f"  {quote}\n")
    print(f"  {s['welcome_title']}\n\n  {s['welcome_what']}\n")
    input(f"  [{s['start']}] ")
    # Keyboard layout (live OS only)
    do_keyboard(s)
    print(f"\n  {s['situation_title']}\n")
    if POOL_CONF.exists():
        print(f"  {s['returning']}\n")
    else:
        print(f"  1. {s['opt_persist']}")
        if "opt_persist_desc" in s:
            print(f"     {s['opt_persist_desc']}")
        print(f"  2. {s['opt_explore']}")
        if "opt_explore_desc" in s:
            for line in s["opt_explore_desc"].splitlines():
                print(f"     {line}")
        print(f"  3. {s['opt_skip']}\n")
        while True:
            choice = input(f"  {s['choice']} [1-3]: ").strip()
            if choice in ("1", "2", "3"):
                break
            print("  (1-3)")
        if choice == "1":
            print(f"\n  {s['persist_title']}\n  {s['persist_explain']}\n")
            do_persistence(s)
        elif choice == "2":
            print(f"\n  {s['explore_title']}\n")
            do_explore(s)
            if "explore_warn" in s:
                print(f"\n  {s['explore_warn']}\n")
        elif choice == "3":
            mark_done()
            return print(f"\n  {s['next_guide']}\n")
    print(f"\n  {s['tour_title']}\n")
    show_tour(s)
    input(f"  [{s['continue']}] ")
    print(f"\n  {s['next_title']}\n")
    show_next_steps(s, lang)
    input(f"\n  [{s['finish']}] ")
    mark_done()

if __name__ == "__main__":
    tui_main()
