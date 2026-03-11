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

portal_app = typer.Typer(help="Transfert de fichiers hôte ↔ conteneur.")
setup_app = typer.Typer(help="Configuration et import.")
golden_app = typer.Typer(help="Golden images — images réutilisables.")
tor_app = typer.Typer(help="Passerelle Tor.")
telemetry_app = typer.Typer(help="Métriques d'usage.")

app.add_typer(apply_app, name="apply")
app.add_typer(dev_app, name="dev")
app.add_typer(instance_app, name="instance")
app.add_typer(domain_app, name="domain")
app.add_typer(snapshot_app, name="snapshot")
app.add_typer(network_app, name="network")
app.add_typer(ai_app, name="ai")
app.add_typer(stt_app, name="stt")
app.add_typer(llm_app, name="llm")
app.add_typer(portal_app, name="portal")
app.add_typer(setup_app, name="setup")
app.add_typer(golden_app, name="golden")
app.add_typer(tor_app, name="tor")
app.add_typer(telemetry_app, name="telemetry")


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
    from anklume.cli._dev_setup import run_dev_setup_cmd

    run_dev_setup_cmd()


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


@dev_app.command("env")
def dev_env(
    name: Annotated[
        str,
        typer.Argument(help="Nom de l'environnement (ex: myproject)"),
    ] = "dev",
    machine_type: Annotated[
        str,
        typer.Option("--type", "-t", help="Type d'instance : lxc (léger) ou vm (isolé)"),
    ] = "lxc",
    gpu: Annotated[
        bool,
        typer.Option("--gpu", help="Activer le GPU passthrough"),
    ] = False,
    llm: Annotated[
        bool,
        typer.Option("--llm", help="Accès aux services LLM (Ollama, STT)"),
    ] = False,
    claude_code: Annotated[
        bool,
        typer.Option("--claude-code", help="Installer Claude Code CLI"),
    ] = False,
    mount: Annotated[
        list[str] | None,
        typer.Option("--mount", "-m", help="Montage persistant (nom=/chemin). Répétable."),
    ] = None,
    memory: Annotated[
        str,
        typer.Option("--memory", help="Limite mémoire (ex: 4GiB, 8GiB)"),
    ] = "",
    cpu: Annotated[
        str,
        typer.Option("--cpu", help="Limite CPU (ex: 4, 8)"),
    ] = "",
    output: Annotated[
        str,
        typer.Option("--output", "-o", help="Répertoire projet anklume"),
    ] = ".",
    preset: Annotated[
        str,
        typer.Option("--preset", "-p", help="Preset prédéfini (anklume)"),
    ] = "",
    llm_backend: Annotated[
        str,
        typer.Option(
            "--llm-backend",
            help="Backend LLM : local (Ollama), openai, anthropic",
        ),
    ] = "local",
    llm_model: Annotated[
        str,
        typer.Option("--llm-model", help="Modèle LLM (ex: qwen2:7b, gpt-4o)"),
    ] = "",
    llm_api_url: Annotated[
        str,
        typer.Option("--llm-api-url", help="URL API LLM (pour openai/anthropic)"),
    ] = "",
    llm_api_key: Annotated[
        str,
        typer.Option("--llm-api-key", help="Clé API LLM (pour openai/anthropic)"),
    ] = "",
    sanitize: Annotated[
        str,
        typer.Option(
            "--sanitize",
            help="Sanitisation LLM : false, true (cloud), always (tout)",
        ),
    ] = "false",
) -> None:
    """Générer un environnement de développement (domaine + rôle dev_env)."""
    from anklume.cli._dev_env import run_dev_env
    from anklume.engine.dev_env import DevEnvConfig

    if preset == "anklume":
        from anklume.engine.dev_env import anklume_self_dev_config

        config = anklume_self_dev_config()
    else:
        # Construire les montages depuis --mount key=path
        mount_paths: dict[str, str] = {}
        for m in mount or []:
            if "=" not in m:
                typer.echo(
                    f"Format invalide pour --mount : {m} (attendu: nom=/chemin)",
                    err=True,
                )
                raise typer.Exit(1)
            k, v = m.split("=", 1)
            mount_paths[k] = v

        config = DevEnvConfig(
            name=name,
            machine_type=machine_type,
            gpu=gpu,
            llm=llm,
            claude_code=claude_code,
            mount_paths=mount_paths,
            memory=memory,
            cpu=cpu,
            llm_backend=llm_backend,
            llm_model=llm_model,
            llm_api_url=llm_api_url,
            llm_api_key=llm_api_key,
            sanitize=sanitize,
        )

    run_dev_env(config, output=output)


@dev_app.command("test-real")
def dev_test_real(
    keep: Annotated[
        bool,
        typer.Option("--keep", help="Conserver la VM après les tests"),
    ] = False,
    filter_expr: Annotated[
        str,
        typer.Option("--filter", "-k", help="Filtre pytest (-k expression)"),
    ] = "",
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Afficher la sortie complète"),
    ] = False,
    memory: Annotated[
        str,
        typer.Option("--memory", help="Mémoire de la VM (ex: 8GiB)"),
    ] = "8GiB",
    cpu: Annotated[
        str,
        typer.Option("--cpu", help="CPU de la VM (ex: 8)"),
    ] = "8",
    timeout: Annotated[
        int,
        typer.Option("--timeout", help="Timeout des tests en secondes"),
    ] = 600,
) -> None:
    """Lancer les tests réels E2E dans une VM KVM isolée."""
    from anklume.cli._dev_test_real import run_dev_test_real
    from anklume.engine.e2e_real import E2eRealConfig

    config = E2eRealConfig(
        memory=memory,
        cpu=cpu,
        keep_vm=keep,
        test_filter=filter_expr,
        verbose=verbose,
        timeout=timeout,
    )
    run_dev_test_real(config)


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


@instance_app.command("gui")
def instance_gui(
    instance: Annotated[str, typer.Argument(help="Nom de l'instance")],
    app: Annotated[
        str,
        typer.Argument(help="Application à lancer (ex: firefox, code)"),
    ] = "bash",
) -> None:
    """Lancer une application graphique dans une instance."""
    from anklume.cli._gui import run_instance_gui

    run_instance_gui(instance, app)


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


# --- anklume portal <push|pull|list> ---


@portal_app.command("push")
def portal_push(
    instance: Annotated[str, typer.Argument(help="Nom de l'instance")],
    local_path: Annotated[str, typer.Argument(help="Chemin du fichier local")],
    remote_path: Annotated[str, typer.Argument(help="Chemin distant")] = "/tmp/",  # noqa: S108
) -> None:
    """Envoyer un fichier vers une instance."""
    from anklume.cli._portal import run_portal_push

    run_portal_push(instance, local_path, remote_path)


@portal_app.command("pull")
def portal_pull(
    instance: Annotated[str, typer.Argument(help="Nom de l'instance")],
    remote_path: Annotated[str, typer.Argument(help="Chemin du fichier distant")],
    local_path: Annotated[str, typer.Argument(help="Chemin local de destination")] = ".",
) -> None:
    """Récupérer un fichier depuis une instance."""
    from anklume.cli._portal import run_portal_pull

    run_portal_pull(instance, remote_path, local_path)


@portal_app.command("list")
def portal_list(
    instance: Annotated[str, typer.Argument(help="Nom de l'instance")],
    path: Annotated[str, typer.Argument(help="Chemin du répertoire distant")] = "/root/",
) -> None:
    """Lister les fichiers d'un répertoire distant."""
    from anklume.cli._portal import run_portal_list

    run_portal_list(instance, path)


# --- anklume instance clipboard ---


@instance_app.command("clipboard")
def instance_clipboard(
    instance: Annotated[str, typer.Argument(help="Nom de l'instance")],
    pull: Annotated[
        bool,
        typer.Option("--pull", help="Conteneur → hôte (défaut: hôte → conteneur)"),
    ] = False,
) -> None:
    """Partager le presse-papiers avec une instance."""
    from anklume.cli._instance import run_instance_clipboard

    run_instance_clipboard(instance, pull=pull)


# --- anklume disp ---


@app.command("disp")
def disp(
    image: Annotated[
        str | None,
        typer.Argument(help="Image Incus (ex: images:debian/13)"),
    ] = None,
    cmd: Annotated[
        list[str] | None,
        typer.Argument(help="Commande à exécuter"),
    ] = None,
    list_all: Annotated[
        bool,
        typer.Option("--list", "-l", help="Lister les conteneurs jetables"),
    ] = False,
    cleanup: Annotated[
        bool,
        typer.Option("--cleanup", help="Détruire tous les conteneurs jetables"),
    ] = False,
) -> None:
    """Lancer un conteneur jetable."""
    from anklume.cli._disp import run_disp

    run_disp(image=image, cmd=cmd, list_all=list_all, cleanup=cleanup)


# --- anklume setup <import> ---


@setup_app.command("import")
def setup_import(
    directory: Annotated[
        str,
        typer.Option("--dir", "-d", help="Répertoire de sortie"),
    ] = ".",
) -> None:
    """Importer une infrastructure Incus existante."""
    from anklume.cli._setup import run_setup_import

    run_setup_import(output_dir=directory)


@setup_app.command("aliases")
def setup_aliases(
    remove: Annotated[
        bool,
        typer.Option("--remove", "-r", help="Supprimer les aliases"),
    ] = False,
    shell: Annotated[
        str | None,
        typer.Option("--shell", "-s", help="Shell cible (bash/zsh/fish). Auto-détecté."),
    ] = None,
) -> None:
    """Installer les aliases shell (anklume, ank)."""
    from anklume.cli._setup import run_setup_aliases

    run_setup_aliases(remove=remove, shell=shell)


@setup_app.command("gui")
def setup_gui(
    fix: Annotated[
        bool,
        typer.Option("--fix", help="Réparer les profils GUI et conteneurs."),
    ] = False,
    recover: Annotated[
        bool,
        typer.Option("--recover", help="Récupération d'urgence (stop, retrait profil, restart)."),
    ] = False,
) -> None:
    """Diagnostic (et réparation) de l'environnement GUI."""
    from anklume.cli._gui import run_setup_gui, run_setup_gui_fix, run_setup_gui_recover

    if recover:
        run_setup_gui_recover()
    elif fix:
        run_setup_gui_fix()
    else:
        run_setup_gui()


# --- anklume golden <create|list|delete> ---


@golden_app.command("create")
def golden_create(
    instance: Annotated[str, typer.Argument(help="Nom de l'instance à publier")],
    alias: Annotated[
        str | None,
        typer.Option("--alias", "-a", help="Alias personnalisé (défaut: golden/<instance>)"),
    ] = None,
) -> None:
    """Publier une instance comme golden image."""
    from anklume.cli._golden import run_golden_create

    run_golden_create(instance, alias=alias)


@golden_app.command("list")
def golden_list_cmd() -> None:
    """Lister les golden images."""
    from anklume.cli._golden import run_golden_list

    run_golden_list()


@golden_app.command("delete")
def golden_delete(
    alias: Annotated[str, typer.Argument(help="Alias de l'image à supprimer")],
) -> None:
    """Supprimer une golden image."""
    from anklume.cli._golden import run_golden_delete

    run_golden_delete(alias)


# --- anklume tor <status> ---


@tor_app.command("status")
def tor_status() -> None:
    """Afficher l'état des passerelles Tor."""
    from anklume.cli._tor import run_tor_status

    run_tor_status()


# --- anklume console ---


console_app = typer.Typer(help="Console tmux colorée par domaine.")
app.add_typer(console_app, name="console")


@console_app.callback(invoke_without_command=True)
def console(
    ctx: typer.Context,
    domain: Annotated[
        str | None,
        typer.Option("--domain", help="Domaine (tous si omis)"),
    ] = None,
    detach: Annotated[
        bool,
        typer.Option("--detach", "-d", help="Lancer en arrière-plan"),
    ] = False,
    kill: Annotated[
        bool,
        typer.Option("--kill", help="Tuer et recréer la session"),
    ] = False,
    dedicated: Annotated[
        bool,
        typer.Option("--dedicated", help="1 fenêtre par instance (2 panes)"),
    ] = False,
    status_color: Annotated[
        str,
        typer.Option("--status-color", help="Couleur barre statut"),
    ] = "terminal",
) -> None:
    """Ouvrir la console tmux."""
    if ctx.invoked_subcommand is not None:
        return
    from anklume.cli._console import run_console

    run_console(
        domain=domain,
        detach=detach,
        kill=kill,
        dedicated=dedicated,
        status_color=status_color,
    )


@console_app.command("kill")
def console_kill(
    domain: Annotated[
        str | None,
        typer.Option("--domain", help="Domaine (tous si omis)"),
    ] = None,
) -> None:
    """Tuer la session tmux anklume."""
    from anklume.cli._console import run_console_kill

    run_console_kill(domain=domain)


# --- anklume doctor ---


@app.command("doctor")
def doctor(
    fix: Annotated[
        bool,
        typer.Option("--fix", help="Appliquer les corrections automatiques"),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Sortie JSON"),
    ] = False,
) -> None:
    """Diagnostic automatique de l'infrastructure."""
    from anklume.cli._doctor import run_doctor_cmd

    run_doctor_cmd(fix=fix, json_output=json_output)


# --- anklume telemetry <on|off|status> ---


@telemetry_app.command("on")
def telemetry_on() -> None:
    """Activer la collecte de métriques."""
    from anklume.cli._telemetry import run_telemetry_on

    run_telemetry_on()


@telemetry_app.command("off")
def telemetry_off() -> None:
    """Désactiver la collecte de métriques."""
    from anklume.cli._telemetry import run_telemetry_off

    run_telemetry_off()


@telemetry_app.command("status")
def telemetry_status() -> None:
    """Afficher l'état et le résumé des métriques."""
    from anklume.cli._telemetry import run_telemetry_status

    run_telemetry_status()
