"""Implémentation des commandes `anklume setup`."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import typer

from anklume.engine.import_infra import import_infrastructure
from anklume.engine.incus_driver import IncusDriver, IncusError

# Shells supportés et leurs fichiers rc
_SHELL_RC: dict[str, str] = {
    "bash": ".bashrc",
    "zsh": ".zshrc",
    "fish": "",  # traité séparément (conf.d)
}

_ALIAS_MARKER = "# anklume-aliases"


def _detect_shell() -> str:
    """Détecte le shell courant."""
    shell = os.environ.get("SHELL", "")
    for name in _SHELL_RC:
        if name in shell:
            return name
    return "bash"


def _fish_alias_block() -> str:
    return f"""{_ALIAS_MARKER}
alias anklume 'uv run --project {Path.cwd()} anklume'
alias ank 'uv run --project {Path.cwd()} anklume'
{_ALIAS_MARKER}-end"""


def _posix_alias_block() -> str:
    return f"""{_ALIAS_MARKER}
alias anklume='uv run --project {Path.cwd()} anklume'
alias ank='uv run --project {Path.cwd()} anklume'
{_ALIAS_MARKER}-end"""


def _get_rc_path(shell: str) -> Path:
    home = Path.home()
    if shell == "fish":
        conf_dir = home / ".config" / "fish" / "conf.d"
        conf_dir.mkdir(parents=True, exist_ok=True)
        return conf_dir / "anklume.fish"
    return home / _SHELL_RC[shell]


def _install_aliases(rc_path: Path, block: str) -> bool:
    """Insère ou met à jour le bloc d'aliases. Retourne True si modifié."""
    content = rc_path.read_text() if rc_path.exists() else ""

    if _ALIAS_MARKER in content:
        # Remplacer le bloc existant
        import re

        content = re.sub(
            rf"{_ALIAS_MARKER}.*?{_ALIAS_MARKER}-end",
            block,
            content,
            flags=re.DOTALL,
        )
    else:
        content = content.rstrip() + "\n\n" + block + "\n"

    rc_path.write_text(content)
    return True


def _uninstall_aliases(rc_path: Path) -> bool:
    """Supprime le bloc d'aliases. Retourne True si modifié."""
    if not rc_path.exists():
        return False
    content = rc_path.read_text()
    if _ALIAS_MARKER not in content:
        return False

    import re

    content = re.sub(
        rf"\n*{_ALIAS_MARKER}.*?{_ALIAS_MARKER}-end\n*",
        "\n",
        content,
        flags=re.DOTALL,
    )
    rc_path.write_text(content)
    return True


def run_setup_aliases(remove: bool = False, shell: str | None = None) -> None:
    """Installe ou supprime les aliases shell (anklume, ank)."""
    detected = shell or _detect_shell()
    if detected not in _SHELL_RC:
        typer.echo(f"Shell '{detected}' non supporté. Supportés : {', '.join(_SHELL_RC)}", err=True)
        raise typer.Exit(1)

    rc_path = _get_rc_path(detected)
    block = _fish_alias_block() if detected == "fish" else _posix_alias_block()

    if remove:
        if _uninstall_aliases(rc_path):
            typer.echo(f"Aliases supprimés de {rc_path}")
        else:
            typer.echo("Aucun alias anklume trouvé.")
        return

    # Vérifier si uv tool a déjà installé anklume globalement
    result = subprocess.run(
        ["uv", "tool", "list"],
        capture_output=True,
        text=True,
        check=False,
    )
    if "anklume" in result.stdout:
        typer.echo("anklume est déjà installé globalement via `uv tool install`.")
        typer.echo("Alias 'ank' ajouté comme raccourci.")
        # Installer juste ank comme raccourci
        if detected == "fish":
            block = f"{_ALIAS_MARKER}\nalias ank anklume\n{_ALIAS_MARKER}-end"
        else:
            block = f"{_ALIAS_MARKER}\nalias ank='anklume'\n{_ALIAS_MARKER}-end"

    _install_aliases(rc_path, block)
    typer.echo(f"Aliases installés dans {rc_path}")
    typer.echo(f"Rechargez votre shell ou lancez : source {rc_path}")


def run_setup_import(output_dir: str = ".") -> None:
    """Scanne Incus et génère les fichiers domaine."""
    from anklume.engine.import_infra import IMPORT_LIMITATIONS

    driver = IncusDriver()

    try:
        result = import_infrastructure(driver, Path(output_dir))
    except IncusError as e:
        typer.echo(f"Erreur : {e}", err=True)
        raise typer.Exit(1) from None

    if not result.domains:
        typer.echo("Aucun projet Incus trouvé (hors default).")
        return

    typer.echo(f"Projets scannés : {len(result.domains)}")
    for domain in result.domains:
        inst_count = len(domain.instances)
        net = domain.network or "aucun"
        typer.echo(f"  {domain.project} : {inst_count} instance(s), réseau {net}")

    typer.echo("\nFichiers générés :")
    for f in result.files_written:
        typer.echo(f"  {f}")

    typer.echo("\nLimitations de l'import (bootstrap approximatif) :")
    for lim in IMPORT_LIMITATIONS:
        typer.echo(f"  - {lim}")
