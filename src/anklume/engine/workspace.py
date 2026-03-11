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


VALID_TILES = frozenset({
    "left",
    "right",
    "top-left",
    "top-right",
    "bottom-left",
    "bottom-right",
    "maximize",
})


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
    tile: str = ""  # KWin quick-tile: left, right, top-left, ..., maximize


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

    # Détection de collisions : deux machines fullscreen sur le même bureau
    seen_fullscreen: dict[tuple[int, int, int], str] = {}
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

        # Collision : deux apps fullscreen sur le même desktop+screen
        if entry.fullscreen:
            key = (col, row, entry.screen)
            if key in seen_fullscreen:
                other = seen_fullscreen[key]
                errors.append(
                    f"{entry.machine_name}: collision fullscreen avec {other} "
                    f"sur desktop [{col},{row}] screen {entry.screen}."
                )
            else:
                seen_fullscreen[key] = entry.machine_name

        # Validation tile
        if entry.tile:
            if entry.tile not in VALID_TILES:
                errors.append(
                    f"{entry.machine_name}: tile '{entry.tile}' invalide "
                    f"(valeurs: {', '.join(sorted(VALID_TILES))})."
                )
            if entry.fullscreen:
                errors.append(
                    f"{entry.machine_name}: tile et fullscreen sont mutuellement exclusifs."
                )
            if entry.position is not None:
                errors.append(
                    f"{entry.machine_name}: tile et position sont mutuellement exclusifs."
                )
            if entry.size is not None:
                errors.append(
                    f"{entry.machine_name}: tile et size sont mutuellement exclusifs."
                )

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
                tile=ws.get("tile", ""),
            )
            entries.append(entry)

    cols, rows = compute_grid_needs(entries)
    return WorkspaceLayout(entries=entries, grid_cols=cols, grid_rows=rows)


def resolve_tile(
    tile: str,
    screen_w: int,
    screen_h: int,
) -> tuple[tuple[int, int], tuple[int, int]] | None:
    """Résout un tile en (position, size). None pour maximize.

    Args:
        tile: Mode de tiling (left, right, top-left, ..., maximize).
        screen_w: Largeur de l'écran en pixels.
        screen_h: Hauteur de l'écran en pixels.

    Returns:
        Tuple ((x, y), (w, h)) ou None pour maximize.
    """
    if tile == "maximize":
        return None  # géré séparément via maximizehoriz/maximizevert
    half_w = screen_w // 2
    half_h = screen_h // 2
    mapping: dict[str, tuple[tuple[int, int], tuple[int, int]]] = {
        "left": ((0, 0), (half_w, screen_h)),
        "right": ((half_w, 0), (half_w, screen_h)),
        "top-left": ((0, 0), (half_w, half_h)),
        "top-right": ((half_w, 0), (half_w, half_h)),
        "bottom-left": ((0, half_h), (half_w, half_h)),
        "bottom-right": ((half_w, half_h), (half_w, half_h)),
    }
    return mapping.get(tile)


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
