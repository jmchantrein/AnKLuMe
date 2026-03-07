"""Tests E2E — vérifient le pipeline complet contre le vrai Incus.

Ces tests créent de vraies ressources Incus (projets, réseaux, instances)
avec le préfixe `e2e-` pour éviter les conflits. Nettoyage automatique.

Prérequis : Incus installé et configuré sur l'hôte.
"""

import json
import os
import subprocess

import pytest
import yaml

from anklume.cli._apply import run_apply
from anklume.cli._init import run_init
from anklume.engine.addressing import assign_addresses
from anklume.engine.incus_driver import IncusDriver
from anklume.engine.parser import parse_project
from anklume.engine.reconciler import reconcile


def _incus_json(args: list[str]) -> list | dict:
    """Appel incus direct avec sortie JSON."""
    result = subprocess.run(
        ["incus", *args, "--format", "json"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(f"incus {' '.join(args)} a échoué : {result.stderr}")
    return json.loads(result.stdout)


def _incus_run(args: list[str]) -> None:
    """Appel incus direct sans sortie."""
    result = subprocess.run(["incus", *args], capture_output=True, text=True)
    if result.returncode != 0:
        pytest.fail(f"incus {' '.join(args)} a échoué : {result.stderr}")


def _project_exists(name: str) -> bool:
    projects = _incus_json(["project", "list"])
    return any(p["name"] == name for p in projects)


def _network_exists(name: str, project: str) -> bool:
    networks = _incus_json(["network", "list", "--project", project])
    return any(n["name"] == name for n in networks)


def _instance_exists(name: str, project: str) -> bool:
    instances = _incus_json(["list", "--project", project])
    return any(i["name"] == name for i in instances)


def _instance_status(name: str, project: str) -> str:
    instances = _incus_json(["list", "--project", project])
    for i in instances:
        if i["name"] == name:
            return i["status"]
    return "NotFound"


def _instance_config_get(name: str, project: str, key: str) -> str:
    """Lire une clé de config spécifique via `incus config get`."""
    result = subprocess.run(
        ["incus", "config", "get", name, key, "--project", project],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _cleanup_project(name: str) -> None:
    """Nettoyer un projet E2E : arrêter/supprimer instances, réseau, projet."""
    if not _project_exists(name):
        return

    # Supprimer les instances
    instances = _incus_json(["list", "--project", name])
    for inst in instances:
        inst_name = inst["name"]
        # Retirer la protection delete si présente
        subprocess.run(
            [
                "incus",
                "config",
                "set",
                inst_name,
                "security.protection.delete=false",
                "--project",
                name,
            ],
            capture_output=True,
        )
        if inst["status"] == "Running":
            subprocess.run(
                ["incus", "stop", inst_name, "--project", name, "--force"],
                capture_output=True,
            )
        subprocess.run(
            ["incus", "delete", inst_name, "--project", name, "--force"],
            capture_output=True,
        )

    # Supprimer les réseaux
    networks = _incus_json(["network", "list", "--project", name])
    for net in networks:
        if net["managed"]:
            subprocess.run(
                ["incus", "network", "delete", net["name"], "--project", name],
                capture_output=True,
            )

    # Supprimer le projet
    subprocess.run(["incus", "project", "delete", name], capture_output=True)


@pytest.fixture()
def e2e_project(tmp_path, monkeypatch):
    """Crée un projet anklume temporaire et nettoie Incus après."""
    project_name = "e2e-alpha"
    monkeypatch.chdir(tmp_path)

    # Nettoyage préventif
    _cleanup_project(project_name)

    yield tmp_path, project_name

    # Nettoyage post-test
    _cleanup_project(project_name)


@pytest.fixture()
def e2e_multi_project(tmp_path, monkeypatch):
    """Crée un projet anklume avec 2 domaines et nettoie après."""
    projects = ["e2e-alpha", "e2e-beta"]
    monkeypatch.chdir(tmp_path)

    for p in projects:
        _cleanup_project(p)

    yield tmp_path, projects

    for p in projects:
        _cleanup_project(p)


def _write_project(path, domains: dict, schema_version: int = 1):
    """Écrire un projet anklume complet."""
    (path / "anklume.yml").write_text(
        yaml.dump(
            {
                "schema_version": schema_version,
                "defaults": {"os_image": "images:debian/13", "trust_level": "semi-trusted"},
                "addressing": {"base": "10.100", "zone_step": 10},
                "nesting": {"prefix": True},
            }
        )
    )

    domains_dir = path / "domains"
    domains_dir.mkdir(exist_ok=True)
    for name, data in domains.items():
        (domains_dir / f"{name}.yml").write_text(yaml.dump(data))

    (path / "policies.yml").write_text(yaml.dump({"policies": []}))


class TestE2EApplyAll:
    """Pipeline complet : apply all crée les ressources dans Incus."""

    def test_creates_project_network_instance(self, e2e_project):
        path, project_name = e2e_project
        _write_project(
            path,
            {
                project_name: {
                    "description": "E2E test domain",
                    "trust_level": "semi-trusted",
                    "machines": {
                        "dev": {"description": "E2E dev", "type": "lxc"},
                    },
                },
            },
        )

        run_apply(dry_run=False)

        full_name = f"{project_name}-dev"
        assert _project_exists(project_name)
        assert _network_exists(f"net-{project_name}", project_name)
        assert _instance_exists(full_name, project_name)
        assert _instance_status(full_name, project_name) == "Running"

    def test_protection_delete_set(self, e2e_project):
        path, project_name = e2e_project
        _write_project(
            path,
            {
                project_name: {
                    "description": "E2E test",
                    "trust_level": "semi-trusted",
                    "machines": {
                        "protected": {"description": "Protected", "type": "lxc"},
                    },
                },
            },
        )

        run_apply(dry_run=False)

        full_name = f"{project_name}-protected"
        val = _instance_config_get(full_name, project_name, "security.protection.delete")
        assert val == "true"

    def test_ephemeral_no_protection(self, e2e_project):
        path, project_name = e2e_project
        _write_project(
            path,
            {
                project_name: {
                    "description": "E2E test",
                    "trust_level": "semi-trusted",
                    "ephemeral": True,
                    "machines": {
                        "tmp": {"description": "Ephemeral", "type": "lxc"},
                    },
                },
            },
        )

        run_apply(dry_run=False)

        full_name = f"{project_name}-tmp"
        val = _instance_config_get(full_name, project_name, "security.protection.delete")
        assert val != "true"


class TestE2EIdempotence:
    """Apply deux fois produit le même résultat."""

    def test_second_apply_no_changes(self, e2e_project):
        path, project_name = e2e_project
        _write_project(
            path,
            {
                project_name: {
                    "description": "E2E idempotence",
                    "trust_level": "semi-trusted",
                    "machines": {
                        "dev": {"description": "E2E dev", "type": "lxc"},
                    },
                },
            },
        )

        # Premier apply
        run_apply(dry_run=False)
        assert _instance_status(f"{project_name}-dev", project_name) == "Running"

        # Second apply — doit être idempotent
        driver = IncusDriver()

        infra = parse_project(path)
        assign_addresses(infra)
        result = reconcile(infra, driver, dry_run=True)

        assert len(result.actions) == 0, (
            f"Le second apply devrait ne rien faire, mais planifie : "
            f"{[a.detail for a in result.actions]}"
        )


class TestE2EDryRun:
    """Dry-run ne crée rien dans Incus."""

    def test_dry_run_creates_nothing(self, e2e_project):
        path, project_name = e2e_project
        _write_project(
            path,
            {
                project_name: {
                    "description": "E2E dry-run",
                    "trust_level": "semi-trusted",
                    "machines": {
                        "dev": {"description": "E2E dev", "type": "lxc"},
                    },
                },
            },
        )

        run_apply(dry_run=True)

        assert not _project_exists(project_name)


class TestE2EApplyDomain:
    """Apply domain ne déploie qu'un seul domaine."""

    def test_only_specified_domain(self, e2e_multi_project):
        path, projects = e2e_multi_project
        _write_project(
            path,
            {
                projects[0]: {
                    "description": "Alpha",
                    "trust_level": "semi-trusted",
                    "machines": {"a": {"description": "A", "type": "lxc"}},
                },
                projects[1]: {
                    "description": "Beta",
                    "trust_level": "semi-trusted",
                    "machines": {"b": {"description": "B", "type": "lxc"}},
                },
            },
        )

        run_apply(domain_name=projects[0], dry_run=False)

        assert _project_exists(projects[0])
        assert not _project_exists(projects[1])


class TestE2EStoppedInstance:
    """Une instance arrêtée est redémarrée par apply."""

    def test_restarts_stopped_instance(self, e2e_project):
        path, project_name = e2e_project
        _write_project(
            path,
            {
                project_name: {
                    "description": "E2E restart",
                    "trust_level": "semi-trusted",
                    "machines": {
                        "dev": {"description": "E2E dev", "type": "lxc"},
                    },
                },
            },
        )

        full_name = f"{project_name}-dev"

        # Premier apply
        run_apply(dry_run=False)
        assert _instance_status(full_name, project_name) == "Running"

        # Arrêter l'instance manuellement
        _incus_run(["stop", full_name, "--project", project_name])
        assert _instance_status(full_name, project_name) == "Stopped"

        # Second apply — doit redémarrer
        run_apply(dry_run=False)
        assert _instance_status(full_name, project_name) == "Running"


@pytest.fixture()
def e2e_workflow(tmp_path, monkeypatch):
    """Crée un projet via anklume init et nettoie après."""
    project_name = "e2e-wflow"
    monkeypatch.chdir(tmp_path)
    _cleanup_project(project_name)

    yield tmp_path, project_name

    _cleanup_project(project_name)


class TestE2EDevWorkflow:
    """Workflow complet : init → configurer → apply → vérifier."""

    def test_init_configure_apply(self, e2e_workflow):
        path, project_name = e2e_workflow
        project_dir = path / "infra"

        # 1. anklume init
        run_init(str(project_dir))

        # 2. Remplacer le domaine par défaut par un nom E2E-safe
        (project_dir / "domains" / "pro.yml").unlink()
        (project_dir / "domains" / f"{project_name}.yml").write_text(
            yaml.dump(
                {
                    "description": "E2E workflow test",
                    "trust_level": "semi-trusted",
                    "machines": {
                        "dev": {"description": "Development", "type": "lxc"},
                    },
                }
            )
        )

        # 3. Apply depuis le répertoire projet
        os.chdir(project_dir)
        run_apply(dry_run=False)

        # 4. Vérifier les ressources Incus
        full_name = f"{project_name}-dev"
        assert _project_exists(project_name)
        assert _network_exists(f"net-{project_name}", project_name)
        assert _instance_exists(full_name, project_name)
        assert _instance_status(full_name, project_name) == "Running"

        # 5. Idempotence — second apply ne change rien
        driver = IncusDriver()
        infra = parse_project(project_dir)
        assign_addresses(infra)
        result = reconcile(infra, driver, dry_run=True)
        assert len(result.actions) == 0, (
            f"Second apply devrait être idempotent : {[a.detail for a in result.actions]}"
        )
