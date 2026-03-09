"""Clipboard sharing — presse-papiers hôte ↔ conteneur.

Pipe le contenu du presse-papiers entre l'hôte (Wayland)
et un conteneur via incus exec.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from typing import Literal

from anklume.engine.incus_driver import IncusDriver
from anklume.engine.models import Infrastructure
from anklume.engine.snapshot import resolve_instance_project

log = logging.getLogger(__name__)

CLIPBOARD_PATH = "/tmp/.anklume-clipboard"  # noqa: S108


@dataclass
class ClipboardResult:
    """Résultat d'une opération presse-papiers."""

    direction: Literal["push", "pull"]
    instance: str
    content_length: int  # caractères transférés


def read_host_clipboard() -> str:
    """Lit le presse-papiers hôte via wl-paste."""
    result = subprocess.run(
        ["wl-paste", "--no-newline"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    if result.returncode != 0:
        msg = f"wl-paste échoué : {result.stderr}"
        raise RuntimeError(msg)
    return result.stdout


def write_host_clipboard(text: str) -> None:
    """Écrit sur le presse-papiers hôte via wl-copy."""
    result = subprocess.run(
        ["wl-copy"],
        input=text,
        capture_output=True,
        text=True,
        timeout=5,
    )
    if result.returncode != 0:
        msg = f"wl-copy échoué : {result.stderr}"
        raise RuntimeError(msg)


def clipboard_push(
    driver: IncusDriver,
    infra: Infrastructure,
    instance: str,
) -> ClipboardResult:
    """Copie le presse-papiers hôte vers le conteneur.

    Raises:
        ValueError: instance inconnue.
        RuntimeError: wl-paste échoué.
    """
    project = resolve_instance_project(infra, instance)
    if project is None:
        msg = f"Instance inconnue : {instance}"
        raise ValueError(msg)

    text = read_host_clipboard()

    # Écrire dans le conteneur via instance_exec + stdin
    driver.instance_exec(instance, project, ["tee", CLIPBOARD_PATH], input=text)

    return ClipboardResult(
        direction="push",
        instance=instance,
        content_length=len(text),
    )


def clipboard_pull(
    driver: IncusDriver,
    infra: Infrastructure,
    instance: str,
) -> ClipboardResult:
    """Copie le contenu du conteneur vers le presse-papiers hôte.

    Raises:
        ValueError: instance inconnue.
        RuntimeError: wl-copy échoué.
    """
    project = resolve_instance_project(infra, instance)
    if project is None:
        msg = f"Instance inconnue : {instance}"
        raise ValueError(msg)

    result = driver.instance_exec(instance, project, ["cat", CLIPBOARD_PATH])
    text = result.stdout

    write_host_clipboard(text)

    return ClipboardResult(
        direction="pull",
        instance=instance,
        content_length=len(text),
    )
