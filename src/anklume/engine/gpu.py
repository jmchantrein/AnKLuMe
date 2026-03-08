"""GPU passthrough — détection, validation et profils.

Détecte le GPU hôte via nvidia-smi, valide la cohérence gpu: true
sur les machines, et enrichit les profils Incus pour le passthrough.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass

from anklume.engine.models import Infrastructure

log = logging.getLogger(__name__)

GPU_PROFILE_NAME = "gpu-passthrough"


@dataclass
class GpuInfo:
    """Informations GPU détectées sur l'hôte."""

    detected: bool
    model: str
    vram_total_mib: int
    vram_used_mib: int

    @classmethod
    def none(cls) -> GpuInfo:
        """Sentinel : aucun GPU détecté."""
        return cls(detected=False, model="", vram_total_mib=0, vram_used_mib=0)


def detect_gpu() -> GpuInfo:
    """Détecte la présence d'un GPU NVIDIA via nvidia-smi."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.used",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return GpuInfo.none()

    if result.returncode != 0:
        return GpuInfo.none()

    return _parse_nvidia_smi(result.stdout)


def _parse_nvidia_smi(stdout: str) -> GpuInfo:
    """Parse la sortie CSV de nvidia-smi (première ligne)."""
    for line in stdout.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 3:
            try:
                return GpuInfo(
                    detected=True,
                    model=parts[0],
                    vram_total_mib=int(parts[1]),
                    vram_used_mib=int(parts[2]),
                )
            except ValueError:
                break
    return GpuInfo.none()


def validate_gpu_machines(
    infra: Infrastructure,
    gpu_info: GpuInfo,
) -> list[str]:
    """Valide la cohérence gpu: true sur les machines.

    Retourne une liste de messages d'erreur (vide = ok).
    """
    errors: list[str] = []

    gpu_machines: list[str] = []
    for domain in infra.enabled_domains:
        for machine in domain.machines.values():
            if machine.gpu:
                if not gpu_info.detected:
                    errors.append(
                        f"Machine '{machine.full_name}' requiert un GPU "
                        f"(gpu: true) mais aucun GPU détecté sur l'hôte"
                    )
                gpu_machines.append(machine.full_name)

    # Vérifier la politique si GPU détecté et plusieurs machines GPU
    if gpu_info.detected and len(gpu_machines) > 1:
        policy = "exclusive"
        if infra.config.gpu_policy is not None:
            policy = infra.config.gpu_policy.policy

        if policy == "exclusive":
            names = ", ".join(gpu_machines)
            errors.append(
                f"Politique GPU exclusive : plusieurs machines GPU "
                f"détectées ({names}). Utiliser gpu_policy: shared "
                f"ou retirer gpu: true"
            )

    return errors


def apply_gpu_profiles(infra: Infrastructure) -> GpuInfo:
    """Détecte le GPU et enrichit les profils des machines gpu: true.

    Ajoute 'gpu-passthrough' aux profils de chaque machine avec
    gpu: true dans les domaines activés, si un GPU est détecté.

    Retourne GpuInfo pour usage ultérieur.
    """
    gpu_info = detect_gpu()

    if not gpu_info.detected:
        return gpu_info

    for domain in infra.enabled_domains:
        for machine in domain.machines.values():
            if machine.gpu and GPU_PROFILE_NAME not in machine.profiles:
                machine.profiles.append(GPU_PROFILE_NAME)

    return gpu_info
