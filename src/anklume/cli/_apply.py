"""Implémentation de `anklume apply all` et `anklume apply domain <nom>`."""

from __future__ import annotations

from pathlib import Path

import typer

from anklume.cli._common import load_infra
from anklume.engine.incus_driver import IncusDriver
from anklume.engine.nesting import detect_nesting_context
from anklume.engine.reconciler import ReconcileResult, reconcile
from anklume.engine.snapshot import create_auto_snapshots


def run_apply(
    *,
    domain_name: str | None = None,
    dry_run: bool = False,
    no_provision: bool = False,
) -> None:
    """Pipeline apply : parse → validate → reconcile → snapshot → provision."""
    project_dir = Path.cwd()
    infra = load_infra(project_dir)

    # Filtrer un domaine spécifique si demandé
    if domain_name:
        if domain_name not in infra.domains:
            typer.echo(f"Domaine inconnu : {domain_name}", err=True)
            raise typer.Exit(1)
        infra.domains = {domain_name: infra.domains[domain_name]}

    # GPU passthrough : détection et enrichissement des profils
    from anklume.engine.gpu import apply_gpu_profiles, validate_gpu_machines

    gpu_info = apply_gpu_profiles(infra)
    gpu_errors = validate_gpu_machines(infra, gpu_info)
    if gpu_errors:
        for err in gpu_errors:
            typer.echo(f"GPU : {err}", err=True)
        raise typer.Exit(1)

    # GUI : détection Wayland/PipeWire/iGPU et enrichissement des profils
    from anklume.engine.gui import apply_gui_profiles

    gui_info = apply_gui_profiles(infra)

    driver = IncusDriver()
    nesting_ctx = detect_nesting_context()

    # Pré-fetch des projets existants (un seul appel subprocess pour tout le pipeline)
    existing_projects = {p.name for p in driver.project_list()}

    # Snapshots pré-apply (instances existantes)
    if not dry_run:
        pre = create_auto_snapshots(
            driver,
            infra,
            "pre",
            existing_projects=existing_projects,
        )
        if pre:
            typer.echo(f"Snapshots pré-apply : {len(pre)} créé(s)")

    reconcile_result = reconcile(
        infra, driver, dry_run=dry_run, nesting_context=nesting_ctx, gui_info=gui_info,
    )

    # Snapshots post-apply — refetch des projets (reconcile a pu en créer)
    if not dry_run and reconcile_result.executed:
        post_projects = {p.name for p in driver.project_list()}
        post = create_auto_snapshots(
            driver,
            infra,
            "post",
            existing_projects=post_projects,
        )
        if post:
            typer.echo(f"Snapshots post-apply : {len(post)} créé(s)")

    # Afficher le résultat de la réconciliation
    _print_result(reconcile_result, dry_run=dry_run)

    if not reconcile_result.success:
        raise typer.Exit(1)

    # Provisioning Ansible
    if not dry_run and not no_provision:
        from anklume.provisioner import provision

        prov_result = provision(infra, project_dir)
        if prov_result.skipped:
            if prov_result.skip_reason and "ansible" in prov_result.skip_reason.lower():
                typer.echo(f"⚠ {prov_result.skip_reason}")
        elif prov_result.success:
            typer.echo("Provisioning Ansible terminé.")
        else:
            typer.echo(f"Provisioning échoué : {prov_result.error}", err=True)


def _print_result(result: ReconcileResult, *, dry_run: bool) -> None:
    """Affiche le résultat de la réconciliation."""
    prefix = "[dry-run] " if dry_run else ""

    if not result.actions:
        typer.echo(f"{prefix}Infrastructure à jour — rien à faire.")
        return

    for action in result.actions:
        symbol = "+" if action.verb == "create" else "▶" if action.verb == "start" else "•"
        typer.echo(f"{prefix}  {symbol} {action.detail}")

    if not dry_run:
        ok = len(result.executed)
        fail = len(result.errors)
        typer.echo(f"\n{ok} action(s) réussie(s), {fail} erreur(s).")

        for action, msg in result.errors:
            typer.echo(f"  ✗ {action.target} : {msg}", err=True)
