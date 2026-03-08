"""Logique métier IA — état des services, flush, switch.

Détecte l'état des services IA (Ollama, STT) et fournit les
informations pour `anklume ai status`, `anklume ai flush`,
`anklume ai switch`.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, urlopen

from anklume.engine.gpu import GpuInfo, detect_gpu
from anklume.engine.models import Infrastructure

log = logging.getLogger(__name__)

# Ports par défaut (canoniques : provisioner/roles/*/defaults/main.yml)
_DEFAULT_OLLAMA_PORT = 11434
_DEFAULT_STT_PORT = 8000
_DEFAULT_LLAMA_SERVER_PORT = 8081
_DEFAULT_OPEN_WEBUI_PORT = 3000
_DEFAULT_LOBECHAT_PORT = 3210
_DEFAULT_OPENCLAW_PORT = 8090
_SERVICE_TIMEOUT = 3  # secondes

# Rôles IA reconnus
ROLE_OLLAMA_SERVER = "ollama_server"
ROLE_STT_SERVER = "stt_server"
ROLE_OPEN_WEBUI = "open_webui"
ROLE_LOBECHAT = "lobechat"
ROLE_OPENCLAW_SERVER = "openclaw_server"

# Descripteurs de services IA (data-driven)
_SERVICE_DEFS: list[dict[str, str | int]] = [
    {
        "role": ROLE_OLLAMA_SERVER,
        "name": "ollama",
        "port_var": "ollama_port",
        "default_port": _DEFAULT_OLLAMA_PORT,
        "health_path": "/api/ps",
    },
    {
        "role": ROLE_STT_SERVER,
        "name": "stt",
        "port_var": "stt_port",
        "default_port": _DEFAULT_STT_PORT,
        "health_path": "/v1/models",
    },
    {
        "role": ROLE_OPEN_WEBUI,
        "name": "open_webui",
        "port_var": "open_webui_port",
        "default_port": _DEFAULT_OPEN_WEBUI_PORT,
        "health_path": "/",
    },
    {
        "role": ROLE_LOBECHAT,
        "name": "lobechat",
        "port_var": "lobechat_port",
        "default_port": _DEFAULT_LOBECHAT_PORT,
        "health_path": "/",
    },
    {
        "role": ROLE_OPENCLAW_SERVER,
        "name": "openclaw",
        "port_var": "openclaw_port",
        "default_port": _DEFAULT_OPENCLAW_PORT,
        "health_path": "/health",
    },
]

DEFAULT_STATE_PATH = Path("/var/lib/anklume/ai-access.json")


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class AiServiceStatus:
    """État d'un service IA."""

    name: str
    reachable: bool
    url: str
    detail: str = ""


@dataclass
class AiStatus:
    """État complet de l'infrastructure IA."""

    gpu: GpuInfo
    services: list[AiServiceStatus] = field(default_factory=list)


@dataclass
class FlushResult:
    """Résultat d'un flush VRAM."""

    models_unloaded: list[str]
    llama_server_stopped: bool
    vram_before_mib: int
    vram_after_mib: int


@dataclass
class AiAccessState:
    """État de l'accès GPU courant."""

    domain: str | None
    timestamp: str
    previous: str | None = None


# ---------------------------------------------------------------------------
# compute_ai_status
# ---------------------------------------------------------------------------


def compute_ai_status(infra: Infrastructure) -> AiStatus:
    """Calcule l'état des services IA.

    Détecte le GPU, puis vérifie la joignabilité d'Ollama et Speaches
    sur les machines ayant les rôles correspondants.
    """
    gpu_info = detect_gpu()
    services: list[AiServiceStatus] = []

    for domain in infra.enabled_domains:
        for machine in domain.machines.values():
            if not machine.ip:
                continue

            for svc_def in _SERVICE_DEFS:
                if str(svc_def["role"]) not in machine.roles:
                    continue
                port = machine.vars.get(
                    str(svc_def["port_var"]),
                    svc_def["default_port"],
                )
                health_url = f"http://{machine.ip}:{port}{svc_def['health_path']}"
                svc_name = str(svc_def["name"])
                detail, reachable = _check_service(health_url, svc_name)
                services.append(
                    AiServiceStatus(
                        name=svc_name,
                        reachable=reachable,
                        url=f"http://{machine.ip}:{port}",
                        detail=detail,
                    )
                )

    return AiStatus(gpu=gpu_info, services=services)


# ---------------------------------------------------------------------------
# flush_vram
# ---------------------------------------------------------------------------


def flush_vram(infra: Infrastructure) -> FlushResult:
    """Libère la VRAM GPU — décharge les modèles Ollama, arrête llama-server.

    Best-effort : chaque étape est indépendante.
    """
    gpu_before = detect_gpu()

    if not gpu_before.detected:
        return FlushResult(
            models_unloaded=[],
            llama_server_stopped=False,
            vram_before_mib=0,
            vram_after_mib=0,
        )

    # Trouver la machine Ollama
    ollama_ip, ollama_port, project, instance_name = _find_ollama_machine(infra)

    models_unloaded: list[str] = []
    if ollama_ip:
        models_unloaded = _unload_all_models(ollama_ip, ollama_port)

    # Arrêter llama-server si actif
    llama_stopped = False
    if ollama_ip and project and instance_name:
        llama_stopped = _stop_llama_server(
            ollama_ip,
            _DEFAULT_LLAMA_SERVER_PORT,
            project,
            instance_name,
        )

    gpu_after = detect_gpu()

    return FlushResult(
        models_unloaded=models_unloaded,
        llama_server_stopped=llama_stopped,
        vram_before_mib=gpu_before.vram_used_mib,
        vram_after_mib=gpu_after.vram_used_mib,
    )


# ---------------------------------------------------------------------------
# State file — accès GPU
# ---------------------------------------------------------------------------


def read_ai_access(*, state_path: Path | None = None) -> AiAccessState:
    """Lit le fichier d'état d'accès GPU."""
    path = state_path or DEFAULT_STATE_PATH
    if not path.exists():
        return AiAccessState(domain=None, timestamp="")

    try:
        data = json.loads(path.read_text())
        return AiAccessState(
            domain=data.get("domain"),
            timestamp=data.get("timestamp", ""),
            previous=data.get("previous"),
        )
    except (json.JSONDecodeError, OSError):
        return AiAccessState(domain=None, timestamp="")


def write_ai_access(
    domain: str,
    *,
    state_path: Path | None = None,
) -> AiAccessState:
    """Écrit le fichier d'état d'accès GPU."""
    path = state_path or DEFAULT_STATE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    # Lire l'état précédent
    previous_state = read_ai_access(state_path=path)
    previous_domain = previous_state.domain

    timestamp = datetime.now(tz=UTC).isoformat()
    state = AiAccessState(
        domain=domain,
        timestamp=timestamp,
        previous=previous_domain,
    )

    data = {
        "domain": state.domain,
        "timestamp": state.timestamp,
        "previous": state.previous,
    }
    path.write_text(json.dumps(data, indent=2) + "\n")

    return state


# ---------------------------------------------------------------------------
# switch_ai_access
# ---------------------------------------------------------------------------


def switch_ai_access(
    infra: Infrastructure,
    target_domain: str,
) -> AiAccessState:
    """Bascule l'accès exclusif GPU vers un domaine.

    Raises:
        ValueError: domaine inexistant, désactivé, ou politique open.
    """
    # Vérifier la politique
    if infra.config.ai_access_policy == "open":
        msg = "Switch désactivé en politique open"
        raise ValueError(msg)

    # Vérifier que le domaine cible existe
    if target_domain not in infra.domains:
        msg = f"Domaine '{target_domain}' inexistant"
        raise ValueError(msg)

    # Vérifier que le domaine est activé
    if not infra.domains[target_domain].enabled:
        msg = f"Domaine '{target_domain}' désactivé"
        raise ValueError(msg)

    # Flush VRAM
    flush_vram(infra)

    # Écrire le nouvel état
    return write_ai_access(target_domain, state_path=DEFAULT_STATE_PATH)


# ---------------------------------------------------------------------------
# Service health check (public — réutilisé par cli/_stt.py)
# ---------------------------------------------------------------------------


def check_service_health(url: str) -> bool:
    """Vérifie qu'un endpoint HTTP répond avec status 200."""
    try:
        req = Request(url, method="GET")  # noqa: S310
        response = urlopen(req, timeout=_SERVICE_TIMEOUT)  # noqa: S310
        return response.status == 200
    except (OSError, TimeoutError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Helpers internes
# ---------------------------------------------------------------------------


def _find_ollama_machine(
    infra: Infrastructure,
) -> tuple[str | None, int, str | None, str | None]:
    """Trouve l'IP, le port, le projet et le nom de la machine Ollama.

    Returns:
        (ip, port, project_name, instance_full_name) ou (None, default_port, None, None).
    """
    for domain in infra.enabled_domains:
        for machine in domain.machines.values():
            if ROLE_OLLAMA_SERVER in machine.roles and machine.ip:
                port = machine.vars.get("ollama_port", _DEFAULT_OLLAMA_PORT)
                return machine.ip, port, domain.name, machine.full_name
    return None, _DEFAULT_OLLAMA_PORT, None, None


def _unload_all_models(ip: str, port: int) -> list[str]:
    """Décharge tous les modèles Ollama chargés en VRAM."""
    # Lister les modèles chargés
    try:
        ps_url = f"http://{ip}:{port}/api/ps"
        req = Request(ps_url, method="GET")  # noqa: S310
        response = urlopen(req, timeout=_SERVICE_TIMEOUT)  # noqa: S310
        data = json.loads(response.read().decode())
        models = [m.get("name", "") for m in data.get("models", [])]
    except (OSError, TimeoutError, json.JSONDecodeError):
        return []

    # Décharger chaque modèle
    unloaded = []
    for model_name in models:
        if not model_name:
            continue
        try:
            payload = json.dumps({"model": model_name, "keep_alive": 0}).encode()
            gen_url = f"http://{ip}:{port}/api/generate"
            req = Request(gen_url, data=payload, method="POST")  # noqa: S310
            req.add_header("Content-Type", "application/json")
            urlopen(req, timeout=_SERVICE_TIMEOUT)  # noqa: S310
            unloaded.append(model_name)
        except (OSError, TimeoutError):
            log.warning("Échec déchargement modèle %s", model_name)

    return unloaded


def _stop_llama_server(
    ip: str,
    port: int,
    project: str,
    instance_name: str,
) -> bool:
    """Arrête llama-server si actif (via health check puis incus exec)."""
    if not check_service_health(f"http://{ip}:{port}/health"):
        return False

    return _incus_exec_stop_llama(project, instance_name)


def _incus_exec_stop_llama(project: str, instance_name: str) -> bool:
    """Exécute systemctl stop llama-server via incus exec."""
    try:
        subprocess.run(
            [
                "incus",
                "exec",
                instance_name,
                "--project",
                project,
                "--",
                "systemctl",
                "stop",
                "llama-server",
            ],
            capture_output=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
    return True


def _check_service(url: str, service_type: str) -> tuple[str, bool]:
    """Vérifie la joignabilité d'un service IA.

    Returns:
        (detail, reachable) — detail est une info supplémentaire, reachable un bool.
    """
    try:
        req = Request(url, method="GET")  # noqa: S310
        response = urlopen(req, timeout=_SERVICE_TIMEOUT)  # noqa: S310
        if response.status == 200:
            body = response.read().decode()
            return _parse_service_response(body, service_type), True
    except (OSError, TimeoutError, ValueError):
        pass

    return "", False


def _parse_service_response(body: str, service_type: str) -> str:
    """Extrait un résumé de la réponse du service."""
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return "actif"

    if service_type == "ollama":
        models = data.get("models", [])
        if models:
            names = [m.get("name", "?") for m in models]
            return ", ".join(names) + " chargé"
        return "actif (aucun modèle chargé)"

    if service_type == "stt":
        return "actif"

    return "actif"
