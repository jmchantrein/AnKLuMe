"""Steps behave pour les scénarios init."""

from __future__ import annotations

from behave import given, then

from anklume.engine.parser import parse_project


@given('un répertoire vide "{name}"')
def step_repertoire_vide(context, name):
    """Crée un répertoire vide dans le tmpdir."""
    d = context.tmpdir / name
    d.mkdir(parents=True, exist_ok=True)
    context.target_dir = d


@given('un répertoire non vide "{name}"')
def step_repertoire_non_vide(context, name):
    """Crée un répertoire avec un fichier dedans."""
    d = context.tmpdir / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "existing.txt").write_text("contenu")
    context.target_dir = d


@then('le fichier "{path}" existe')
def step_fichier_existe(context, path):
    full = context.tmpdir / path
    assert full.exists(), f"Fichier {full} n'existe pas"


@then('le répertoire "{path}" existe')
def step_repertoire_existe(context, path):
    full = context.tmpdir / path
    assert full.is_dir(), f"Répertoire {full} n'existe pas"


@then("la commande échoue")
def step_commande_echoue(context):
    assert context.exit_code != 0, f"La commande a réussi (code {context.exit_code})"


@then('le projet "{path}" peut être parsé par le moteur')
def step_projet_parsable(context, path):
    project_dir = context.tmpdir / path
    infra = parse_project(project_dir)
    assert infra is not None
    assert len(infra.domains) > 0
