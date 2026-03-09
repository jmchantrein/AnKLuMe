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
domain_app = typer.Typer(help="Gestion des domaines.")
snapshot_app = typer.Typer(help="Gestion des snapshots.")
network_app = typer.Typer(help="Réseau et sécurité nftables.")
ai_app = typer.Typer(help="Gestion des services IA.")
stt_app = typer.Typer(help="Push-to-talk STT.")
llm_app = typer.Typer(help="Supervision LLM.")

app.add_typer(apply_app, name="apply")
app.add_typer(dev_app, name="dev")
app.add_typer(instance_app, name="instance")
app.add_typer(domain_app, name="domain")
app.add_typer(snapshot_app, name="snapshot")
app.add_typer(network_app, name="network")
app.add_typer(ai_app, name="ai")
app.add_typer(stt_app, name="stt")
app.add_typer(llm_app, name="llm")


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


@dev_app.command("molecule")
def dev_molecule(
    role: Annotated[
        str,
        typer.Argument(help="Nom du rôle (tous si omis)"),
    ] = "",
    scenario: Annotated[
        str,
        typer.Option("--scenario", "-s", help="Nom du scénario Molecule"),
    ] = "default",
    command: Annotated[
        str,
        typer.Option("--command", "-c", help="Commande Molecule (test, converge, verify, destroy)"),
    ] = "test",
) -> None:
    """Lancer les tests Molecule sur les rôles Ansible."""
    from anklume.cli._molecule import run_molecule

    run_molecule(role=role, scenario=scenario, command=command)


# --- anklume instance <list|exec|info> ---


@instance_app.command("list")
def instance_list() -> None:
    """Lister toutes les instances avec état réel."""
    from anklume.cli._instance import run_instance_list

    run_instance_list()


@instance_app.command("exec")
def instance_exec(
    instance: Annotated[str, typer.Argument(help="Nom de l'instance")],
    cmd: Annotated[list[str], typer.Argument(help="Commande à exécuter")],
) -> None:
    """Exécuter une commande dans une instance."""
    from anklume.cli._instance import run_instance_exec

    run_instance_exec(instance, cmd)


@instance_app.command("info")
def instance_info(
    instance: Annotated[str, typer.Argument(help="Nom de l'instance")],
) -> None:
    """Détails d'une instance (config, snapshots, IPs)."""
    from anklume.cli._instance import run_instance_info

    run_instance_info(instance)


# --- anklume domain <list|check|exec|status> ---


@domain_app.command("list")
def domain_list() -> None:
    """Lister tous les domaines."""
    from anklume.cli._domain import run_domain_list

    run_domain_list()


@domain_app.command("check")
def domain_check(
    name: Annotated[str, typer.Argument(help="Nom du domaine à valider")],
) -> None:
    """Valider un domaine isolément."""
    from anklume.cli._domain import run_domain_check

    run_domain_check(name)


@domain_app.command("exec")
def domain_exec(
    name: Annotated[str, typer.Argument(help="Nom du domaine")],
    cmd: Annotated[list[str], typer.Argument(help="Commande à exécuter")],
) -> None:
    """Exécuter une commande dans toutes les instances d'un domaine."""
    from anklume.cli._domain import run_domain_exec

    run_domain_exec(name, cmd)


@domain_app.command("status")
def domain_status(
    name: Annotated[str, typer.Argument(help="Nom du domaine")],
) -> None:
    """État détaillé d'un domaine."""
    from anklume.cli._domain import run_domain_status

    run_domain_status(name)


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


@snapshot_app.command("delete")
def snapshot_delete(
    instance: Annotated[str, typer.Argument(help="Nom de l'instance")],
    snapshot: Annotated[str, typer.Argument(help="Nom du snapshot")],
) -> None:
    """Supprimer un snapshot."""
    from anklume.cli._snapshot import run_snapshot_delete

    run_snapshot_delete(instance=instance, snapshot=snapshot)


@snapshot_app.command("rollback")
def snapshot_rollback(
    instance: Annotated[str, typer.Argument(help="Nom de l'instance")],
    snapshot: Annotated[str, typer.Argument(help="Nom du snapshot")],
) -> None:
    """Rollback destructif (restaure + supprime les snapshots postérieurs)."""
    from anklume.cli._snapshot import run_snapshot_rollback

    run_snapshot_rollback(instance=instance, snapshot=snapshot)


# --- anklume network <rules|deploy|status> ---


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


@network_app.command("status")
def network_status() -> None:
    """Afficher l'état réseau (bridges, IPs, nftables)."""
    from anklume.cli._network import run_network_status

    run_network_status()


# --- anklume llm <status|bench> ---


@llm_app.command("status")
def llm_status() -> None:
    """Vue dédiée backends LLM, modèles, VRAM."""
    from anklume.cli._llm import run_llm_status

    run_llm_status()


@llm_app.command("bench")
def llm_bench(
    model: Annotated[
        str,
        typer.Option("--model", "-m", help="Modèle à benchmarker"),
    ] = "",
    prompt: Annotated[
        str,
        typer.Option("--prompt", "-p", help="Prompt personnalisé"),
    ] = "",
) -> None:
    """Benchmark inférence (tokens/s, latence)."""
    from anklume.cli._llm import run_llm_bench

    run_llm_bench(model=model, prompt=prompt)


@llm_app.command("sanitize")
def llm_sanitize(
    text: Annotated[
        str | None,
        typer.Argument(help="Texte à sanitiser (- pour stdin)"),
    ] = None,
    mode: Annotated[
        str,
        typer.Option("--mode", help="Mode : mask, pseudonymize"),
    ] = "mask",
    ner: Annotated[
        bool,
        typer.Option("--ner", help="Activer la détection NER"),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Sortie JSON"),
    ] = False,
) -> None:
    """Dry-run de sanitisation."""
    from anklume.cli._llm import run_llm_sanitize

    if text is None:
        typer.echo("Erreur : texte requis (argument ou - pour stdin)", err=True)
        raise typer.Exit(1)

    run_llm_sanitize(text=text, mode=mode, ner=ner, json_output=json_output)


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


@ai_app.command("test")
def ai_test(
    backend: Annotated[
        str,
        typer.Option("--backend", "-b", help="Backend LLM (ollama ou claude)"),
    ] = "ollama",
    mode: Annotated[
        str,
        typer.Option("--mode", "-m", help="Mode (dry-run, auto-apply, auto-pr)"),
    ] = "dry-run",
    max_retries: Annotated[
        int,
        typer.Option("--max-retries", help="Nombre max de tentatives"),
    ] = 3,
) -> None:
    """Boucle test + analyse LLM + correction automatique."""
    from anklume.cli._ai import run_ai_test

    run_ai_test(backend=backend, mode=mode, max_retries=max_retries)


# --- anklume stt <setup|start|stop|status> ---


@stt_app.command("setup")
def stt_setup(
    device: Annotated[
        str,
        typer.Option("--device", "-d", help="Device serveur (gpu, cpu, auto)"),
    ] = "auto",
    hotkey: Annotated[
        str,
        typer.Option("--hotkey", "-k", help="Touche push-to-talk (ex: F23, SCROLLLOCK)"),
    ] = "",
    model: Annotated[
        str,
        typer.Option("--model", "-m", help="Modèle Whisper (ex: Systran/faster-whisper-medium)"),
    ] = "",
) -> None:
    """Configurer le STT (Voxtype + Speaches)."""
    from anklume.cli._stt import run_stt_setup

    run_stt_setup(device=device, hotkey=hotkey, model=model)


@stt_app.command("start")
def stt_start() -> None:
    """Démarrer le push-to-talk STT."""
    from anklume.cli._stt import run_stt_start

    run_stt_start()


@stt_app.command("stop")
def stt_stop() -> None:
    """Arrêter le push-to-talk STT."""
    from anklume.cli._stt import run_stt_stop

    run_stt_stop()


@stt_app.command("status")
def stt_status() -> None:
    """Afficher l'état du service STT."""
    from anklume.cli._stt import run_stt_status

    run_stt_status()
