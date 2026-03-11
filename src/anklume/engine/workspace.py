"""Workspace layout déclaratif — moteur pur Python.

Équivalent GUI de tmuxp : chaque machine avec gui: true déclare
optionnellement son placement sur les bureaux virtuels.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anklume.engine.models import Infrastructure


@dataclass
class DesktopInfo:
    """Un bureau virtuel KDE."""

    position: int
    uuid: str
    name: str


@dataclass
class GridInfo:
    """État de la grille de bureaux virtuels."""

    cols: int
    rows: int
    count: int
    desktops: list[DesktopInfo] = field(default_factory=list)


@dataclass
class WorkspaceEntry:
    """Placement d'une machine GUI sur le bureau."""

    machine_name: str
    domain_name: str
    trust_level: str
    desktop: tuple[int, int]  # (colonne, ligne) 1-indexed
    autostart: bool = False
    app: str = ""
    position: tuple[int, int] | None = None  # (x, y) pixels
    size: tuple[int, int] | None = None  # (w, h) pixels
    fullscreen: bool = False
    screen: int = 0


@dataclass
class WorkspaceLayout:
    """Layout complet du bureau."""

    entries: list[WorkspaceEntry]
    grid_cols: int
    grid_rows: int


def compute_grid_needs(entries: list[WorkspaceEntry]) -> tuple[int, int]:
    """Calcule la grille minimale requise (cols, rows)."""
    if not entries:
        return 0, 0
    max_col = max(e.desktop[0] for e in entries)
    max_row = max(e.desktop[1] for e in entries)
    return max_col, max_row


def resolve_desktop_index(col: int, row: int, grid_cols: int) -> int:
    """Convertit [col, row] (1-indexed) en index linéaire (0-indexed).

    Grille parcourue ligne par ligne : index = (row-1) * cols + (col-1).
    """
    return (row - 1) * grid_cols + (col - 1)


def validate_workspace_entries(entries: list[WorkspaceEntry]) -> list[str]:
    """Valide les entrées workspace. Retourne les messages d'erreur."""
    errors: list[str] = []
    for entry in entries:
        col, row = entry.desktop
        if col < 1:
            errors.append(f"{entry.machine_name}: desktop colonne {col} invalide (min 1).")
        if row < 1:
            errors.append(f"{entry.machine_name}: desktop ligne {row} invalide (min 1).")
        if entry.position is not None:
            x, y = entry.position
            if x < 0 or y < 0:
                errors.append(f"{entry.machine_name}: position ({x}, {y}) invalide (min 0, 0).")
        if entry.size is not None:
            w, h = entry.size
            if w < 1 or h < 1:
                errors.append(f"{entry.machine_name}: size ({w}, {h}) invalide (min 1, 1).")
        if entry.screen < 0:
            errors.append(f"{entry.machine_name}: screen {entry.screen} invalide (min 0).")
    return errors


def parse_workspace(infra: Infrastructure) -> WorkspaceLayout:
    """Extrait les entrées workspace de tous les domaines activés.

    Args:
        infra: Infrastructure (models.Infrastructure).

    Returns:
        WorkspaceLayout avec les entrées et la grille minimale.
    """
    entries: list[WorkspaceEntry] = []

    for domain in infra.enabled_domains:
        for machine in domain.machines.values():
            ws = machine.workspace
            if not ws:
                continue

            desktop_raw = ws.get("desktop", [1, 1])
            desktop = (int(desktop_raw[0]), int(desktop_raw[1]))

            entry = WorkspaceEntry(
                machine_name=machine.full_name,
                domain_name=domain.name,
                trust_level=domain.trust_level,
                desktop=desktop,
                autostart=ws.get("autostart", False),
                app=ws.get("app", ""),
                position=tuple(ws["position"]) if ws.get("position") else None,
                size=tuple(ws["size"]) if ws.get("size") else None,
                fullscreen=ws.get("fullscreen", False),
                screen=ws.get("screen", 0),
            )
            entries.append(entry)

    cols, rows = compute_grid_needs(entries)
    return WorkspaceLayout(entries=entries, grid_cols=cols, grid_rows=rows)


def compute_grid_change(
    current_cols: int,
    current_rows: int,
    current_count: int,
    add_cols: int = 0,
    add_rows: int = 0,
) -> tuple[int, int]:
    """Calcule le nouveau count et rows après ajout de colonnes/lignes.

    Returns:
        (new_count, new_rows)
    """
    new_cols = current_cols + add_cols
    new_rows = current_rows + add_rows
    new_count = new_cols * new_rows
    return new_count, new_rows


def compute_grid_set(target_cols: int, target_rows: int) -> tuple[int, int]:
    """Calcule le count et rows pour une grille forcée.

    Returns:
        (new_count, new_rows)
    """
    return target_cols * target_rows, target_rows
