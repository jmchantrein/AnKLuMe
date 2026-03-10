"""Dev setup — préparation de l'environnement de développement anklume.

Vérifie et configure : Incus, dépendances dev, hooks git.
"""

from __future__ import annotations

import logging
import shutil
import stat
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

log = logging.getLogger(__name__)

StepStatus = Literal["ok", "warning", "error"]

# Binaires optionnels vérifiés par dev setup
_DEV_BINARIES: list[tuple[str, str, StepStatus]] = [
    ("ruff", "ruff (lint + format)", "warning"),
    ("ansible-playbook", "ansible-playbook (provisioning)", "warning"),
    ("molecule", "molecule (tests rôles Ansible)", "warning"),
]


@dataclass
class SetupStep:
    """Résultat d'une étape de setup."""

    name: str
    status: StepStatus
    message: str
    skipped: bool = False


@dataclass
class DevSetupReport:
    """Rapport complet du dev setup."""

    steps: list[SetupStep] = field(default_factory=list)

    @property
    def ok_count(self) -> int:
        return sum(1 for s in self.steps if s.status == "ok")

    @property
    def warning_count(self) -> int:
        return sum(1 for s in self.steps if s.status == "warning")

    @property
    def error_count(self) -> int:
        return sum(1 for s in self.steps if s.status == "error")

    @property
    def success(self) -> bool:
        return self.error_count == 0


def check_incus_available() -> SetupStep:
    """Vérifie qu'Incus est installé et accessible."""
    path = shutil.which("incus")
    if not path:
        return SetupStep(
            name="Incus",
            status="error",
            message="incus introuvable dans le PATH",
        )

    try:
        result = subprocess.run(
            ["incus", "project", "list", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return SetupStep(
                name="Incus",
                status="error",
                message=f"incus accessible mais erreur : {result.stderr.strip()[:100]}",
            )
        return SetupStep(
            name="Incus",
            status="ok",
            message=f"installé ({path}), accès vérifié",
        )
    except subprocess.TimeoutExpired:
        return SetupStep(
            name="Incus",
            status="error",
            message="incus timeout (daemon injoignable ?)",
        )


def check_dev_dependencies() -> list[SetupStep]:
    """Vérifie la présence des outils de développement."""
    steps: list[SetupStep] = []
    for binary, display, severity in _DEV_BINARIES:
        path = shutil.which(binary)
        if path:
            steps.append(SetupStep(
                name=binary,
                status="ok",
                message=f"installé ({path})",
            ))
        else:
            steps.append(SetupStep(
                name=binary,
                status=severity,
                message=f"{display} introuvable",
            ))
    return steps


def check_git_hooks(project_root: Path) -> SetupStep:
    """Vérifie que le pre-commit hook est installé et exécutable."""
    hook = project_root / ".git" / "hooks" / "pre-commit"
    if not hook.exists():
        return SetupStep(
            name="Hooks git",
            status="warning",
            message="pre-commit hook absent",
        )

    if not hook.stat().st_mode & stat.S_IXUSR:
        return SetupStep(
            name="Hooks git",
            status="warning",
            message="pre-commit hook présent mais pas exécutable",
        )

    return SetupStep(
        name="Hooks git",
        status="ok",
        message="pre-commit hook installé",
    )


def install_git_hooks(
    project_root: Path,
    source_hook: Path | None = None,
) -> SetupStep:
    """Installe le pre-commit hook s'il est absent.

    Args:
        project_root: Racine du projet git.
        source_hook: Chemin du hook source. Si None, utilise hooks/pre-commit
                     à la racine du projet.
    """
    hooks_dir = project_root / ".git" / "hooks"
    target = hooks_dir / "pre-commit"

    if target.exists() and target.stat().st_mode & stat.S_IXUSR:
        return SetupStep(
            name="Hooks git",
            status="ok",
            message="pre-commit hook déjà installé",
            skipped=True,
        )

    if source_hook is None:
        source_hook = project_root / "hooks" / "pre-commit"

    if not source_hook.exists():
        return SetupStep(
            name="Hooks git",
            status="warning",
            message=f"hook source introuvable : {source_hook}",
        )

    hooks_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_hook, target)
    target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    return SetupStep(
        name="Hooks git",
        status="ok",
        message="pre-commit hook installé",
    )


def run_dev_setup(
    *,
    project_root: Path | None = None,
    install_hooks: bool = True,
) -> DevSetupReport:
    """Exécute le setup complet de l'environnement de développement.

    Étapes :
    1. Vérifier Incus (installé + accessible)
    2. Vérifier les dépendances dev (ruff, ansible, molecule)
    3. Vérifier/installer les hooks git
    """
    if project_root is None:
        project_root = Path.cwd()

    report = DevSetupReport()

    # 1. Incus
    report.steps.append(check_incus_available())

    # 2. Dépendances dev
    report.steps.extend(check_dev_dependencies())

    # 3. Hooks git
    if install_hooks:
        report.steps.append(install_git_hooks(project_root))
    else:
        report.steps.append(check_git_hooks(project_root))

    return report
