"""Doctor — diagnostic automatique de l'infrastructure.

Vérifie l'état du système (binaires, GPU, domaines, réseau)
et suggère des corrections.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Literal

from anklume.engine.incus_driver import IncusDriver
from anklume.engine.models import Infrastructure
from anklume.engine.ops import compute_network_status

log = logging.getLogger(__name__)

CheckStatus = Literal["ok", "warning", "error"]


@dataclass
class CheckResult:
    """Résultat d'une vérification."""

    name: str
    status: CheckStatus
    message: str
    fix_command: str | None = None


@dataclass
class DoctorReport:
    """Rapport complet de diagnostic."""

    checks: list[CheckResult] = field(default_factory=list)

    @property
    def ok_count(self) -> int:
        return sum(1 for c in self.checks if c.status == "ok")

    @property
    def warning_count(self) -> int:
        return sum(1 for c in self.checks if c.status == "warning")

    @property
    def error_count(self) -> int:
        return sum(1 for c in self.checks if c.status == "error")


def _check_binary(
    display_name: str,
    binary: str,
    severity_if_missing: CheckStatus = "error",
    missing_message: str = "",
) -> CheckResult:
    """Vérifie la présence d'un binaire dans le PATH."""
    path = shutil.which(binary)
    if path:
        return CheckResult(name=display_name, status="ok", message=f"installé ({path})")
    return CheckResult(
        name=display_name,
        status=severity_if_missing,
        message=missing_message or f"{binary} introuvable dans le PATH",
    )


def check_incus() -> CheckResult:
    """Vérifie qu'Incus est installé et accessible."""
    return _check_binary("Incus", "incus")


def check_nftables() -> CheckResult:
    """Vérifie que nftables est installé."""
    return _check_binary("nftables", "nft")


def check_ansible() -> CheckResult:
    """Vérifie qu'Ansible est installé."""
    return _check_binary(
        "Ansible",
        "ansible-playbook",
        severity_if_missing="warning",
        missing_message="ansible-playbook introuvable (provisioning indisponible)",
    )


def check_gpu() -> CheckResult:
    """Vérifie la présence et l'état du GPU."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            gpu_name = result.stdout.strip().splitlines()[0]
            return CheckResult(name="GPU", status="ok", message=gpu_name)
        return CheckResult(
            name="GPU",
            status="warning",
            message="nvidia-smi retourne une erreur",
        )
    except FileNotFoundError:
        return CheckResult(
            name="GPU",
            status="warning",
            message="nvidia-smi introuvable (GPU optionnel)",
        )
    except subprocess.TimeoutExpired:
        return CheckResult(name="GPU", status="warning", message="nvidia-smi timeout")


def check_domains(infra: Infrastructure) -> list[CheckResult]:
    """Vérifie la validité des domaines."""
    if not infra.domains:
        return [
            CheckResult(
                name="Domaines",
                status="warning",
                message="aucun domaine configuré",
            )
        ]

    return [
        CheckResult(
            name=f"Domaine {domain.name}",
            status="ok",
            message=(f"{len(domain.machines)} machine(s), trust={domain.trust_level}"),
        )
        for domain in infra.enabled_domains
    ]


def check_networks(
    infra: Infrastructure,
    driver: IncusDriver,
) -> list[CheckResult]:
    """Vérifie l'état des bridges réseau via compute_network_status."""
    net_status = compute_network_status(infra, driver)
    results: list[CheckResult] = []

    for net in net_status.networks:
        if net.exists:
            results.append(
                CheckResult(
                    name=f"Réseau {net.bridge}",
                    status="ok",
                    message="bridge actif",
                )
            )
        else:
            results.append(
                CheckResult(
                    name=f"Réseau {net.bridge}",
                    status="warning",
                    message="bridge absent",
                    fix_command="anklume apply all",
                )
            )

    return results


@dataclass
class DriftItem:
    """Un écart entre l'état désiré et l'état réel."""

    verb: str  # "create" | "start" | "stop" | "delete"
    resource: str  # "project" | "network" | "instance" | "profile"
    target: str  # nom de la ressource
    detail: str  # description lisible


def check_drift(
    infra: Infrastructure,
    driver: IncusDriver,
) -> list[DriftItem]:
    """Détecte le drift entre l'infrastructure déclarée et l'état réel.

    Exécute la réconciliation en dry_run et convertit les actions planifiées
    en items de drift.
    """
    from anklume.engine.reconciler import reconcile

    result = reconcile(infra, driver, dry_run=True)

    return [
        DriftItem(
            verb=action.verb,
            resource=action.resource,
            target=action.target,
            detail=action.detail,
        )
        for action in result.actions
    ]


def run_doctor(
    driver: IncusDriver | None = None,
    infra: Infrastructure | None = None,
    *,
    fix: bool = False,
    drift: bool = False,
) -> DoctorReport:
    """Exécute toutes les vérifications."""
    checks: list[CheckResult] = []

    # Checks système
    checks.append(check_incus())
    checks.append(check_nftables())
    checks.append(check_ansible())
    checks.append(check_gpu())

    # Checks infra (si disponible)
    if infra is not None:
        checks.extend(check_domains(infra))

        if driver is not None:
            checks.extend(check_networks(infra, driver))

    # Drift detection (si demandé + infra + driver disponibles)
    if drift and infra is not None and driver is not None:
        drift_items = check_drift(infra, driver)
        if drift_items:
            for item in drift_items:
                checks.append(
                    CheckResult(
                        name=f"Drift {item.resource}",
                        status="warning",
                        message=item.detail,
                        fix_command="anklume apply all",
                    )
                )
        else:
            checks.append(
                CheckResult(
                    name="Drift",
                    status="ok",
                    message="infrastructure synchronisée, aucun drift détecté",
                )
            )

    return DoctorReport(checks=checks)
