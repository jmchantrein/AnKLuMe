"""Génération de domaines d'environnement de développement.

Produit un fichier domaine YAML complet pour un environnement de dev,
avec choix LXC/VM, GPU optionnel, LLM local/cloud, sanitisation,
montages persistants.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import yaml

from anklume.engine.llm_routing import (
    BACKEND_LOCAL,
    SANITIZE_FALSE,
    SANITIZE_TRUE,
)


@dataclass
class DevEnvConfig:
    """Configuration d'un environnement de développement."""

    name: str = "dev"
    description: str = ""
    machine_type: str = "lxc"
    trust_level: str = "trusted"
    gpu: bool = False
    llm: bool = False
    claude_code: bool = False
    mount_paths: dict[str, str] = field(default_factory=dict)
    memory: str = ""
    cpu: str = ""
    extra_packages: list[str] = field(default_factory=list)
    git_name: str = ""
    git_email: str = ""
    os_image: str = ""
    # LLM routing
    llm_backend: str = BACKEND_LOCAL
    llm_model: str = ""
    llm_api_url: str = ""
    llm_api_key: str = ""
    # Sanitisation
    sanitize: str = SANITIZE_FALSE

    def __post_init__(self) -> None:
        if not self.description:
            self.description = f"Environnement de développement {self.name}"


def _build_machines(config: DevEnvConfig) -> dict[str, dict]:
    """Construit la section machines du domaine."""
    # Rôles de base + dev
    roles: list[str] = ["base", "dev-tools", "dev_env"]

    # Ollama local si GPU + backend local
    if config.gpu and config.llm_backend == BACKEND_LOCAL:
        roles.append("ollama_server")

    # Variables Ansible pour la machine dev
    machine_vars: dict = {}

    # AI coding tools
    if config.claude_code:
        machine_vars["dev_env_install_claude_code"] = True
        machine_vars["dev_env_install_node"] = True

    if config.llm:
        machine_vars["dev_env_install_aider"] = True

    # LLM routing vars
    if config.llm and config.llm_backend != BACKEND_LOCAL:
        machine_vars["llm_backend"] = config.llm_backend
        if config.llm_api_url:
            machine_vars["llm_api_url"] = config.llm_api_url
        if config.llm_api_key:
            machine_vars["llm_api_key"] = config.llm_api_key

    if config.llm_model:
        if config.llm_backend == BACKEND_LOCAL:
            machine_vars["ollama_default_model"] = config.llm_model
        else:
            machine_vars["llm_model"] = config.llm_model

    # Sanitisation
    if config.sanitize != SANITIZE_FALSE:
        machine_vars["ai_sanitize"] = config.sanitize

    # Git config
    if config.git_name:
        machine_vars["dev_env_git_name"] = config.git_name
    if config.git_email:
        machine_vars["dev_env_git_email"] = config.git_email

    # Paquets supplémentaires
    if config.extra_packages:
        machine_vars["dev_env_extra_packages"] = config.extra_packages

    # Config Incus (limites ressources)
    machine_config: dict = {}
    if config.memory:
        machine_config["limits.memory"] = config.memory
    if config.cpu:
        machine_config["limits.cpu"] = config.cpu

    # Machine principale (dev)
    machine: dict = {
        "description": config.description,
        "type": config.machine_type,
        "roles": roles,
    }
    if config.gpu:
        machine["gpu"] = True
    if machine_vars:
        machine["vars"] = machine_vars
    if machine_config:
        machine["config"] = machine_config
    if config.mount_paths:
        machine["persistent"] = config.mount_paths

    machines: dict[str, dict] = {config.name: machine}

    # Machine sanitizer dédiée (si sanitisation activée)
    if config.sanitize != SANITIZE_FALSE:
        sanitizer_vars: dict = {
            "sanitizer_mode": "mask",
            "sanitizer_audit": True,
        }
        machines["sanitizer"] = {
            "description": "Proxy de sanitisation LLM",
            "type": "lxc",
            "roles": ["base", "llm_sanitizer"],
            "vars": sanitizer_vars,
        }

    return machines


def generate_dev_domain(config: DevEnvConfig) -> str:
    """Génère le YAML d'un domaine de développement.

    Returns:
        Contenu YAML prêt à écrire dans domains/<name>.yml
    """
    machines = _build_machines(config)

    # Domaine
    domain: dict = {
        "description": config.description,
        "trust_level": config.trust_level,
        "machines": machines,
    }

    # Sérialiser en YAML avec commentaire d'en-tête
    header = (
        f"# Domaine {config.name} — environnement de développement\n"
        f"# Généré par : anklume dev env\n"
    )
    body = yaml.dump(
        domain,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )
    return header + body


def generate_dev_policies(
    config: DevEnvConfig,
    *,
    ai_domain: str = "ai-tools",
) -> str:
    """Génère les politiques réseau pour un environnement de dev.

    - Ollama distant (pas de GPU local) : accès au port 11434
    - STT distant : accès au port 8000
    - Sanitizer dans le même domaine : pas de politique nécessaire
    """
    policies: list[dict] = []

    # Accès à Ollama distant si backend local sans GPU
    if config.llm and config.llm_backend == BACKEND_LOCAL and not config.gpu:
        policies.append(
            {
                "from": config.name,
                "to": ai_domain,
                "ports": [11434],
                "description": f"{config.name} accède à Ollama",
            }
        )

    # Accès STT distant
    if config.llm:
        policies.append(
            {
                "from": config.name,
                "to": ai_domain,
                "ports": [8000],
                "description": f"{config.name} accède à Speaches (STT)",
            }
        )

    if not policies:
        return ""

    return yaml.dump(
        {"policies": policies},
        default_flow_style=False,
        allow_unicode=True,
    )


# --- Preset : self-dev anklume ---


def anklume_self_dev_config() -> DevEnvConfig:
    """Configuration prédéfinie pour le développement d'anklume.

    Environnement LXC léger avec uv, ruff, pytest, Claude Code,
    repo anklume monté en persistant, sanitisation activée pour
    les appels cloud.
    """
    return DevEnvConfig(
        name="ank-dev",
        description="Développement anklume",
        machine_type="lxc",
        trust_level="trusted",
        gpu=False,
        llm=True,
        claude_code=True,
        mount_paths={"anklume": "/home/dev/AnKLuMe"},
        memory="4GiB",
        cpu="4",
        extra_packages=["shellcheck", "ansible"],
        llm_backend=BACKEND_LOCAL,
        llm_model="",
        sanitize=SANITIZE_TRUE,
    )
