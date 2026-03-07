"""Steps behave pour les scénarios apply."""

from __future__ import annotations

import yaml
from behave import given, then

from anklume.engine.incus_driver import IncusInstance, IncusNetwork

# ============================================================
# Given — Contexte
# ============================================================


@given("un projet anklume valide avec la config par défaut")
def step_projet_valide(context):
    """Crée un projet anklume minimal dans le tmpdir."""
    project_dir = context.tmpdir
    config = {"schema_version": 1, "defaults": {"os_image": "images:debian/13"}}
    (project_dir / "anklume.yml").write_text(yaml.dump(config))
    (project_dir / "domains").mkdir(exist_ok=True)


@given('un domaine "{name}" avec la machine "{machine}" de type "{mtype}"')
def step_domaine_avec_machine(context, name, machine, mtype):
    """Ajoute un fichier domaine au projet."""
    domains_dir = context.tmpdir / "domains"
    domains_dir.mkdir(exist_ok=True)
    domain_data = {
        "description": f"Domaine {name}",
        "machines": {
            machine: {
                "description": f"Machine {machine}",
                "type": mtype,
            }
        },
    }
    (domains_dir / f"{name}.yml").write_text(yaml.dump(domain_data))


@given('un domaine désactivé "{name}" avec la machine "{machine}" de type "{mtype}"')
def step_domaine_desactive(context, name, machine, mtype):
    """Ajoute un domaine désactivé."""
    domains_dir = context.tmpdir / "domains"
    domains_dir.mkdir(exist_ok=True)
    domain_data = {
        "description": f"Domaine {name}",
        "enabled": False,
        "machines": {
            machine: {
                "description": f"Machine {machine}",
                "type": mtype,
            }
        },
    }
    (domains_dir / f"{name}.yml").write_text(yaml.dump(domain_data))


@given('un domaine éphémère "{name}" avec la machine "{machine}" de type "{mtype}"')
def step_domaine_ephemere(context, name, machine, mtype):
    """Ajoute un domaine éphémère."""
    domains_dir = context.tmpdir / "domains"
    domains_dir.mkdir(exist_ok=True)
    domain_data = {
        "description": f"Domaine {name}",
        "ephemeral": True,
        "machines": {
            machine: {
                "description": f"Machine {machine}",
                "type": mtype,
            }
        },
    }
    (domains_dir / f"{name}.yml").write_text(yaml.dump(domain_data))


@given('le projet Incus "{name}" existe déjà')
def step_projet_existe(context, name):
    """Simule un projet existant dans Incus."""
    if name not in context.existing_projects:
        context.existing_projects.append(name)


@given('le réseau "{name}" existe déjà dans le projet "{project}"')
def step_reseau_existe(context, name, project):
    """Simule un réseau existant dans Incus."""
    nets = context.existing_networks.setdefault(project, [])
    nets.append(IncusNetwork(name=name))


@given('l\'instance "{name}" existe et tourne dans le projet "{project}"')
def step_instance_running(context, name, project):
    """Simule une instance en cours d'exécution."""
    instances = context.existing_instances.setdefault(project, [])
    instances.append(IncusInstance(name=name, status="Running", type="container", project=project))


@given('l\'instance "{name}" existe et est arrêtée dans le projet "{project}"')
def step_instance_stopped(context, name, project):
    """Simule une instance arrêtée."""
    instances = context.existing_instances.setdefault(project, [])
    instances.append(IncusInstance(name=name, status="Stopped", type="container", project=project))


@given('la création du projet "{name}" échoue')
def step_creation_echoue(context, name):
    """Configure le mock pour que la création d'un projet échoue."""
    context.fail_project_create.add(name)


# ============================================================
# Then — Vérifications
# ============================================================


@then('le projet Incus "{name}" est créé')
def step_projet_cree(context, name):
    assert name in context.created_projects, (
        f"Projet {name} non créé. Créés : {context.created_projects}"
    )


@then('le projet Incus "{name}" n\'est pas créé')
def step_projet_non_cree(context, name):
    assert name not in context.created_projects, (
        f"Projet {name} a été créé alors qu'il ne devrait pas"
    )


@then('le réseau "{name}" est créé dans le projet "{project}"')
def step_reseau_cree(context, name, project):
    found = any(n["name"] == name and n["project"] == project for n in context.created_networks)
    assert found, f"Réseau {name} non créé dans {project}. Créés : {context.created_networks}"


@then('l\'instance "{name}" est créée dans le projet "{project}"')
def step_instance_creee(context, name, project):
    found = any(i["name"] == name and i["project"] == project for i in context.created_instances)
    assert found, f"Instance {name} non créée dans {project}. Créées : {context.created_instances}"


@then('l\'instance "{name}" est démarrée')
def step_instance_demarree(context, name):
    found = any(i["name"] == name for i in context.started_instances)
    assert found, f"Instance {name} non démarrée. Démarrées : {context.started_instances}"


@then("aucune action n'est exécutée sur Incus")
def step_aucune_action(context):
    assert len(context.created_projects) == 0, f"Projets créés : {context.created_projects}"
    assert len(context.created_networks) == 0, f"Réseaux créés : {context.created_networks}"
    assert len(context.created_instances) == 0, f"Instances créées : {context.created_instances}"
    assert len(context.started_instances) == 0, f"Instances démarrées : {context.started_instances}"


@then("le plan contient {count:d} actions")
def step_plan_actions(context, count):
    assert context.result is not None, "Pas de résultat de réconciliation"
    actual = len(context.result.actions)
    assert actual == count, f"Plan contient {actual} actions, attendu {count}"


@then("aucune création n'est effectuée")
def step_aucune_creation(context):
    assert len(context.created_projects) == 0
    assert len(context.created_networks) == 0
    assert len(context.created_instances) == 0


@then('l\'instance "{name}" est créée comme "{instance_type}"')
def step_instance_type(context, name, instance_type):
    found = next(
        (i for i in context.created_instances if i["name"] == name),
        None,
    )
    assert found is not None, f"Instance {name} non trouvée"
    assert found["type"] == instance_type, f"Type attendu {instance_type}, obtenu {found['type']}"


@then('l\'instance "{name}" a la config "{key}" à "{value}"')
def step_instance_config(context, name, key, value):
    found = next(
        (i for i in context.created_instances if i["name"] == name),
        None,
    )
    assert found is not None, f"Instance {name} non trouvée"
    config = found.get("config", {})
    assert key in config, f"Config {key} absente. Config : {config}"
    assert config[key] == value, f"Config {key}={config[key]}, attendu {value}"


@then('l\'instance "{name}" n\'a pas la config "{key}"')
def step_instance_no_config(context, name, key):
    found = next(
        (i for i in context.created_instances if i["name"] == name),
        None,
    )
    assert found is not None, f"Instance {name} non trouvée"
    config = found.get("config", {})
    assert key not in config, f"Config {key} présente alors qu'elle ne devrait pas"


@then("des erreurs sont rapportées")
def step_erreurs_rapportees(context):
    assert context.result is not None
    assert len(context.result.errors) > 0, "Aucune erreur rapportée"


@then('le réseau "{name}" est configuré avec le gateway du domaine "{domain}"')
def step_reseau_gateway(context, name, domain):
    found = next(
        (n for n in context.created_networks if n["name"] == name),
        None,
    )
    assert found is not None, f"Réseau {name} non trouvé"
    config = found.get("config") or {}
    gateway = context.infra.domains[domain].gateway
    assert "ipv4.address" in config, f"ipv4.address absent de la config réseau : {config}"
    assert gateway in config["ipv4.address"], (
        f"Gateway {gateway} absent de ipv4.address={config['ipv4.address']}"
    )
