"""Tests réels E2E dans VM KVM — anklume teste anklume.

Orchestre le cycle de vie d'une VM sandbox isolée :
1. Génère un domaine VM KVM dédié
2. L'applique via le pipeline anklume standard
3. Pousse le source anklume dans la VM
4. Exécute pytest (tests marqués @real) dans la VM
5. Collecte les résultats
6. Optionnellement détruit la VM
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from anklume.engine.incus_driver import IncusDriver, IncusError

log = logging.getLogger(__name__)

# Constantes du domaine sandbox
SANDBOX_DOMAIN = "e2e-sandbox"
SANDBOX_INSTANCE = f"{SANDBOX_DOMAIN}-runner"
SANDBOX_PROJECT = SANDBOX_DOMAIN
ANKLUME_VM_PATH = "/opt/anklume"


@dataclass
class E2eRealConfig:
    """Configuration d'exécution des tests réels."""

    memory: str = "8GiB"
    cpu: str = "8"
    keep_vm: bool = False
    test_filter: str = ""
    verbose: bool = False
    timeout: int = 600


@dataclass
class E2eRealResult:
    """Résultat de l'exécution des tests réels."""

    exit_code: int = 1
    stdout: str = ""
    stderr: str = ""
    duration_s: float = 0.0
    tests_passed: int = 0
    tests_failed: int = 0
    tests_errors: int = 0
    phase: str = ""
    errors: list[str] = field(default_factory=list)


def generate_e2e_project(config: E2eRealConfig) -> Path:
    """Génère un projet anklume temporaire avec le domaine sandbox.

    Returns:
        Chemin du répertoire projet temporaire.
    """
    project_dir = Path(tempfile.mkdtemp(prefix="anklume-e2e-"))

    # anklume.yml — base 10.200 pour éviter les conflits
    anklume_yml = {
        "schema_version": 1,
        "defaults": {
            "os_image": "images:debian/13",
            "trust_level": "semi-trusted",
        },
        "addressing": {"base": "10.200", "zone_step": 10},
        "nesting": {"prefix": True},
    }
    (project_dir / "anklume.yml").write_text(yaml.dump(anklume_yml, default_flow_style=False))

    # Domaine VM sandbox
    domain = {
        "description": "Sandbox de tests réels E2E",
        "trust_level": "admin",
        "machines": {
            "runner": {
                "description": "VM KVM pour tests E2E isolés",
                "type": "vm",
                "roles": ["base", "e2e_runner"],
                "config": {
                    "limits.memory": config.memory,
                    "limits.cpu": config.cpu,
                    "security.nesting": "true",
                },
            },
        },
    }
    domains_dir = project_dir / "domains"
    domains_dir.mkdir()
    (domains_dir / f"{SANDBOX_DOMAIN}.yml").write_text(
        yaml.dump(domain, default_flow_style=False, allow_unicode=True, sort_keys=False)
    )

    # policies.yml (vide)
    (project_dir / "policies.yml").write_text(yaml.dump({"policies": []}, default_flow_style=False))

    log.info("Projet E2E sandbox créé : %s", project_dir)
    return project_dir


def wait_for_vm_ready(
    driver: IncusDriver,
    project: str,
    instance: str,
    *,
    timeout: int = 180,
    interval: int = 5,
) -> bool:
    """Attend que la VM soit prête (cloud-init terminé).

    Vérifie que la VM répond à `cat /etc/hostname` via incus exec.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            driver.instance_exec(instance, project, ["cat", "/etc/hostname"])
            return True
        except IncusError:
            log.debug("VM pas encore prête, attente %ds...", interval)
            time.sleep(interval)
    return False


def push_source_to_vm(
    driver: IncusDriver,
    project: str,
    instance: str,
) -> None:
    """Pousse le source anklume dans la VM via tar + incus file push.

    Crée une archive tar du source (sans .git, __pycache__, .venv),
    la pousse dans la VM, et l'extrait.
    """
    source_dir = _find_anklume_root()
    log.info("Packing source depuis %s", source_dir)

    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
        tar_path = tmp.name

    try:
        # Créer l'archive
        subprocess.run(
            [
                "tar",
                "czf",
                tar_path,
                "--exclude=.git",
                "--exclude=__pycache__",
                "--exclude=.venv",
                "--exclude=*.pyc",
                "--exclude=.ruff_cache",
                "--exclude=.pytest_cache",
                "--exclude=.mypy_cache",
                "-C",
                str(source_dir),
                ".",
            ],
            check=True,
            capture_output=True,
        )

        # Pousser l'archive dans la VM
        driver.file_push(instance, project, tar_path, f"{ANKLUME_VM_PATH}/source.tar.gz")

        # Extraire dans la VM
        driver.instance_exec(
            instance,
            project,
            ["tar", "xzf", f"{ANKLUME_VM_PATH}/source.tar.gz", "-C", ANKLUME_VM_PATH],
        )

        # Nettoyer l'archive dans la VM
        driver.instance_exec(
            instance,
            project,
            ["rm", f"{ANKLUME_VM_PATH}/source.tar.gz"],
        )
    finally:
        Path(tar_path).unlink(missing_ok=True)


def install_deps_in_vm(
    driver: IncusDriver,
    project: str,
    instance: str,
) -> None:
    """Installe les dépendances de test dans la VM.

    SETUPTOOLS_SCM_PRETEND_VERSION est nécessaire car le source
    est poussé sans .git/ (hatch-vcs ne peut pas détecter la version).
    """
    driver.instance_exec(
        instance,
        project,
        [
            "bash",
            "-c",
            f"cd {ANKLUME_VM_PATH} "
            "&& export SETUPTOOLS_SCM_PRETEND_VERSION=0.0.0+e2e "
            "&& /root/.local/bin/uv sync --group dev",
        ],
    )


def run_tests_in_vm(
    driver: IncusDriver,
    project: str,
    instance: str,
    config: E2eRealConfig,
) -> E2eRealResult:
    """Exécute pytest dans la VM et collecte les résultats."""
    start = time.monotonic()

    cmd_parts = [
        f"cd {ANKLUME_VM_PATH}",
        "&&",
        "/root/.local/bin/uv",
        "run",
        "pytest",
        "tests/test_e2e_real.py",
        "-m",
        "real",
        "-v",
        "--tb=short",
    ]

    if config.test_filter:
        cmd_parts.extend(["-k", config.test_filter])

    cmd_str = " ".join(cmd_parts)

    try:
        result = driver.instance_exec(
            instance,
            project,
            ["bash", "-c", cmd_str],
            check=False,
            timeout=config.timeout,
        )

        duration = time.monotonic() - start
        passed, failed, errors = _parse_pytest_summary(result.stdout)

        return E2eRealResult(
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            duration_s=duration,
            tests_passed=passed,
            tests_failed=failed,
            tests_errors=errors,
            phase="tests",
        )

    except subprocess.TimeoutExpired:
        return E2eRealResult(
            exit_code=124,
            duration_s=time.monotonic() - start,
            phase="tests",
            errors=[f"Timeout après {config.timeout}s"],
        )


def cleanup_sandbox(project: str = SANDBOX_PROJECT) -> None:
    """Supprime le projet sandbox (instances, réseaux, projet) via IncusDriver."""
    driver = IncusDriver()

    if not driver.project_exists(project):
        return

    # Arrêter et supprimer les instances
    for inst in driver.instance_list(project):
        try:
            driver.instance_config_set(inst.name, project, "security.protection.delete", "false")
            if inst.status == "Running":
                driver.instance_stop(inst.name, project)
            driver.instance_delete(inst.name, project)
        except IncusError:
            log.debug("Cleanup instance %s ignorée", inst.name)

    # Supprimer les réseaux managés (type bridge = managé par Incus)
    for net in driver.network_list(project):
        if net.type == "bridge":
            try:
                driver.network_delete(net.name, project)
            except IncusError:
                log.debug("Cleanup réseau %s ignorée", net.name)

    # Supprimer le projet
    try:
        driver.project_delete(project)
    except IncusError:
        log.debug("Cleanup projet %s ignorée", project)


def _find_anklume_root() -> Path:
    """Trouve la racine du repo anklume."""
    candidate = Path(__file__).resolve().parent.parent.parent.parent
    if (candidate / "pyproject.toml").exists():
        return candidate
    msg = f"Racine anklume introuvable depuis {__file__}"
    raise FileNotFoundError(msg)


def _parse_pytest_summary(stdout: str) -> tuple[int, int, int]:
    """Extrait passed/failed/errors depuis la sortie pytest."""
    import re

    passed = failed = errors = 0
    for line in stdout.splitlines():
        if "passed" in line or "failed" in line or "error" in line:
            m_passed = re.search(r"(\d+) passed", line)
            m_failed = re.search(r"(\d+) failed", line)
            m_errors = re.search(r"(\d+) error", line)
            if m_passed:
                passed = int(m_passed.group(1))
            if m_failed:
                failed = int(m_failed.group(1))
            if m_errors:
                errors = int(m_errors.group(1))
    return passed, failed, errors
