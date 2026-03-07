"""Environnement behave — setup/teardown pour les scénarios BDD."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from anklume.engine.incus_driver import (
    IncusDriver,
    IncusNetwork,
    IncusProject,
)


def before_scenario(context, scenario):
    """Prépare un contexte propre pour chaque scénario."""
    context.tmpdir = Path(tempfile.mkdtemp())
    context.domains = {}
    context.driver = MagicMock(spec=IncusDriver)
    context.result = None
    context.exit_code = 0

    # État Incus simulé
    context.existing_projects = []
    context.existing_networks = {}  # project -> [IncusNetwork]
    context.existing_instances = {}  # project -> [IncusInstance]

    # Historique des appels pour vérification
    context.created_projects = []
    context.created_networks = []
    context.created_instances = []
    context.started_instances = []
    context.fail_project_create = set()

    _setup_driver_mock(context)


def _setup_driver_mock(context):
    """Configure le mock du driver selon l'état simulé."""
    driver = context.driver

    def project_list():
        return [IncusProject(name=p) for p in context.existing_projects]

    def project_exists(name):
        return name in context.existing_projects

    def project_create(name, description=""):
        if name in context.fail_project_create:
            from anklume.engine.incus_driver import IncusError

            raise IncusError(
                command=["incus", "project", "create", name],
                returncode=1,
                stderr=f"failed to create {name}",
            )
        context.created_projects.append(name)
        context.existing_projects.append(name)

    def network_list(project):
        return context.existing_networks.get(project, [])

    def network_exists(name, project):
        return any(n.name == name for n in context.existing_networks.get(project, []))

    def network_create(name, project, config=None):
        context.created_networks.append({"name": name, "project": project, "config": config})
        nets = context.existing_networks.setdefault(project, [])
        nets.append(IncusNetwork(name=name, config=config or {}))

    def instance_list(project):
        return context.existing_instances.get(project, [])

    def instance_create(name, project, image, instance_type="container", **kwargs):
        context.created_instances.append(
            {"name": name, "project": project, "image": image, "type": instance_type, **kwargs}
        )

    def instance_start(name, project):
        context.started_instances.append({"name": name, "project": project})

    driver.project_list.side_effect = project_list
    driver.project_exists.side_effect = project_exists
    driver.project_create.side_effect = project_create
    driver.network_list.side_effect = network_list
    driver.network_exists.side_effect = network_exists
    driver.network_create.side_effect = network_create
    driver.instance_list.side_effect = instance_list
    driver.instance_create.side_effect = instance_create
    driver.instance_start.side_effect = instance_start


def after_scenario(context, scenario):
    """Nettoyage après chaque scénario."""
    import shutil

    shutil.rmtree(context.tmpdir, ignore_errors=True)
