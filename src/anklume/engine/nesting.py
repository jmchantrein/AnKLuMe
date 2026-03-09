"""Nesting Incus — détection de contexte, préfixes et sécurité.

Gère les environnements multi-niveaux (conteneurs dans conteneurs) :
- Détection du niveau de nesting via /etc/anklume/
- Préfixage des noms de ressources Incus par niveau
- Configuration de sécurité adaptée au niveau
- Fichiers de contexte pour les instances enfants
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from anklume.engine.models import NestingConfig

CONTEXT_DIR = Path("/etc/anklume")


@dataclass
class NestingContext:
    """Contexte de nesting du niveau courant."""

    absolute_level: int = 0
    relative_level: int = 0
    vm_nested: bool = False
    yolo: bool = False


def detect_nesting_context(context_dir: Path = CONTEXT_DIR) -> NestingContext:
    """Lit le contexte de nesting depuis le filesystem.

    Si le répertoire ou les fichiers sont absents, retourne le niveau 0.
    """
    if not context_dir.is_dir():
        return NestingContext()

    return NestingContext(
        absolute_level=_read_int(context_dir / "absolute_level", 0),
        relative_level=_read_int(context_dir / "relative_level", 0),
        vm_nested=_read_bool(context_dir / "vm_nested", False),
        yolo=_read_bool(context_dir / "yolo", False),
    )


def prefix_name(name: str, context: NestingContext, nesting_config: NestingConfig) -> str:
    """Préfixe un nom de ressource Incus si nesting actif et niveau > 0."""
    if nesting_config.prefix and context.absolute_level > 0:
        return f"{context.absolute_level:03d}-{name}"
    return name


def unprefix_name(name: str, context: NestingContext, nesting_config: NestingConfig) -> str:
    """Retire le préfixe de nesting d'un nom de ressource Incus."""
    if nesting_config.prefix and context.absolute_level > 0:
        prefix = f"{context.absolute_level:03d}-"
        return name.removeprefix(prefix)
    return name


def nesting_security_config(level: int) -> dict[str, str]:
    """Configuration de sécurité pour les instances créées à ce niveau."""
    if level == 0:
        return {
            "security.nesting": "true",
            "security.syscalls.intercept.mknod": "true",
            "security.syscalls.intercept.setxattr": "true",
        }
    return {
        "security.nesting": "true",
        "security.privileged": "true",
    }


def context_files_for_instance(parent: NestingContext, machine_type: str) -> dict[str, str]:
    """Génère les fichiers de contexte /etc/anklume/ pour une instance enfant."""
    is_vm = machine_type == "vm"

    absolute = parent.absolute_level + 1
    relative = 0 if is_vm else parent.relative_level + 1
    vm_nested = parent.vm_nested or is_vm

    return {
        "absolute_level": str(absolute),
        "relative_level": str(relative),
        "vm_nested": str(vm_nested).lower(),
        "yolo": str(parent.yolo).lower(),
    }


def _read_int(path: Path, default: int) -> int:
    """Lit un entier depuis un fichier, retourne default en cas d'erreur."""
    try:
        text = path.read_text().strip()
        return int(text) if text else default
    except (FileNotFoundError, ValueError):
        return default


def _read_bool(path: Path, default: bool) -> bool:
    """Lit un booléen depuis un fichier, retourne default en cas d'erreur.

    Seules les valeurs exactes ``true`` et ``false`` sont acceptées —
    toute autre valeur est traitée comme default (prévient l'injection
    de valeurs arbitraires via les fichiers de contexte).
    """
    try:
        text = path.read_text().strip().lower()
        if text == "true":
            return True
        if text == "false":
            return False
        return default
    except FileNotFoundError:
        return default
