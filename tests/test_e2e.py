"""Tests E2E — vérifient le pipeline complet contre le vrai Incus.

Ces tests créent de vraies ressources Incus (projets, réseaux, instances)
avec le préfixe `e2e-` pour éviter les conflits. Nettoyage automatique.

Prérequis : Incus installé et configuré sur l'hôte.
"""

import os

import pytest
import yaml

from anklume.cli._apply import run_apply
from anklume.cli._init import run_init
from anklume.engine.addressing import assign_addresses
from anklume.engine.incus_driver import IncusDriver
from anklume.engine.parser import parse_project
from anklume.engine.reconciler import reconcile

from .conftest import write_test_project
from .incus_helpers import (
    cleanup_project,
    instance_config_get,
    instance_exists,
    instance_status,
    network_exists,
    project_exists,
)


@pytest.fixture()
def e2e_project(tmp_path, monkeypatch):
    """Crée un projet anklume temporaire et nettoie Incus après."""
    project_name = "e2e-alpha"
    monkeypatch.chdir(tmp_path)

    # Nettoyage préventif
    cleanup_project(project_name)

    yield tmp_path, project_name

    # Nettoyage post-test
    cleanup_project(project_name)


@pytest.fixture()
def e2e_multi_project(tmp_path, monkeypatch):
    """Crée un projet anklume avec 2 domaines et nettoie après."""
    projects = ["e2e-alpha", "e2e-beta"]
    monkeypatch.chdir(tmp_path)

    for p in projects:
        cleanup_project(p)

    yield tmp_path, projects

    for p in projects:
        cleanup_project(p)


class TestE2EApplyAll:
    """Pipeline complet : apply all crée les ressources dans Incus."""

    def test_creates_project_network_instance(self, e2e_project):
        path, project_name = e2e_project
        write_test_project(
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
        assert project_exists(project_name)
        assert network_exists(f"net-{project_name}", project_name)
        assert instance_exists(full_name, project_name)
        assert instance_status(full_name, project_name) == "Running"

    def test_protection_delete_set(self, e2e_project):
        path, project_name = e2e_project
        write_test_project(
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
        val = instance_config_get(full_name, project_name, "security.protection.delete")
        assert val == "true"

    def test_ephemeral_no_protection(self, e2e_project):
        path, project_name = e2e_project
        write_test_project(
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
        val = instance_config_get(full_name, project_name, "security.protection.delete")
        assert val != "true"


class TestE2EIdempotence:
    """Apply deux fois produit le même résultat."""

    def test_second_apply_no_changes(self, e2e_project):
        path, project_name = e2e_project
        write_test_project(
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
        assert instance_status(f"{project_name}-dev", project_name) == "Running"

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
        write_test_project(
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

        assert not project_exists(project_name)


class TestE2EApplyDomain:
    """Apply domain ne déploie qu'un seul domaine."""

    def test_only_specified_domain(self, e2e_multi_project):
        path, projects = e2e_multi_project
        write_test_project(
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

        assert project_exists(projects[0])
        assert not project_exists(projects[1])


class TestE2EStoppedInstance:
    """Une instance arrêtée est redémarrée par apply."""

    def test_restarts_stopped_instance(self, e2e_project):
        path, project_name = e2e_project
        write_test_project(
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
        assert instance_status(full_name, project_name) == "Running"

        # Arrêter l'instance manuellement
        from .incus_helpers import incus_run

        incus_run(["stop", full_name, "--project", project_name])
        assert instance_status(full_name, project_name) == "Stopped"

        # Second apply — doit redémarrer
        run_apply(dry_run=False)
        assert instance_status(full_name, project_name) == "Running"


@pytest.fixture()
def e2e_workflow(tmp_path, monkeypatch):
    """Crée un projet via anklume init et nettoie après."""
    project_name = "e2e-wflow"
    monkeypatch.chdir(tmp_path)
    cleanup_project(project_name)

    yield tmp_path, project_name

    cleanup_project(project_name)


class TestE2EDevWorkflow:
    """Workflow complet : init → configurer → apply → vérifier."""

    def test_init_configure_apply(self, e2e_workflow):
        path, project_name = e2e_workflow
        project_dir = path / "infra"

        # 1. anklume init
        run_init(str(project_dir))

        # 2. Changer le base d'adressage pour éviter conflit avec l'infra réelle
        anklume_yml = yaml.safe_load((project_dir / "anklume.yml").read_text())
        anklume_yml["addressing"]["base"] = "10.200"
        (project_dir / "anklume.yml").write_text(yaml.dump(anklume_yml))

        # 3. Remplacer le domaine par défaut par un nom E2E-safe
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

        # 4. Apply depuis le répertoire projet
        os.chdir(project_dir)
        run_apply(dry_run=False)

        # 5. Vérifier les ressources Incus
        full_name = f"{project_name}-dev"
        assert project_exists(project_name)
        assert network_exists(f"net-{project_name}", project_name)
        assert instance_exists(full_name, project_name)
        assert instance_status(full_name, project_name) == "Running"

        # 6. Idempotence — second apply ne change rien
        driver = IncusDriver()
        infra = parse_project(project_dir)
        assign_addresses(infra)
        result = reconcile(infra, driver, dry_run=True)
        assert len(result.actions) == 0, (
            f"Second apply devrait être idempotent : {[a.detail for a in result.actions]}"
        )
