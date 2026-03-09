"""Console tmux — session colorée par domaine.

Crée une session tmux avec une fenêtre par domaine et un panneau
par instance. Code couleur par trust level.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field

from anklume.engine.incus_driver import IncusDriver
from anklume.engine.models import TRUST_LEVELS, Infrastructure
from anklume.engine.nesting import NestingContext, prefix_name

log = logging.getLogger(__name__)

TRUST_COLORS: dict[str, str] = {
    "admin": "colour196",
    "trusted": "colour33",
    "semi-trusted": "colour220",
    "untrusted": "colour208",
    "disposable": "colour240",
}

# Vérification à l'import : chaque trust level a une couleur
if set(TRUST_COLORS) != set(TRUST_LEVELS):
    msg = f"TRUST_COLORS désynchronisé : {set(TRUST_COLORS)} != {set(TRUST_LEVELS)}"
    raise RuntimeError(msg)

SESSION_NAME = "anklume"


@dataclass
class ConsolePane:
    """Panneau tmux pour une instance."""

    instance: str
    domain: str
    trust_level: str
    command: str  # "incus exec <name> --project <proj> -- bash"


@dataclass
class ConsoleConfig:
    """Configuration tmux complète."""

    session_name: str
    windows: dict[str, list[ConsolePane]] = field(default_factory=dict)


def _tmux_run(*args: str) -> subprocess.CompletedProcess:
    """Exécute une commande tmux."""
    return subprocess.run(["tmux", *args], check=False)


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
                )
            )

        if panes:
            windows[dom.name] = panes

    return ConsoleConfig(session_name=session_name, windows=windows)


def launch_console(
    config: ConsoleConfig,
    *,
    detach: bool = False,
) -> None:
    """Lance la session tmux.

    Crée la session, fenêtres et panneaux, puis attache
    (ou détache avec detach=True).
    """
    if not config.windows:
        return

    first_window = True

    for domain_name, panes in config.windows.items():
        if first_window:
            _tmux_run(
                "new-session",
                "-d",
                "-s",
                config.session_name,
                "-n",
                domain_name,
            )
            first_window = False
        else:
            _tmux_run(
                "new-window",
                "-t",
                config.session_name,
                "-n",
                domain_name,
            )

        window_target = f"{config.session_name}:{domain_name}"

        for i, pane in enumerate(panes):
            if i > 0:
                _tmux_run("split-window", "-t", window_target, "-v")

            _tmux_run(
                "send-keys",
                "-t",
                f"{window_target}.{i}",
                pane.command,
                "Enter",
            )

        # Couleur de la status bar selon trust level
        color = TRUST_COLORS.get(panes[0].trust_level, "colour220")
        _tmux_run(
            "set-option",
            "-t",
            window_target,
            "window-status-current-style",
            f"bg={color}",
        )

        # Répartir les panneaux uniformément
        _tmux_run("select-layout", "-t", window_target, "tiled")

    if not detach:
        _tmux_run("attach-session", "-t", config.session_name)
