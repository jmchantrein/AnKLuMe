"""Shared utilities for the anklume CLI."""

import os
import shlex
import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console

console = Console()

_learn_incus_cache: bool | None = None

# Project root: two levels up from scripts/cli/
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def get_infra_path() -> Path:
    """Detect infra.yml or infra/ directory."""
    yml = PROJECT_ROOT / "infra.yml"
    if yml.is_file():
        return yml
    d = PROJECT_ROOT / "infra"
    if d.is_dir():
        return d
    return yml  # let load_infra raise


def load_infra_safe() -> dict:
    """Load and return parsed infra dict, or exit on error."""
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    from generate import load_infra

    try:
        return load_infra(str(get_infra_path()))
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error loading infra:[/red] {e}")
        raise typer.Exit(1) from None


def is_learn_incus() -> bool:
    """Check if Incus learning mode is enabled (~/.anklume/learn_incus)."""
    global _learn_incus_cache  # noqa: PLW0603
    if _learn_incus_cache is None:
        try:
            _learn_incus_cache = (
                Path.home() / ".anklume" / "learn_incus"
            ).read_text().strip() == "on"
        except FileNotFoundError:
            _learn_incus_cache = False
    return _learn_incus_cache


def format_bytes(n: int) -> str:
    """Format byte count as human-readable string (KiB, MiB, GiB)."""
    if n < 1024:
        return f"{n}B"
    if n < 1024 * 1024:
        return f"{n / 1024:.0f}KiB"
    if n < 1024 * 1024 * 1024:
        return f"{n / (1024 * 1024):.1f}MiB"
    return f"{n / (1024 * 1024 * 1024):.1f}GiB"


def run_cmd(
    args: list[str],
    *,
    cwd: str | None = None,
    check: bool = True,
    capture: bool = False,
    timeout: int | None = None,
) -> subprocess.CompletedProcess:
    """Run a subprocess with optional Rich output."""
    if args and args[0] == "incus" and is_learn_incus():
        console.print(f"[dim][incus] {shlex.join(args)}[/dim]")
    effective_cwd = cwd or str(PROJECT_ROOT)
    try:
        return subprocess.run(
            args, cwd=effective_cwd, check=check,
            capture_output=capture, text=True, timeout=timeout,
        )
    except subprocess.CalledProcessError as e:
        if not capture:
            raise typer.Exit(e.returncode) from None
        raise
    except FileNotFoundError:
        console.print(f"[red]Command not found:[/red] {args[0]}")
        raise typer.Exit(1) from None


def run_script(name: str, *args: str, cwd: str | None = None) -> subprocess.CompletedProcess:
    """Run a script from scripts/ directory."""
    script = PROJECT_ROOT / "scripts" / name
    return run_cmd(["bash", str(script), *args], cwd=cwd)


def run_make(target: str, *args: str) -> subprocess.CompletedProcess:
    """Run a Makefile target."""
    return run_cmd(["make", "-C", str(PROJECT_ROOT), target, *args])


def is_live_os() -> bool:
    """Detect if running on anklume Live OS (boot=anklume in kernel cmdline)."""
    try:
        return "boot=anklume" in Path("/proc/cmdline").read_text()
    except OSError:
        return False


def require_container() -> None:
    """Exit if not running inside a container (bypassed on Live OS)."""
    if is_live_os():
        return
    try:
        result = subprocess.run(
            ["systemd-detect-virt", "--container"],
            capture_output=True, text=True, check=False, timeout=5,
        )
        if result.returncode != 0:
            console.print("[yellow]This command must run inside the anklume container.[/yellow]")
            raise typer.Exit(1)
    except FileNotFoundError:
        pass  # no systemd-detect-virt, assume OK


def get_mode() -> str:
    """Read ANKLUME_MODE env var or ~/.anklume/mode, default 'user'."""
    env = os.environ.get("ANKLUME_MODE", "")
    if env:
        return env
    try:
        return Path.home().joinpath(".anklume", "mode").read_text().strip()
    except FileNotFoundError:
        return "user"


def get_lang() -> str:
    """Return language code. Respects ANKLUME_LANG env, defaults to 'fr' in student mode."""
    lang = os.environ.get("ANKLUME_LANG", "")
    if lang:
        return lang
    if get_mode() == "student":
        return "fr"
    return ""


def load_translations() -> dict[str, str]:
    """Load i18n/fr.yml translations. Returns empty dict on failure."""
    import yaml

    path = PROJECT_ROOT / "i18n" / "fr.yml"
    if not path.is_file():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}
