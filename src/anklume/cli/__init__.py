"""anklume CLI — point d'entrée."""

from typing import Annotated

import typer

from anklume import __version__

app = typer.Typer(
    name="anklume",
    help="Framework déclaratif de compartimentalisation d'infrastructure.",
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"anklume {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option("--version", "-V", help="Afficher la version", callback=_version_callback, is_eager=True),
    ] = None,
) -> None:
    """anklume — isolation compartimentée avec Incus."""


@app.command()
def init(
    directory: Annotated[str, typer.Argument(help="Répertoire du projet à créer")] = ".",
    lang: Annotated[str, typer.Option("--lang", "-l", help="Langue (en/fr)")] = "fr",
) -> None:
    """Créer un nouveau projet anklume."""
    from anklume.cli._init import run_init

    run_init(directory, lang=lang)


@app.command()
def apply(
    domain: Annotated[str | None, typer.Argument(help="Domaine unique à déployer")] = None,
) -> None:
    """Déployer l'infrastructure vers Incus."""
    typer.echo("apply : pas encore implémenté")


@app.command()
def status() -> None:
    """Afficher l'état de l'infrastructure."""
    typer.echo("status : pas encore implémenté")


@app.command()
def destroy(
    force: Annotated[bool, typer.Option("--force", help="Détruire aussi les instances protégées")] = False,
) -> None:
    """Détruire l'infrastructure."""
    typer.echo("destroy : pas encore implémenté")
