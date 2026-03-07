"""Steps communs partagés entre les features."""

from __future__ import annotations

import os

from behave import when

from anklume.cli._init import run_init
from anklume.engine.addressing import assign_addresses
from anklume.engine.parser import parse_project
from anklume.engine.reconciler import reconcile
from anklume.engine.validator import validate


@when('je lance "{command}"')
def step_lance_commande(context, command):
    """Dispatch vers le bon handler selon la commande."""
    parts = command.split()

    if parts[0] == "init":
        _handle_init(context, parts)
    elif parts[0] == "apply":
        _handle_apply(context, parts)


def _handle_init(context, parts):
    """Exécute anklume init."""
    target = parts[1] if len(parts) > 1 else "."
    lang = "fr"
    for i, p in enumerate(parts):
        if p == "--lang" and i + 1 < len(parts):
            lang = parts[i + 1]

    target_path = context.tmpdir / target
    old_cwd = os.getcwd()
    try:
        os.chdir(context.tmpdir)
        try:
            run_init(str(target_path), lang=lang)
            context.exit_code = 0
        except (SystemExit, Exception) as e:
            code = getattr(e, "code", 1)
            context.exit_code = code if code is not None else 0
    finally:
        os.chdir(old_cwd)


def _handle_apply(context, parts):
    """Exécute le pipeline apply."""
    infra = parse_project(context.tmpdir)

    # Filtrer par domaine si nécessaire
    if len(parts) >= 3 and parts[1] == "domain":
        domain_name = parts[2]
        infra.domains = {domain_name: infra.domains[domain_name]}

    dry_run = "--dry-run" in parts

    result = validate(infra)
    if not result.valid:
        context.exit_code = 1
        return

    assign_addresses(infra)
    context.infra = infra
    context.result = reconcile(infra, context.driver, dry_run=dry_run)
