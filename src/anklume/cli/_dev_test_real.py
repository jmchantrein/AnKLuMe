"""anklume dev test-real — exécuter les tests réels dans une VM KVM."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import typer

from anklume.engine.e2e_real import (
    SANDBOX_INSTANCE,
    SANDBOX_PROJECT,
    E2eRealConfig,
    E2eRealResult,
    generate_e2e_project,
    install_deps_in_vm,
    push_source_to_vm,
    run_tests_in_vm,
    wait_for_vm_ready,
)
from anklume.engine.incus_driver import IncusDriver


def run_dev_test_real(config: E2eRealConfig) -> None:
    """Lance les tests réels E2E dans une VM KVM isolée."""
    project_dir: Path | None = None
    original_dir = Path.cwd()

    try:
        # 1. Générer le projet sandbox
        typer.echo(f"Création du projet sandbox ({config.memory} RAM, {config.cpu} CPU)...")
        project_dir = generate_e2e_project(config)

        # 2. Appliquer (crée la VM, sans provisioning — la VM doit booter d'abord)
        typer.echo("Déploiement de la VM sandbox via anklume apply...")
        os.chdir(project_dir)

        from anklume.cli._apply import run_apply

        try:
            run_apply(dry_run=False, no_provision=True)
        except SystemExit as e:
            if e.code != 0:
                typer.echo("Échec du déploiement de la VM sandbox.", err=True)
                raise typer.Exit(1) from None

        os.chdir(original_dir)

        # 3. Attendre que la VM soit prête (cloud-init terminé)
        driver = IncusDriver()
        typer.echo("Attente du boot de la VM...")
        if not wait_for_vm_ready(driver, SANDBOX_PROJECT, SANDBOX_INSTANCE):
            typer.echo("La VM ne répond pas après le timeout.", err=True)
            raise typer.Exit(1)
        typer.echo("VM prête.")

        # 4. Provisioning Ansible (maintenant que la VM répond)
        typer.echo("Provisioning Ansible (Incus, uv, nftables)...")
        os.chdir(project_dir)
        from anklume.cli._common import load_infra
        from anklume.provisioner import provision

        infra = load_infra(project_dir)
        prov_result = provision(infra, project_dir)
        os.chdir(original_dir)
        if not prov_result.success and not prov_result.skipped:
            typer.echo(f"Provisioning échoué : {prov_result.error}", err=True)
            raise typer.Exit(1)
        typer.echo("Provisioning terminé.")

        # 5. Pousser le source anklume
        typer.echo("Transfert du source anklume dans la VM...")
        push_source_to_vm(driver, SANDBOX_PROJECT, SANDBOX_INSTANCE)

        # 6. Installer les dépendances
        typer.echo("Installation des dépendances (uv sync)...")
        install_deps_in_vm(driver, SANDBOX_PROJECT, SANDBOX_INSTANCE)

        # 7. Exécuter les tests
        filter_msg = f" (filtre: {config.test_filter})" if config.test_filter else ""
        typer.echo(f"Exécution des tests réels dans la VM{filter_msg}...")
        result = run_tests_in_vm(driver, SANDBOX_PROJECT, SANDBOX_INSTANCE, config)

        # 8. Afficher les résultats
        _print_result(result, verbose=config.verbose)

        # 9. Cleanup ou conserver
        if config.keep_vm:
            typer.echo(
                f"\nVM conservée : incus exec {SANDBOX_INSTANCE} "
                f"--project {SANDBOX_PROJECT} -- bash"
            )
        else:
            _cleanup(project_dir)

        raise typer.Exit(result.exit_code)

    except typer.Exit as exit_err:
        if exit_err.exit_code != 0 and project_dir and not config.keep_vm:
            _cleanup(project_dir)
        raise
    except Exception as e:
        typer.echo(f"Erreur inattendue : {e}", err=True)
        if project_dir and not config.keep_vm:
            _cleanup(project_dir)
        raise typer.Exit(1) from None
    finally:
        os.chdir(original_dir)


def _print_result(result: E2eRealResult, *, verbose: bool = False) -> None:
    """Affiche le résumé des résultats."""
    typer.echo(f"\n{'=' * 60}")
    typer.echo(f"Tests réels E2E — {result.duration_s:.1f}s")
    typer.echo(f"{'=' * 60}")

    if result.errors:
        for err in result.errors:
            typer.echo(f"  ERREUR : {err}", err=True)

    total = result.tests_passed + result.tests_failed + result.tests_errors
    typer.echo(f"  Total    : {total}")
    typer.echo(f"  Passés   : {result.tests_passed}")
    typer.echo(f"  Échoués  : {result.tests_failed}")
    typer.echo(f"  Erreurs  : {result.tests_errors}")

    if result.exit_code == 0:
        typer.echo("\nTous les tests réels sont passés.")
    else:
        typer.echo(f"\nCode de sortie : {result.exit_code}", err=True)

    if verbose and result.stdout:
        typer.echo(f"\n{'─' * 60}")
        typer.echo(result.stdout)

    if verbose and result.stderr:
        typer.echo(result.stderr, err=True)


def _cleanup(project_dir: Path) -> None:
    """Supprime la VM sandbox et le répertoire temporaire."""
    typer.echo("Nettoyage de la VM sandbox...")
    from anklume.engine.e2e_real import cleanup_sandbox

    cleanup_sandbox(SANDBOX_PROJECT)
    shutil.rmtree(project_dir, ignore_errors=True)
