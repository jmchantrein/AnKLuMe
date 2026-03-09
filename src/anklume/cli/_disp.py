"""Implémentation de `anklume disp`."""

from __future__ import annotations

import subprocess

import typer

from anklume.engine.disposable import (
    DISP_PROJECT,
    cleanup_disposables,
    destroy_disposable,
    launch_disposable,
    list_disposables,
)
from anklume.engine.incus_driver import IncusDriver, IncusError


def run_disp(
    image: str | None = None,
    cmd: list[str] | None = None,
    list_all: bool = False,
    cleanup: bool = False,
) -> None:
    """Lance un conteneur jetable."""
    driver = IncusDriver()

    if list_all:
        _run_list(driver)
        return

    if cleanup:
        _run_cleanup(driver)
        return

    if image is None:
        typer.echo("Erreur : image requise (ex: images:debian/13)", err=True)
        raise typer.Exit(1)

    _run_launch(driver, image, cmd)


def _run_list(driver: IncusDriver) -> None:
    """Liste les conteneurs jetables."""
    disposables = list_disposables(driver)

    if not disposables:
        typer.echo("Aucun conteneur jetable actif.")
        return

    typer.echo(f"{'NOM':<20s} {'ÉTAT'}")
    for disp in disposables:
        typer.echo(f"{disp.name:<20s} {disp.status}")

    typer.echo(f"\n{len(disposables)} conteneur(s) jetable(s)")


def _run_cleanup(driver: IncusDriver) -> None:
    """Détruit tous les conteneurs jetables."""
    count = cleanup_disposables(driver)
    typer.echo(f"{count} conteneur(s) jetable(s) supprimé(s).")


def _run_launch(
    driver: IncusDriver,
    image: str,
    cmd: list[str] | None,
) -> None:
    """Lance un conteneur jetable, exécute, détruit."""
    try:
        disp = launch_disposable(driver, image)
    except IncusError as e:
        typer.echo(f"Erreur création : {e}", err=True)
        raise typer.Exit(1) from None

    typer.echo(f"Conteneur jetable {disp.name} démarré ({image})")

    try:
        if cmd:
            # Exécution unique
            result = driver.instance_exec(disp.name, DISP_PROJECT, cmd)
            if result.stdout:
                typer.echo(result.stdout, nl=False)
            if result.stderr:
                typer.echo(result.stderr, nl=False, err=True)
        else:
            # Shell interactif (stdin/stdout hérités)
            subprocess.run(
                ["incus", "exec", disp.name, "--project", DISP_PROJECT, "--", "bash"],
            )
    except IncusError as e:
        typer.echo(f"Erreur exec : {e}", err=True)
    finally:
        try:
            destroy_disposable(driver, disp.name)
            typer.echo(f"Conteneur {disp.name} détruit.")
        except IncusError as e:
            typer.echo(f"Erreur destruction : {e}", err=True)
            raise typer.Exit(1) from None
