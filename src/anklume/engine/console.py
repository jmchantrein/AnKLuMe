"""Console tmux — session colorée par domaine.

Crée une session tmux avec une fenêtre par domaine et un panneau
par instance. Code couleur par trust level.
Fenêtres numérotées par zone VLAN (offset trust / zone_step).
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field

from anklume.engine.incus_driver import IncusDriver
from anklume.engine.models import TRUST_COLORS, TRUST_LEVELS, Infrastructure
from anklume.engine.nesting import NestingContext, prefix_name

log = logging.getLogger(__name__)

SESSION_NAME = "anklume"

_MAX_PANES_PER_WINDOW = 4

# Couleurs nommées pour la barre de statut (--status-color)
STATUS_COLORS: dict[str, str] = {
    "terminal": "default",
    "dark": "colour236",
    "black": "colour232",
    "grey": "colour240",
    "blue": "colour17",
    "green": "colour22",
    "red": "colour52",
}


@dataclass
class ConsolePane:
    """Panneau tmux pour une instance."""

    instance: str
    domain: str
    trust_level: str
    command: str
    zone_id: int = 0


@dataclass
class ConsoleConfig:
    """Configuration tmux complète."""

    session_name: str
    windows: dict[str, list[ConsolePane]] = field(default_factory=dict)
    status_color: str = "terminal"
    dedicated: bool = False


@dataclass
class _WindowPlan:
    """Plan interne pour une fenêtre tmux."""

    name: str
    panes: list[ConsolePane]
    trust_level: str


def _tmux_run(*args: str) -> subprocess.CompletedProcess:
    """Exécute une commande tmux (silencieux)."""
    return subprocess.run(["tmux", *args], check=False, capture_output=True)


def _tmux_interactive(*args: str) -> subprocess.CompletedProcess:
    """Exécute une commande tmux interactive (attach, etc.)."""
    return subprocess.run(["tmux", *args], check=False)


def _session_exists(session_name: str) -> bool:
    """Vérifie si une session tmux existe déjà."""
    result = _tmux_run("has-session", "-t", session_name)
    return result is not None and result.returncode == 0


def kill_session(session_name: str | None = None) -> bool:
    """Tue une session tmux anklume."""
    name = session_name or SESSION_NAME
    result = _tmux_run("kill-session", "-t", name)
    return result.returncode == 0


def _compute_zone_id(trust_level: str, zone_step: int) -> int:
    """Calcule l'ID de zone depuis le trust level.

    Zone = TRUST_LEVELS[trust] // zone_step.
    admin(0)→0, trusted(10)→1, semi-trusted(20)→2,
    untrusted(40)→4, disposable(50)→5.
    """
    offset = TRUST_LEVELS.get(trust_level, 20)
    return offset // zone_step if zone_step > 0 else offset


def _build_window_plans(config: ConsoleConfig) -> list[_WindowPlan]:
    """Construit le plan des fenêtres : fenêtre 0 hôte, puis par zone VLAN."""
    # Fenêtre 0 : hôte
    host_pane = ConsolePane(
        instance="host",
        domain="host",
        trust_level="admin",
        command="bash",
    )

    if config.dedicated:
        plans: list[_WindowPlan] = [
            _WindowPlan(name="0:0", panes=[host_pane], trust_level="admin"),
        ]
        # 1 fenêtre par instance, 2 panes verticaux (même conteneur)
        # Numérotation séquentielle par zone
        all_panes: list[ConsolePane] = []
        for panes in config.windows.values():
            all_panes.extend(panes)
        all_panes.sort(key=lambda p: (p.zone_id, p.domain, p.instance))
        zone_seq: dict[int, int] = {}
        for pane in all_panes:
            seq = zone_seq.get(pane.zone_id, 0)
            plans.append(
                _WindowPlan(
                    name=f"{pane.zone_id}:{seq}",
                    panes=[pane, pane],
                    trust_level=pane.trust_level,
                )
            )
            zone_seq[pane.zone_id] = seq + 1
        return plans

    # Mode normal : grouper par zone_id, max 4 panes par fenêtre
    # L'hôte est intégré à la zone 0 (admin)
    zone_panes: dict[int, list[ConsolePane]] = {0: [host_pane]}
    for panes in config.windows.values():
        for pane in panes:
            zone_panes.setdefault(pane.zone_id, []).append(pane)

    plans = []
    for zone_id in sorted(zone_panes):
        panes = zone_panes[zone_id]
        panes.sort(key=lambda p: (p.domain != "host", p.domain, p.instance))
        trust = next(
            (p.trust_level for p in panes if p.domain != "host"),
            panes[0].trust_level,
        )

        for i in range(0, len(panes), _MAX_PANES_PER_WINDOW):
            chunk = panes[i : i + _MAX_PANES_PER_WINDOW]
            seq = i // _MAX_PANES_PER_WINDOW
            plans.append(
                _WindowPlan(
                    name=f"{zone_id}:{seq}",
                    panes=chunk,
                    trust_level=trust,
                )
            )

    return plans


def _setup_session(session_name: str, status_bg: str) -> None:
    """Configure les options au niveau de la session."""
    _tmux_run(
        "set-option",
        "-t",
        session_name,
        "status-style",
        f"bg={status_bg},fg=white",
    )
    _tmux_run(
        "set-option",
        "-t",
        session_name,
        "pane-border-status",
        "top",
    )
    _tmux_run(
        "set-option",
        "-t",
        session_name,
        "pane-border-format",
        "#{?pane_active,#[reverse#,bold] #{pane_title} #[default], #{pane_title} }",
    )
    _tmux_run(
        "set-option",
        "-t",
        session_name,
        "pane-border-lines",
        "heavy",
    )
    _tmux_run(
        "set-option",
        "-t",
        session_name,
        "pane-border-indicators",
        "colour",
    )
    # Rebind split : nouveau panneau → même machine
    _tmux_run(
        "bind-key",
        '"',
        "run-shell",
        "tmux split-window -v #{pane_start_command}",
    )
    _tmux_run(
        "bind-key",
        "%",
        "run-shell",
        "tmux split-window -h #{pane_start_command}",
    )


def _apply_window_colors(window_target: str, color: str, fg: str) -> None:
    """Applique les couleurs trust sur une fenêtre."""
    # Onglets : nom seul (sans index tmux), actif coloré, inactif dimmed
    _tmux_run(
        "set-option",
        "-w",
        "-t",
        window_target,
        "window-status-format",
        " #{window_name} ",
    )
    _tmux_run(
        "set-option",
        "-w",
        "-t",
        window_target,
        "window-status-current-format",
        " #{window_name} ",
    )
    _tmux_run(
        "set-option",
        "-w",
        "-t",
        window_target,
        "window-status-current-style",
        f"bg={color},fg={fg},bold",
    )
    _tmux_run(
        "set-option",
        "-w",
        "-t",
        window_target,
        "window-status-style",
        f"fg={color},dim",
    )
    # Bordures : inactif dimmed, actif trust color vive
    _tmux_run(
        "set-option",
        "-w",
        "-t",
        window_target,
        "pane-border-style",
        "fg=colour238",
    )
    _tmux_run(
        "set-option",
        "-w",
        "-t",
        window_target,
        "pane-active-border-style",
        f"fg={color},bold",
    )
    # Contenu : inactif fortement dimmed, actif = terminal normal
    _tmux_run(
        "set-option",
        "-w",
        "-t",
        window_target,
        "window-style",
        "fg=colour240,bg=colour232",
    )
    _tmux_run(
        "set-option",
        "-w",
        "-t",
        window_target,
        "window-active-style",
        "fg=default,bg=default",
    )


def _apply_layout(window_target: str, pane_count: int) -> None:
    """Applique le layout optimal selon le nombre de panneaux.

    2 panes : côte à côte, 3-4 : grille 2x2.
    """
    if pane_count == 2:
        _tmux_run("select-layout", "-t", window_target, "even-horizontal")
    elif pane_count > 2:
        _tmux_run("select-layout", "-t", window_target, "tiled")


def build_console_config(
    infra: Infrastructure,
    driver: IncusDriver,
    *,
    domain: str | None = None,
    nesting_context: NestingContext | None = None,
) -> ConsoleConfig:
    """Construit la configuration tmux depuis l'infra.

    Filtre les instances existantes (Running) uniquement.
    """
    ctx = nesting_context or NestingContext()
    nesting_cfg = infra.config.nesting
    zone_step = infra.config.addressing.zone_step

    if domain:
        session_name = f"{SESSION_NAME}-{domain}"
    else:
        session_name = SESSION_NAME

    existing_projects = {p.name for p in driver.project_list()}
    windows: dict[str, list[ConsolePane]] = {}

    for dom in infra.enabled_domains:
        if domain and dom.name != domain:
            continue

        project_name = prefix_name(dom.name, ctx, nesting_cfg)
        if project_name not in existing_projects:
            continue

        real_instances = {i.name: i for i in driver.instance_list(project_name)}
        panes: list[ConsolePane] = []
        zone_id = _compute_zone_id(dom.trust_level, zone_step)

        for machine in dom.sorted_machines:
            incus_name = prefix_name(machine.full_name, ctx, nesting_cfg)
            real = real_instances.get(incus_name)

            if real is None or real.status != "Running":
                continue

            cmd = f"incus exec {incus_name} --project {project_name} -- bash"
            panes.append(
                ConsolePane(
                    instance=incus_name,
                    domain=dom.name,
                    trust_level=dom.trust_level,
                    command=cmd,
                    zone_id=zone_id,
                )
            )

        if panes:
            windows[dom.name] = panes

    return ConsoleConfig(session_name=session_name, windows=windows)


def launch_console(
    config: ConsoleConfig,
    *,
    detach: bool = False,
    kill: bool = False,
) -> None:
    """Lance la session tmux.

    Crée la session, fenêtres et panneaux, puis attache.
    Si la session existe : réattache (ou --kill pour recréer).
    """
    if not config.windows:
        return

    if _session_exists(config.session_name):
        if kill:
            _tmux_run("kill-session", "-t", config.session_name)
        elif not detach:
            _tmux_interactive("attach-session", "-t", config.session_name)
            return
        else:
            return

    plans = _build_window_plans(config)
    if not plans:
        return

    status_bg = STATUS_COLORS.get(config.status_color, config.status_color)

    for idx, plan in enumerate(plans):
        if idx == 0:
            _tmux_run(
                "new-session",
                "-d",
                "-s",
                config.session_name,
                "-n",
                plan.name,
                plan.panes[0].command,
            )
            _setup_session(config.session_name, status_bg)
        else:
            _tmux_run(
                "new-window",
                "-t",
                config.session_name,
                "-n",
                plan.name,
                plan.panes[0].command,
            )

        window_target = f"{config.session_name}:{plan.name}"

        for i, pane in enumerate(plan.panes):
            if i > 0:
                _tmux_run(
                    "split-window",
                    "-t",
                    window_target,
                    "-v",
                    pane.command,
                )
            _tmux_run(
                "select-pane",
                "-t",
                f"{window_target}.{i}",
                "-T",
                f"[{pane.domain}] {pane.instance}",
            )

        _apply_layout(window_target, len(plan.panes))

        tc = TRUST_COLORS.get(plan.trust_level)
        color = tc.ansi if tc else "colour220"
        fg = tc.fg if tc else "black"
        _apply_window_colors(window_target, color, fg)

    _tmux_run(
        "select-window",
        "-t",
        f"{config.session_name}:{plans[0].name}",
    )

    if not detach:
        _tmux_interactive("attach-session", "-t", config.session_name)
