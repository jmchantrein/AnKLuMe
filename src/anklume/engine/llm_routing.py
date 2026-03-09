"""Routage LLM — résolution du backend et intégration sanitiser.

Résout l'endpoint LLM effectif pour chaque machine consommatrice :
local (Ollama), externe (OpenAI-compatible, Anthropic), avec
routage conditionnel via le proxy de sanitisation.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

from anklume.engine.ai import (
    DEFAULT_OLLAMA_PORT,
    ROLE_LOBECHAT,
    ROLE_OLLAMA_SERVER,
    ROLE_OPEN_WEBUI,
    ROLE_OPENCLAW_SERVER,
)
from anklume.engine.models import Domain, Infrastructure, Machine

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

BACKEND_LOCAL = "local"
BACKEND_OPENAI = "openai"
BACKEND_ANTHROPIC = "anthropic"

LLM_BACKENDS = {BACKEND_LOCAL, BACKEND_OPENAI, BACKEND_ANTHROPIC}

SANITIZE_FALSE = "false"
SANITIZE_TRUE = "true"
SANITIZE_ALWAYS = "always"

AI_SANITIZE_VALUES = {SANITIZE_FALSE, SANITIZE_TRUE, SANITIZE_ALWAYS}

ROLE_LLM_SANITIZER = "llm_sanitizer"
ROLE_OPENCODE_SERVER = "opencode_server"

LLM_CONSUMER_ROLES = {
    ROLE_OPENCLAW_SERVER,
    ROLE_LOBECHAT,
    ROLE_OPEN_WEBUI,
    ROLE_OPENCODE_SERVER,
}

_EXTERNAL_BACKENDS = {BACKEND_OPENAI, BACKEND_ANTHROPIC}

_DEFAULT_SANITIZER_PORT = 8089


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass
class LlmEndpoint:
    """Endpoint LLM résolu pour une machine."""

    backend: str  # BACKEND_LOCAL, BACKEND_OPENAI, BACKEND_ANTHROPIC
    url: str  # URL effective (Ollama, cloud, ou sanitizer)
    api_key: str  # Clé API (vide pour local)
    model: str  # Modèle sélectionné
    sanitized: bool  # Passe par le proxy sanitizer
    upstream_url: str  # URL réelle derrière le sanitizer (vide si direct)


# ---------------------------------------------------------------------------
# _find_machine_by_role — helper générique
# ---------------------------------------------------------------------------


def _find_machine_by_role(
    role: str,
    domain: Domain,
    infra: Infrastructure,
) -> Machine | None:
    """Trouve la première machine avec le rôle donné et une IP.

    Cherche d'abord dans le domaine spécifié, puis dans tous les
    domaines activés.
    """
    for machine in domain.machines.values():
        if role in machine.roles and machine.ip:
            return machine

    for d in infra.enabled_domains:
        if d.name == domain.name:
            continue
        for machine in d.machines.values():
            if role in machine.roles and machine.ip:
                return machine

    return None


def _machine_url(machine: Machine, port_var: str, default_port: int) -> str:
    """Construit l'URL HTTP d'une machine à partir de son IP et port."""
    port = machine.vars.get(port_var, default_port)
    return f"http://{machine.ip}:{port}"


# ---------------------------------------------------------------------------
# resolve_llm_endpoint
# ---------------------------------------------------------------------------


def resolve_llm_endpoint(
    machine: Machine,
    domain: Domain,
    infra: Infrastructure,
) -> LlmEndpoint:
    """Résout l'endpoint LLM effectif pour une machine.

    Raises:
        ValueError: configuration invalide (backend inconnu,
                    URL manquante, sanitizer introuvable).
    """
    mv = machine.vars
    backend = str(mv.get("llm_backend", BACKEND_LOCAL))
    ai_sanitize = str(mv.get("ai_sanitize", SANITIZE_FALSE))
    api_url = str(mv.get("llm_api_url", ""))
    api_key = str(mv.get("llm_api_key", ""))
    model = str(mv.get("llm_model", ""))

    # Validation
    errors = validate_llm_config(backend, ai_sanitize, api_url, api_key)
    if errors:
        msg = "; ".join(errors)
        raise ValueError(msg)

    # Déterminer si la sanitisation est active
    needs_sanitize = _needs_sanitization(backend, ai_sanitize)

    # Résoudre l'URL du backend réel
    if backend == BACKEND_LOCAL:
        real_url = find_ollama_url(domain, infra)
    else:
        real_url = api_url

    # Routage via sanitizer si requis
    if needs_sanitize:
        sanitizer_url = find_sanitizer_url(domain, infra)
        if sanitizer_url is None:
            msg = (
                f"ai_sanitize={ai_sanitize!r} mais aucune machine avec rôle "
                f"'llm_sanitizer' trouvée dans l'infrastructure"
            )
            raise ValueError(msg)
        return LlmEndpoint(
            backend=backend,
            url=sanitizer_url,
            api_key=api_key,
            model=model,
            sanitized=True,
            upstream_url=real_url,
        )

    return LlmEndpoint(
        backend=backend,
        url=real_url,
        api_key=api_key,
        model=model,
        sanitized=False,
        upstream_url="",
    )


# ---------------------------------------------------------------------------
# find_sanitizer_url
# ---------------------------------------------------------------------------


def find_sanitizer_url(
    domain: Domain,
    infra: Infrastructure,
) -> str | None:
    """Trouve l'URL du proxy sanitizer dans le domaine ou l'infra.

    Cherche d'abord dans le même domaine, puis dans tous les
    domaines activés.
    """
    machine = _find_machine_by_role(ROLE_LLM_SANITIZER, domain, infra)
    if machine is None:
        return None
    return _machine_url(machine, "sanitizer_port", _DEFAULT_SANITIZER_PORT)


# ---------------------------------------------------------------------------
# find_ollama_url
# ---------------------------------------------------------------------------


def find_ollama_url(
    domain: Domain,
    infra: Infrastructure,
) -> str:
    """Trouve l'URL Ollama accessible depuis le domaine.

    Cherche d'abord dans le même domaine, puis dans l'infra.
    Fallback : localhost.
    """
    machine = _find_machine_by_role(ROLE_OLLAMA_SERVER, domain, infra)
    if machine is None:
        return f"http://localhost:{DEFAULT_OLLAMA_PORT}"
    return _machine_url(machine, "ollama_port", DEFAULT_OLLAMA_PORT)


# ---------------------------------------------------------------------------
# enrich_llm_vars
# ---------------------------------------------------------------------------


def enrich_llm_vars(infra: Infrastructure) -> Infrastructure:
    """Enrichit les vars des machines avec les endpoints résolus.

    Ajoute ``llm_effective_url``, ``llm_effective_key``,
    ``llm_effective_model``, ``llm_effective_backend`` aux machines
    qui ont un rôle consommateur LLM.

    Met aussi à jour ``sanitizer_upstream_url`` sur les machines
    sanitizer quand un consommateur les référence.

    Retourne une copie enrichie de l'infrastructure.
    """
    # Fast path : pas de consommateur LLM → retour direct
    if not any(
        _is_llm_consumer(m)
        for d in infra.enabled_domains
        for m in d.machines.values()
    ):
        return infra

    enriched = copy.deepcopy(infra)

    # Collecter les upstream URLs pour les sanitizers
    # full_name -> {upstream_urls}
    sanitizer_upstreams: dict[str, set[str]] = {}

    for domain in enriched.enabled_domains:
        for machine in domain.machines.values():
            if not _is_llm_consumer(machine):
                continue

            ep = resolve_llm_endpoint(machine, domain, enriched)

            machine.vars["llm_effective_backend"] = ep.backend
            machine.vars["llm_effective_url"] = ep.url
            machine.vars["llm_effective_key"] = ep.api_key
            machine.vars["llm_effective_model"] = ep.model

            # Collecter l'upstream pour le sanitizer
            if ep.sanitized and ep.upstream_url:
                san = _find_machine_by_role(ROLE_LLM_SANITIZER, domain, enriched)
                if san is not None:
                    sanitizer_upstreams.setdefault(
                        san.full_name, set()
                    ).add(ep.upstream_url)

    # Appliquer les upstream URLs sur les machines sanitizer
    for domain in enriched.enabled_domains:
        for machine in domain.machines.values():
            if ROLE_LLM_SANITIZER in machine.roles:
                upstreams = sanitizer_upstreams.get(machine.full_name, set())
                if upstreams:
                    machine.vars["sanitizer_upstream_url"] = sorted(upstreams)[0]

    return enriched


# ---------------------------------------------------------------------------
# validate_llm_config
# ---------------------------------------------------------------------------


def validate_llm_config(
    backend: str,
    ai_sanitize: str,
    api_url: str,
    api_key: str,
) -> list[str]:
    """Valide la configuration LLM d'une machine.

    Returns:
        Liste d'erreurs (vide si tout est valide).
    """
    errors: list[str] = []

    if backend not in LLM_BACKENDS:
        errors.append(
            f"llm_backend '{backend}' invalide "
            f"(valeurs possibles : {', '.join(sorted(LLM_BACKENDS))})"
        )

    if ai_sanitize not in AI_SANITIZE_VALUES:
        errors.append(
            f"ai_sanitize '{ai_sanitize}' invalide "
            f"(valeurs possibles : {', '.join(sorted(AI_SANITIZE_VALUES))})"
        )

    if backend in _EXTERNAL_BACKENDS:
        if not api_url:
            errors.append(
                f"llm_api_url requis pour le backend '{backend}'"
            )
        if not api_key:
            errors.append(
                f"llm_api_key requis pour le backend '{backend}'"
            )

    return errors


# ---------------------------------------------------------------------------
# Helpers internes
# ---------------------------------------------------------------------------


def _needs_sanitization(backend: str, ai_sanitize: str) -> bool:
    """Détermine si la sanitisation est requise."""
    if ai_sanitize == SANITIZE_ALWAYS:
        return True
    if ai_sanitize == SANITIZE_TRUE and backend in _EXTERNAL_BACKENDS:
        return True
    return False


def _is_llm_consumer(machine: Machine) -> bool:
    """Vérifie si la machine a un rôle consommateur LLM."""
    return bool(set(machine.roles) & LLM_CONSUMER_ROLES)
