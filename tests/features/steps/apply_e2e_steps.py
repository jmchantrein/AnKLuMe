"""Steps behave E2E — vérifications contre Incus réel."""

from __future__ import annotations

import subprocess

from behave import then, when
from tests.incus_helpers import (
    instance_config_get,
    instance_exists,
    instance_status,
    network_exists,
    project_exists,
)

# ============================================================
# When — Actions E2E
# ============================================================


@when('j\'arrête l\'instance "{name}" dans le projet "{project}"')
def step_arreter_instance(context, name, project):
    """Arrête une instance réelle dans Incus (force pour éviter les timeouts)."""
    result = subprocess.run(
        ["incus", "stop", name, "--project", project, "--force"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Échec arrêt {name}: {result.stderr}"


# ============================================================
# Then — Vérifications E2E
# ============================================================


@then('le projet Incus "{name}" existe dans Incus')
def step_projet_existe_incus(context, name):
    assert project_exists(name), f"Projet '{name}' introuvable dans Incus"


@then('le projet Incus "{name}" n\'existe pas dans Incus')
def step_projet_non_existe_incus(context, name):
    assert not project_exists(name), f"Projet '{name}' existe dans Incus alors qu'il ne devrait pas"


@then('le réseau "{name}" existe dans le projet Incus "{project}"')
def step_reseau_existe_incus(context, name, project):
    assert network_exists(name, project), f"Réseau '{name}' introuvable dans le projet '{project}'"


@then('l\'instance "{name}" existe dans le projet Incus "{project}"')
def step_instance_existe_incus(context, name, project):
    assert instance_exists(name, project), (
        f"Instance '{name}' introuvable dans le projet '{project}'"
    )


@then('l\'instance "{name}" a le statut "{status}" dans le projet Incus "{project}"')
def step_instance_statut_incus(context, name, status, project):
    actual = instance_status(name, project)
    assert actual == status, f"Instance '{name}' a le statut '{actual}', attendu '{status}'"


@then('la config Incus "{key}" de "{instance}" dans "{project}" vaut "{value}"')
def step_config_incus_vaut(context, key, instance, project, value):
    actual = instance_config_get(instance, project, key)
    assert actual == value, f"Config '{key}' de '{instance}': '{actual}', attendu '{value}'"


@then('la config Incus "{key}" de "{instance}" dans "{project}" ne vaut pas "{value}"')
def step_config_incus_ne_vaut_pas(context, key, instance, project, value):
    actual = instance_config_get(instance, project, key)
    assert actual != value, (
        f"Config '{key}' de '{instance}' vaut '{value}' alors qu'elle ne devrait pas"
    )


@then("le résultat de réconciliation est vide")
def step_resultat_vide(context):
    assert context.result is not None, "Pas de résultat de réconciliation"
    assert len(context.result.actions) == 0, (
        f"Le plan contient {len(context.result.actions)} action(s), attendu 0 : "
        f"{[a.detail for a in context.result.actions]}"
    )
