"""Workspace layout — backend KDE Plasma (kwinrulesrc + DBus)."""

from __future__ import annotations

import configparser
import functools
import re
import subprocess
from pathlib import Path

import typer

from anklume.engine.models import TRUST_COLORS
from anklume.engine.workspace import (
    DesktopInfo,
    GridInfo,
    WorkspaceEntry,
    WorkspaceLayout,
    compute_grid_change,
    compute_grid_needs,
    compute_grid_set,
    parse_workspace,
    resolve_desktop_index,
    resolve_tile,
    validate_workspace_entries,
)

# Constantes kwinrulesrc
_KWIN_RULE_FORCE = "2"
_KWIN_RULE_APPLY = "3"
_KWIN_MATCH_SUBSTRING = "2"


# ---------------------------------------------------------------------------
# DBus helpers
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def _gui_uid() -> int:
    """Détecte l'UID de l'utilisateur graphique (propriétaire de kwin)."""
    import os

    # SUDO_UID si lancé via sudo
    sudo_uid = os.environ.get("SUDO_UID")
    if sudo_uid:
        return int(sudo_uid)

    # Chercher le propriétaire du processus kwin
    result = subprocess.run(
        ["pgrep", "-n", "-U", "1000:", "kwin"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        pid = result.stdout.strip()
        try:
            stat = Path(f"/proc/{pid}").stat()
            return stat.st_uid
        except OSError:
            pass

    return os.getuid()


def _dbus_env() -> dict[str, str]:
    """Retourne l'environnement DBus de la session graphique."""
    uid = _gui_uid()
    return {"DBUS_SESSION_BUS_ADDRESS": f"unix:path=/run/user/{uid}/bus"}


def _kwriteconfig6(file: str, group: str, key: str, value: str) -> None:
    """Écrit une valeur dans un fichier de config KDE via kwriteconfig6."""
    import os
    import pwd

    uid = _gui_uid()
    cmd = ["kwriteconfig6", "--file", file, "--group", group, "--key", key, value]

    if os.getuid() == 0 and uid != 0:
        username = pwd.getpwuid(uid).pw_name
        cmd = ["sudo", "-u", username, *cmd]

    subprocess.run(cmd, capture_output=True, check=False)


def _qdbus6(args: list[str], env: dict[str, str] | None = None) -> str:
    """Appelle qdbus6 et retourne stdout.

    Si root, exécute via sudo -u pour accéder au bus DBus de l'utilisateur.
    """
    import os

    dbus_env = env or _dbus_env()
    uid = _gui_uid()

    if os.getuid() == 0 and uid != 0:
        # Root ne peut pas accéder au bus DBus directement — sudo -u
        import pwd

        username = pwd.getpwuid(uid).pw_name
        # Passer l'env DBus via env(1) pour éviter l'injection via sudo
        cmd = [
            "sudo",
            "-u",
            username,
            "env",
            f"DBUS_SESSION_BUS_ADDRESS={dbus_env['DBUS_SESSION_BUS_ADDRESS']}",
            "qdbus6",
            *args,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    else:
        result = subprocess.run(
            ["qdbus6", *args],
            capture_output=True,
            text=True,
            env=dbus_env,
            check=False,
        )
    return result.stdout.strip()


def get_grid_info() -> GridInfo:
    """Lit l'état de la grille via DBus VirtualDesktopManager."""
    env = _dbus_env()
    vdm = "org.kde.KWin"
    path = "/VirtualDesktopManager"
    iface = "org.kde.KWin.VirtualDesktopManager"

    count_str = _qdbus6([vdm, path, f"{iface}.count"], env)
    rows_str = _qdbus6([vdm, path, f"{iface}.rows"], env)
    count = int(count_str) if count_str.isdigit() else 1
    rows = int(rows_str) if rows_str.isdigit() else 1
    cols = max(1, count // rows) if rows > 0 else count

    # Lire les desktops (format avec --literal)
    raw = _qdbus6(["--literal", vdm, path, f"{iface}.desktops"], env)
    desktops = _parse_desktops(raw)

    return GridInfo(cols=cols, rows=rows, count=count, desktops=desktops)


def _parse_desktops(raw: str) -> list[DesktopInfo]:
    """Parse la sortie --literal de qdbus6 pour les desktops.

    Format : [Variant: [Argument: a(uss) {[Argument: (uss) 0, "uuid", "name"], ...}]]
    """
    desktops: list[DesktopInfo] = []
    # Cherche les tuples (position, "uuid", "name")
    pattern = re.compile(r'\(uss\)\s+(\d+),\s*"([^"]+)",\s*"([^"]*)"')
    for match in pattern.finditer(raw):
        pos = int(match.group(1))
        uuid = match.group(2)
        name = match.group(3)
        desktops.append(DesktopInfo(position=pos, uuid=uuid, name=name))
    return desktops


def ensure_virtual_desktops(needed_count: int, needed_rows: int) -> None:
    """Crée les desktops manquants et ajuste rows via DBus."""
    env = _dbus_env()
    grid = get_grid_info()
    vdm = "org.kde.KWin"
    path = "/VirtualDesktopManager"
    iface = "org.kde.KWin.VirtualDesktopManager"

    # Créer les desktops manquants
    for i in range(grid.count, needed_count):
        _qdbus6(
            [vdm, path, f"{iface}.createDesktop", str(i), f"Bureau {i + 1}"],
            env,
        )

    # Ajuster rows via DBus (synchrone) + persister dans kwinrc
    if needed_rows != grid.rows:
        _qdbus6(
            [vdm, path, "org.freedesktop.DBus.Properties.Set", iface, "rows", str(needed_rows)],
            env,
        )
        _kwriteconfig6("kwinrc", "Desktops", "Rows", str(needed_rows))


def resolve_desktop_uuids(
    layout: WorkspaceLayout,
    grid: GridInfo,
) -> dict[tuple[int, int], str]:
    """Mapper (col, row) → UUID depuis la grille."""
    uuid_map: dict[tuple[int, int], str] = {}
    for entry in layout.entries:
        col, row = entry.desktop
        index = resolve_desktop_index(col, row, grid.cols)
        if index < len(grid.desktops):
            uuid_map[(col, row)] = grid.desktops[index].uuid
    return uuid_map


# ---------------------------------------------------------------------------
# kwinrulesrc
# ---------------------------------------------------------------------------


def install_workspace_rules(
    entries: list[WorkspaceEntry],
    uuid_map: dict[tuple[int, int], str],
    *,
    kwin_path: Path | None = None,
    screen_size: tuple[int, int] = (1920, 1080),
) -> None:
    """Écrit les règles kwinrulesrc (desktop + position + tiling + couleur trust).

    Args:
        entries: Entrées workspace à écrire.
        uuid_map: Mapping (col, row) → UUID desktop.
        kwin_path: Chemin vers kwinrulesrc (défaut: ~/.config/kwinrulesrc).
        screen_size: Taille de l'écran (w, h) pour le calcul du tiling.
    """
    if kwin_path is None:
        kwin_path = Path.home() / ".config" / "kwinrulesrc"

    config = configparser.ConfigParser()
    config.optionxform = str  # préserver la casse
    if kwin_path.exists():
        config.read(str(kwin_path))

    # Lire les règles existantes
    general = config["General"] if "General" in config else {}
    existing_count = int(general.get("count", "0"))
    rule_ids = general.get("rules", "").split(",") if general.get("rules") else []
    # Nettoyer les IDs vides
    rule_ids = [r for r in rule_ids if r]

    for entry in entries:
        section = f"anklume-{entry.machine_name}"

        if section not in rule_ids:
            existing_count += 1
            rule_ids.append(section)

        # Couleur trust
        color = TRUST_COLORS.get(entry.trust_level)
        scheme_name = f"anklume-{entry.trust_level}"

        rule: dict[str, str] = {
            "Description": f"anklume: {entry.machine_name} ({entry.trust_level}) workspace",
            "wmclass": entry.app or entry.machine_name,
            "wmclassmatch": _KWIN_MATCH_SUBSTRING,
        }

        # Couleur trust
        if color:
            rule["decocolor"] = scheme_name
            rule["decocolorrule"] = _KWIN_RULE_FORCE

        # Bureau virtuel
        desktop_uuid = uuid_map.get(entry.desktop)
        if desktop_uuid:
            rule["desktops"] = desktop_uuid
            rule["desktopsrule"] = _KWIN_RULE_FORCE

        # Position
        if entry.position is not None:
            rule["position"] = f"{entry.position[0]},{entry.position[1]}"
            rule["positionrule"] = _KWIN_RULE_APPLY

        # Taille
        if entry.size is not None:
            rule["size"] = f"{entry.size[0]},{entry.size[1]}"
            rule["sizerule"] = _KWIN_RULE_APPLY

        # Plein écran
        if entry.fullscreen:
            rule["fullscreen"] = "true"
            rule["fullscreenrule"] = _KWIN_RULE_FORCE

        # Tiling (KWin quick-tile)
        if entry.tile:
            if entry.tile == "maximize":
                rule["maximizehoriz"] = "true"
                rule["maximizehorizrule"] = _KWIN_RULE_FORCE
                rule["maximizevert"] = "true"
                rule["maximizevertrule"] = _KWIN_RULE_FORCE
            else:
                tile_result = resolve_tile(entry.tile, screen_size[0], screen_size[1])
                if tile_result:
                    pos, sz = tile_result
                    rule["position"] = f"{pos[0]},{pos[1]}"
                    rule["positionrule"] = _KWIN_RULE_APPLY
                    rule["size"] = f"{sz[0]},{sz[1]}"
                    rule["sizerule"] = _KWIN_RULE_APPLY

        # Écran
        if entry.screen != 0:
            rule["screen"] = str(entry.screen)
            rule["screenrule"] = _KWIN_RULE_APPLY

        config[section] = rule

    # Mettre à jour General
    if "General" not in config:
        config["General"] = {}
    config["General"]["count"] = str(existing_count)
    config["General"]["rules"] = ",".join(rule_ids)

    # Écrire au format KDE natif (key=value sans espaces)
    kwin_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for sect in config.sections():
        lines.append(f"[{sect}]")
        for key, val in config[sect].items():
            lines.append(f"{key}={val}")
        lines.append("")
    kwin_path.write_text("\n".join(lines))


def _get_screen_size() -> tuple[int, int]:
    """Récupère la taille de l'écran via kscreen-doctor.

    Retourne (1920, 1080) en fallback si l'outil est absent ou échoue.
    """
    try:
        result = subprocess.run(
            ["kscreen-doctor", "-o"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "Geometry:" in line:
                    match = re.search(r"(\d+)x(\d+)", line.split("Geometry:")[1])
                    if match:
                        return int(match.group(1)), int(match.group(2))
    except FileNotFoundError:
        pass
    return 1920, 1080


def _reconfigure_kwin() -> None:
    """Recharge KWin via DBus."""
    subprocess.run(
        ["qdbus6", "org.kde.KWin", "/KWin", "org.kde.KWin.reconfigure"],
        capture_output=True,
        env=_dbus_env(),
        check=False,
    )


# ---------------------------------------------------------------------------
# Commandes CLI
# ---------------------------------------------------------------------------


def run_workspace_load(domain: str | None = None) -> None:
    """Restaure le workspace layout complet."""
    from anklume.cli._common import load_infra

    infra = load_infra()
    layout = parse_workspace(infra)

    if domain:
        layout = WorkspaceLayout(
            entries=[e for e in layout.entries if e.domain_name == domain],
            grid_cols=0,
            grid_rows=0,
        )
        cols, rows = compute_grid_needs(layout.entries)
        layout = WorkspaceLayout(entries=layout.entries, grid_cols=cols, grid_rows=rows)

    if not layout.entries:
        typer.echo("Aucune machine avec workspace: configuré.")
        return

    # Valider
    errors = validate_workspace_entries(layout.entries)
    if errors:
        for err in errors:
            typer.echo(f"  Erreur : {err}", err=True)
        raise typer.Exit(1)

    # Grille
    grid = get_grid_info()
    needed_count = layout.grid_cols * layout.grid_rows
    if needed_count > grid.count:
        typer.echo(
            f"Création de {needed_count - grid.count} bureau(x) virtuel(s) "
            f"({grid.cols}x{grid.rows} → {layout.grid_cols}x{layout.grid_rows})..."
        )
        ensure_virtual_desktops(needed_count, layout.grid_rows)
        grid = get_grid_info()

    # Résoudre les UUIDs
    uuid_map = resolve_desktop_uuids(layout, grid)

    # Écrire kwinrulesrc (avec résolution écran pour le tiling)
    screen_size = _get_screen_size()
    install_workspace_rules(layout.entries, uuid_map, screen_size=screen_size)
    _reconfigure_kwin()

    typer.echo(f"Workspace configuré ({len(layout.entries)} règle(s) KWin).")

    # Lancer les apps autostart
    autostart_entries = [e for e in layout.entries if e.autostart and e.app]
    if autostart_entries:
        typer.echo(f"Lancement de {len(autostart_entries)} application(s)...")
        for entry in autostart_entries:
            try:
                from anklume.cli._gui import run_instance_gui

                run_instance_gui(entry.machine_name, entry.app)
            except Exception as exc:
                typer.echo(f"  {entry.machine_name}: échec ({exc})", err=True)


def run_workspace_status() -> None:
    """Affiche le layout déclaré vs réel."""
    from anklume.cli._common import load_infra

    infra = load_infra()
    layout = parse_workspace(infra)

    if not layout.entries:
        typer.echo("Aucune machine avec workspace: configuré.")
        return

    grid = get_grid_info()
    typer.echo(f"Grille actuelle : {grid.cols}x{grid.rows} ({grid.count} desktops)")
    typer.echo(f"Grille requise  : {layout.grid_cols}x{layout.grid_rows}")
    typer.echo()

    for entry in layout.entries:
        col, row = entry.desktop
        auto = " [autostart]" if entry.autostart else ""
        app = f" → {entry.app}" if entry.app else ""
        pos = f" pos={entry.position}" if entry.position else ""
        fs = " [fullscreen]" if entry.fullscreen else ""
        tile = f" [tile:{entry.tile}]" if entry.tile else ""
        typer.echo(
            f"  {entry.machine_name} ({entry.trust_level}): "
            f"desktop [{col},{row}]{app}{auto}{pos}{fs}{tile}"
        )


def run_workspace_grid(
    add_cols: int = 0,
    add_rows: int = 0,
    set_grid: str = "",
) -> None:
    """Affiche ou modifie la grille de bureaux virtuels."""
    grid = get_grid_info()

    if set_grid:
        # Parse CxR
        match = re.match(r"^(\d+)x(\d+)$", set_grid)
        if not match:
            typer.echo(f"Format invalide : {set_grid} (attendu: CxR, ex: 3x2)", err=True)
            raise typer.Exit(1)
        target_cols = int(match.group(1))
        target_rows = int(match.group(2))
        new_count, new_rows = compute_grid_set(target_cols, target_rows)

        if new_count > grid.count:
            ensure_virtual_desktops(new_count, new_rows)
        elif new_count < grid.count:
            # Supprimer les desktops excédentaires (du dernier)
            env = _dbus_env()
            vdm = "org.kde.KWin"
            path = "/VirtualDesktopManager"
            iface = "org.kde.KWin.VirtualDesktopManager"
            for desktop in reversed(grid.desktops[new_count:]):
                _qdbus6(
                    [vdm, path, f"{iface}.removeDesktop", desktop.uuid],
                    env,
                )
            # Ajuster rows via DBus + persister
            _qdbus6(
                [vdm, path, "org.freedesktop.DBus.Properties.Set", iface, "rows", str(new_rows)],
                env,
            )
            _kwriteconfig6("kwinrc", "Desktops", "Rows", str(new_rows))

        grid = get_grid_info()
        typer.echo(f"Grille : {grid.cols}x{grid.rows} ({grid.count} desktops)")
        return

    if add_cols > 0 or add_rows > 0:
        new_count, new_rows = compute_grid_change(
            grid.cols,
            grid.rows,
            grid.count,
            add_cols=add_cols,
            add_rows=add_rows,
        )
        ensure_virtual_desktops(new_count, new_rows)
        grid = get_grid_info()
        typer.echo(f"Grille : {grid.cols}x{grid.rows} ({grid.count} desktops)")
        return

    # Affichage simple
    typer.echo(f"Grille : {grid.cols} colonne(s) x {grid.rows} ligne(s) ({grid.count} desktops)")
    if grid.desktops:
        for row in range(1, grid.rows + 1):
            cells: list[str] = []
            for col in range(1, grid.cols + 1):
                idx = (row - 1) * grid.cols + (col - 1)
                if idx < len(grid.desktops):
                    d = grid.desktops[idx]
                    cells.append(f"[{col},{row}] {d.name}")
                else:
                    cells.append(f"[{col},{row}] ???")
            typer.echo("  " + "    ".join(cells))
