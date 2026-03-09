"""Implémentation de `anklume stt` — setup, start, stop, status.

Stack validée : Voxtype (client push-to-talk Rust) + dotool (injection
texte AZERTY/Wayland) + Speaches (serveur STT faster-whisper, distant).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen

import typer

from anklume.engine.ai import check_service_health

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

# Dépendances hôte requises pour le push-to-talk
STT_HOST_DEPS: list[str] = [
    "voxtype",
    "dotool",
    "pw-record",
    "notify-send",
]

# Configuration par défaut
_DEFAULT_MODEL = "Systran/faster-whisper-medium"
_DEFAULT_LANGUAGE = "fr"
_DEFAULT_HOTKEY = "F23"
_DEFAULT_XKB_LAYOUT = "fr"

# Chemins
_VOXTYPE_CONFIG_DIR = Path.home() / ".config" / "voxtype"
_VOXTYPE_CONFIG_PATH = _VOXTYPE_CONFIG_DIR / "config.toml"
_SYSTEMD_USER_DIR = Path.home() / ".config" / "systemd" / "user"
_SYSTEMD_SERVICE = "anklume-stt.service"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def get_stt_config() -> dict[str, str]:
    """Retourne la configuration STT depuis les variables d'environnement."""
    return {
        "api_url": os.environ.get("STT_API_URL", ""),
        "model": os.environ.get("STT_MODEL", _DEFAULT_MODEL),
        "language": os.environ.get("STT_LANGUAGE", _DEFAULT_LANGUAGE),
        "hotkey": os.environ.get("STT_HOTKEY", _DEFAULT_HOTKEY),
        "xkb_layout": os.environ.get("STT_XKB_LAYOUT", _DEFAULT_XKB_LAYOUT),
    }


def check_stt_dependencies() -> list[str]:
    """Vérifie les dépendances hôte et retourne la liste des manquantes."""
    return [dep for dep in STT_HOST_DEPS if shutil.which(dep) is None]


# ---------------------------------------------------------------------------
# Détection du serveur STT
# ---------------------------------------------------------------------------


def _find_stt_machine() -> tuple[str, object] | None:
    """Trouve la machine STT dans l'infrastructure déclarée.

    Returns:
        (domain_name, machine) ou None si introuvable.
    """
    try:
        from anklume.cli._common import load_infra
        from anklume.engine.ai import ROLE_STT_SERVER

        infra = load_infra()
        for domain in infra.enabled_domains:
            for machine in domain.machines.values():
                if ROLE_STT_SERVER in machine.roles:
                    return (domain.name, machine)
    except (ImportError, FileNotFoundError, OSError):
        pass
    return None


def _find_stt_endpoint() -> str | None:
    """Trouve l'endpoint STT depuis la config env ou l'infra déclarée."""
    env_url = os.environ.get("STT_API_URL")
    if env_url:
        return env_url

    found = _find_stt_machine()
    if found and found[1].ip:
        from anklume.engine.ai import _DEFAULT_STT_PORT

        machine = found[1]
        port = machine.vars.get("stt_port", _DEFAULT_STT_PORT)
        return f"http://{machine.ip}:{port}"
    return None


def _list_speaches_models(url: str) -> list[str]:
    """Liste les modèles installés sur un serveur Speaches."""
    try:
        req = Request(f"{url}/v1/models", method="GET")  # noqa: S310
        response = urlopen(req, timeout=3)  # noqa: S310
        data = json.loads(response.read().decode())
        return [m.get("id", "") for m in data.get("data", [])]
    except (OSError, TimeoutError, json.JSONDecodeError, ValueError):
        return []


def _ensure_model_installed(url: str, model: str) -> bool:
    """Vérifie et installe un modèle Whisper sur Speaches."""
    if model in _list_speaches_models(url):
        return True

    typer.echo(f"  Téléchargement du modèle {model}…")
    try:
        req = Request(  # noqa: S310
            f"{url}/v1/models/{model}",
            method="POST",
        )
        urlopen(req, timeout=600)  # noqa: S310
        return True
    except (OSError, TimeoutError):
        return False


# ---------------------------------------------------------------------------
# Génération de la config Voxtype
# ---------------------------------------------------------------------------


def _generate_voxtype_config(
    endpoint: str,
    model: str,
    language: str,
    hotkey: str,
) -> str:
    """Génère le contenu du fichier config.toml pour Voxtype."""
    return f"""[hotkey]
key = "{hotkey}"
mode = "push_to_talk"

[audio]
device = "default"
sample_rate = 16000
max_duration_secs = 60

[whisper]
mode = "remote"
model = "{model}"
remote_endpoint = "{endpoint}"
remote_model = "{model}"
language = "{language}"

[output]
mode = "type"
driver_order = ["dotool", "clipboard"]
"""


# ---------------------------------------------------------------------------
# Service systemd utilisateur
# ---------------------------------------------------------------------------


def _generate_systemd_service(xkb_layout: str) -> str:
    """Génère le fichier .service systemd utilisateur pour Voxtype."""
    voxtype_path = shutil.which("voxtype") or "/usr/local/bin/voxtype"
    return f"""[Unit]
Description=Anklume STT — Voxtype push-to-talk
After=graphical-session.target pipewire.service

[Service]
Type=simple
Environment=DOTOOL_XKB_LAYOUT={xkb_layout}
ExecStart={voxtype_path}
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
"""


# ---------------------------------------------------------------------------
# Commandes CLI
# ---------------------------------------------------------------------------


def run_stt_setup(
    *,
    device: str = "auto",
    hotkey: str = "",
    model: str = "",
) -> None:
    """Installe les dépendances, configure Voxtype et le service systemd."""
    config = get_stt_config()
    hotkey = hotkey or config["hotkey"]
    model = model or config["model"]
    language = config["language"]
    xkb_layout = config["xkb_layout"]

    # 1. Vérifier les dépendances
    typer.echo("Vérification des dépendances…")
    missing = check_stt_dependencies()
    if missing:
        typer.echo("Dépendances manquantes :")
        for dep in missing:
            typer.echo(f"  - {dep}")
        typer.echo("\nInstallez-les avec votre gestionnaire de paquets.")
        typer.echo("  Arch : paru -S voxtype-bin dotool")
        raise typer.Exit(1)
    typer.echo("  Dépendances : OK")

    # 2. Trouver le serveur STT
    typer.echo("Recherche du serveur STT…")
    endpoint = _find_stt_endpoint()
    if not endpoint:
        typer.echo("  Aucun serveur STT trouvé.")
        typer.echo("  Configurez STT_API_URL ou déployez un domaine avec le rôle stt_server.")
        raise typer.Exit(1)

    is_healthy = check_service_health(f"{endpoint}/v1/models")
    if is_healthy:
        typer.echo(f"  Serveur STT : actif ({endpoint})")
    else:
        typer.echo(f"  Serveur STT : injoignable ({endpoint})")
        typer.echo("  Le setup continue, le serveur sera utilisé quand il sera disponible.")

    # 3. Installer le modèle sur Speaches
    if is_healthy:
        typer.echo(f"Vérification du modèle {model}…")
        if _ensure_model_installed(endpoint, model):
            typer.echo(f"  Modèle {model} : OK")
        else:
            typer.echo(f"  Échec installation modèle {model}")

    # 4. Configurer le device STT (GPU/CPU) sur le serveur
    if device != "auto":
        typer.echo(f"Configuration device serveur : {device}")
        _configure_server_device(device)

    # 5. Générer la config Voxtype
    typer.echo("Configuration de Voxtype…")
    _VOXTYPE_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    config_content = _generate_voxtype_config(endpoint, model, language, hotkey)
    _VOXTYPE_CONFIG_PATH.write_text(config_content)
    typer.echo(f"  Config écrite : {_VOXTYPE_CONFIG_PATH}")

    # 6. Créer le service systemd utilisateur
    typer.echo("Configuration du service systemd…")
    _SYSTEMD_USER_DIR.mkdir(parents=True, exist_ok=True)
    service_path = _SYSTEMD_USER_DIR / _SYSTEMD_SERVICE
    service_content = _generate_systemd_service(xkb_layout)
    service_path.write_text(service_content)
    typer.echo(f"  Service écrit : {service_path}")

    # Recharger systemd
    subprocess.run(
        ["systemctl", "--user", "daemon-reload"],
        capture_output=True,
    )

    typer.echo("\nSetup terminé. Commandes disponibles :")
    typer.echo("  anklume stt start   — Démarrer le push-to-talk")
    typer.echo("  anklume stt stop    — Arrêter")
    typer.echo("  anklume stt status  — État du service")


def run_stt_start() -> None:
    """Démarre le daemon Voxtype via systemd user."""
    if not _VOXTYPE_CONFIG_PATH.exists():
        typer.echo("Configuration absente. Lancez d'abord : anklume stt setup")
        raise typer.Exit(1)

    service_path = _SYSTEMD_USER_DIR / _SYSTEMD_SERVICE
    if service_path.exists():
        result = subprocess.run(
            ["systemctl", "--user", "start", _SYSTEMD_SERVICE],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            typer.echo("STT démarré (push-to-talk actif)")
        else:
            typer.echo(f"Échec démarrage : {result.stderr.strip()}")
            raise typer.Exit(1)
    else:
        # Fallback : lancer directement
        xkb_layout = get_stt_config()["xkb_layout"]
        env = os.environ.copy()
        env["DOTOOL_XKB_LAYOUT"] = xkb_layout
        subprocess.Popen(
            ["voxtype"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        typer.echo("STT démarré (push-to-talk actif)")


def run_stt_stop() -> None:
    """Arrête le daemon Voxtype."""
    service_path = _SYSTEMD_USER_DIR / _SYSTEMD_SERVICE
    stopped = False
    if service_path.exists():
        result = subprocess.run(
            ["systemctl", "--user", "stop", _SYSTEMD_SERVICE],
            capture_output=True,
            text=True,
        )
        stopped = result.returncode == 0
    if not stopped:
        subprocess.run(["pkill", "-f", "voxtype"], capture_output=True)
    typer.echo("STT arrêté")


def run_stt_status() -> None:
    """Affiche l'état complet du STT (client hôte + serveur distant)."""
    # Dépendances hôte
    missing = check_stt_dependencies()
    typer.echo("Client hôte :")
    if missing:
        typer.echo("  Dépendances manquantes :")
        for dep in missing:
            typer.echo(f"    - {dep}")
    else:
        typer.echo("  Dépendances : OK")

    # État du daemon Voxtype
    service_path = _SYSTEMD_USER_DIR / _SYSTEMD_SERVICE
    if service_path.exists():
        result = subprocess.run(
            ["systemctl", "--user", "is-active", _SYSTEMD_SERVICE],
            capture_output=True,
            text=True,
        )
        state = result.stdout.strip()
        typer.echo(f"  Voxtype : {state}")
    else:
        result = subprocess.run(
            ["pgrep", "-f", "voxtype"],
            capture_output=True,
        )
        running = result.returncode == 0
        typer.echo(f"  Voxtype : {'actif' if running else 'inactif'}")

    # Config Voxtype
    if _VOXTYPE_CONFIG_PATH.exists():
        typer.echo(f"  Config : {_VOXTYPE_CONFIG_PATH}")
    else:
        typer.echo("  Config : absente (lancez anklume stt setup)")

    # Serveur STT distant
    typer.echo("\nServeur STT :")
    endpoint = _find_stt_endpoint()
    if not endpoint:
        typer.echo("  Endpoint : non configuré")
        return

    models = _list_speaches_models(endpoint)
    if models:
        typer.echo(f"  Endpoint : actif ({endpoint})")
        whisper_models = [m for m in models if "whisper" in m.lower() or "faster" in m.lower()]
        if whisper_models:
            typer.echo(f"  Modèles : {', '.join(whisper_models)}")
        else:
            typer.echo("  Modèles : aucun modèle Whisper installé")

        # Vérifier le device (GPU/CPU)
        _show_server_device()
    else:
        if check_service_health(f"{endpoint}/v1/models"):
            typer.echo(f"  Endpoint : actif ({endpoint})")
            typer.echo("  Modèles : aucun")
        else:
            typer.echo(f"  Endpoint : injoignable ({endpoint})")


# ---------------------------------------------------------------------------
# Configuration device serveur (GPU/CPU)
# ---------------------------------------------------------------------------


def _configure_server_device(device: str) -> None:
    """Configure le device d'inférence (gpu/cpu) sur le serveur Speaches."""
    found = _find_stt_machine()
    if not found:
        typer.echo("  Impossible de configurer le device serveur")
        return
    domain_name, machine = found
    _set_device_on_container(domain_name, machine.full_name, device)


def _set_device_on_container(
    project: str,
    instance: str,
    device: str,
) -> None:
    """Configure le device dans le service systemd du conteneur."""
    inference_device = "cuda" if device == "gpu" else "cpu"
    compute_type = "float16" if device == "gpu" else "int8"

    # Modifier le service systemd via sed
    # Les valeurs sont restreintes à un set connu (pas d'input utilisateur libre)
    _ALLOWED_DEVICES = {"cuda", "cpu"}
    _ALLOWED_COMPUTE = {"float16", "int8"}
    for var, value, allowed in [
        ("WHISPER__INFERENCE_DEVICE", inference_device, _ALLOWED_DEVICES),
        ("WHISPER__COMPUTE_TYPE", compute_type, _ALLOWED_COMPUTE),
    ]:
        if value not in allowed:
            continue
        subprocess.run(
            [
                "incus",
                "exec",
                instance,
                "--project",
                project,
                "--",
                "sed",
                "-i",
                f"s|{var}=.*|{var}={value}|",
                "/etc/systemd/system/speaches.service",
            ],
            capture_output=True,
        )

    # Redémarrer Speaches
    for cmd in ["daemon-reload", "restart speaches"]:
        subprocess.run(
            ["incus", "exec", instance, "--project", project, "--", "systemctl", *cmd.split()],
            capture_output=True,
        )
    typer.echo(f"  Device serveur : {device} ({inference_device}/{compute_type})")


def _show_server_device() -> None:
    """Affiche le device d'inférence utilisé par le serveur."""
    found = _find_stt_machine()
    if not found:
        return
    domain_name, machine = found
    result = subprocess.run(
        [
            "incus",
            "exec",
            machine.full_name,
            "--project",
            domain_name,
            "--",
            "grep",
            "WHISPER__INFERENCE_DEVICE",
            "/etc/systemd/system/speaches.service",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        line = result.stdout.strip()
        if "cuda" in line:
            typer.echo("  Device : GPU (CUDA)")
        else:
            typer.echo("  Device : CPU")
