"""anklume CLI — point d'entrée."""

from typing import Annotated

import typer

from anklume import __version__

app = typer.Typer(
    name="anklume",
    help="Framework déclaratif de compartimentalisation d'infrastructure.",
    no_args_is_help=True,
)

# Sous-commandes groupées
apply_app = typer.Typer(help="Déployer l'infrastructure.")
dev_app = typer.Typer(help="Outils de développement.")
instance_app = typer.Typer(help="Gestion des instances.")
snapshot_app = typer.Typer(help="Gestion des snapshots.")
network_app = typer.Typer(help="Réseau et sécurité nftables.")
ai_app = typer.Typer(help="Gestion des services IA.")
stt_app = typer.Typer(help="Push-to-talk STT.")

app.add_typer(apply_app, name="apply")
app.add_typer(dev_app, name="dev")
app.add_typer(instance_app, name="instance")
app.add_typer(snapshot_app, name="snapshot")
app.add_typer(network_app, name="network")
app.add_typer(ai_app, name="ai")
app.add_typer(stt_app, name="stt")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"anklume {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            "-V",
            help="Afficher la version",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = None,
) -> None:
    """anklume — isolation compartimentée avec Incus."""


# --- anklume init ---


@app.command()
def init(
    directory: Annotated[str, typer.Argument(help="Répertoire du projet à créer")] = ".",
    lang: Annotated[str, typer.Option("--lang", "-l", help="Langue (en/fr)")] = "fr",
) -> None:
    """Créer un nouveau projet anklume."""
    from anklume.cli._init import run_init

    run_init(directory, lang=lang)


@app.command()
def status() -> None:
    """Afficher l'état de l'infrastructure."""
    from anklume.cli._status import run_status

    run_status()


@app.command()
def destroy(
    force: Annotated[
        bool,
        typer.Option("--force", help="Détruire aussi les instances protégées"),
    ] = False,
) -> None:
    """Détruire l'infrastructure."""
    from anklume.cli._destroy import run_destroy

    run_destroy(force=force)


# --- anklume apply <all|domaine> ---


@apply_app.command("all")
def apply_all(
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Afficher le plan sans appliquer"),
    ] = False,
    no_provision: Annotated[
        bool,
        typer.Option("--no-provision", help="Ignorer le provisioning Ansible"),
    ] = False,
) -> None:
    """Déployer tous les domaines."""
    from anklume.cli._apply import run_apply

    run_apply(dry_run=dry_run, no_provision=no_provision)


@apply_app.command("domain")
def apply_domain(
    name: Annotated[str, typer.Argument(help="Nom du domaine à déployer")],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Afficher le plan sans appliquer"),
    ] = False,
    no_provision: Annotated[
        bool,
        typer.Option("--no-provision", help="Ignorer le provisioning Ansible"),
    ] = False,
) -> None:
    """Déployer un domaine spécifique."""
    from anklume.cli._apply import run_apply

    run_apply(domain_name=name, dry_run=dry_run, no_provision=no_provision)


# --- anklume dev <setup|lint|test> ---


@dev_app.command("setup")
def dev_setup() -> None:
    """Préparer l'environnement de développement anklume."""
    typer.echo("dev setup : pas encore implémenté")


@dev_app.command("lint")
def dev_lint() -> None:
    """Lancer tous les validateurs (ruff)."""
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "src/", "tests/"],
    )
    if result.returncode == 0:
        result = subprocess.run(
            [sys.executable, "-m", "ruff", "format", "--check", "src/", "tests/"],
        )
    raise typer.Exit(result.returncode)


@dev_app.command("test")
def dev_test() -> None:
    """Lancer pytest."""
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-v"],
    )
    raise typer.Exit(result.returncode)


# --- anklume instance <list|shell> ---


@instance_app.command("list")
def instance_list() -> None:
    """Lister toutes les instances."""
    typer.echo("instance list : pas encore implémenté")


@instance_app.command("shell")
def instance_shell(
    name: Annotated[str, typer.Argument(help="Nom de l'instance")],
) -> None:
    """Ouvrir un shell dans une instance."""
    typer.echo(f"instance shell {name} : pas encore implémenté")


# --- anklume snapshot <create|list|restore> ---


@snapshot_app.command("create")
def snapshot_create(
    instance: Annotated[
        str | None,
        typer.Argument(help="Nom de l'instance (toutes si omis)"),
    ] = None,
    name: Annotated[
        str | None,
        typer.Option("--name", "-n", help="Nom personnalisé du snapshot"),
    ] = None,
) -> None:
    """Créer un snapshot."""
    from anklume.cli._snapshot import run_snapshot_create

    run_snapshot_create(instance=instance, name=name)


@snapshot_app.command("list")
def snapshot_list(
    instance: Annotated[
        str | None,
        typer.Argument(help="Nom de l'instance (toutes si omis)"),
    ] = None,
) -> None:
    """Lister les snapshots."""
    from anklume.cli._snapshot import run_snapshot_list

    run_snapshot_list(instance=instance)


@snapshot_app.command("restore")
def snapshot_restore(
    instance: Annotated[str, typer.Argument(help="Nom de l'instance")],
    snapshot: Annotated[str, typer.Argument(help="Nom du snapshot")],
) -> None:
    """Restaurer un snapshot sur une instance."""
    from anklume.cli._snapshot import run_snapshot_restore

    run_snapshot_restore(instance=instance, snapshot=snapshot)


# --- anklume network <rules|deploy> ---


@network_app.command("rules")
def network_rules() -> None:
    """Générer et afficher les règles nftables."""
    from anklume.cli._network import run_network_rules

    run_network_rules()


@network_app.command("deploy")
def network_deploy() -> None:
    """Appliquer les règles nftables sur l'hôte."""
    from anklume.cli._network import run_network_deploy

    run_network_deploy()


# --- anklume ai <status|flush|switch> ---


@ai_app.command("status")
def ai_status() -> None:
    """Afficher l'état des services IA."""
    from anklume.cli._ai import run_ai_status

    run_ai_status()


@ai_app.command("flush")
def ai_flush() -> None:
    """Libérer la VRAM GPU (décharger modèles, arrêter llama-server)."""
    from anklume.cli._ai import run_ai_flush

    run_ai_flush()


@ai_app.command("switch")
def ai_switch(
    domain: Annotated[str, typer.Argument(help="Domaine cible pour l'accès GPU")],
) -> None:
    """Basculer l'accès exclusif GPU vers un domaine."""
    from anklume.cli._ai import run_ai_switch

    run_ai_switch(domain)


# --- anklume stt <setup|status> ---


@stt_app.command("setup")
def stt_setup() -> None:
    """Installer les dépendances hôte et configurer le raccourci KDE."""
    from anklume.cli._stt import run_stt_setup

    run_stt_setup()


@stt_app.command("status")
def stt_status() -> None:
    """Afficher l'état du service STT."""
    from anklume.cli._stt import run_stt_status

    run_stt_status()
