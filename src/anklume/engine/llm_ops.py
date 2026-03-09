"""Opérations LLM — status dédié et benchmark inférence.

Vue spécialisée sur les backends LLM configurés, les modèles
chargés et les performances d'inférence.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from urllib.request import Request, urlopen

from anklume.engine.ai import (
    DEFAULT_OLLAMA_PORT,
    SERVICE_TIMEOUT,
    find_ollama_machine,
)
from anklume.engine.gpu import GpuInfo, detect_gpu
from anklume.engine.llm_routing import (
    LLM_CONSUMER_ROLES,
    resolve_llm_endpoint,
)
from anklume.engine.models import Infrastructure


@dataclass
class LlmMachineStatus:
    """État LLM d'une machine consommatrice."""

    name: str
    backend: str
    sanitized: bool
    url: str


@dataclass
class LlmStatus:
    """État complet LLM."""

    gpu: GpuInfo
    machines: list[LlmMachineStatus] = field(default_factory=list)
    ollama_status: str = "injoignable"
    ollama_models: list[str] = field(default_factory=list)


@dataclass
class BenchResult:
    """Résultat d'un benchmark LLM."""

    model: str
    prompt: str
    tokens: int
    duration_s: float
    tokens_per_s: float


def compute_llm_status(infra: Infrastructure) -> LlmStatus:
    """Vue LLM dédiée : GPU, machines consommatrices, état Ollama."""
    gpu_info = detect_gpu()
    machines: list[LlmMachineStatus] = []

    for domain in infra.enabled_domains:
        for machine in domain.machines.values():
            if not set(machine.roles) & LLM_CONSUMER_ROLES:
                continue

            try:
                ep = resolve_llm_endpoint(machine, domain, infra)
                machines.append(
                    LlmMachineStatus(
                        name=machine.full_name,
                        backend=ep.backend,
                        sanitized=ep.sanitized,
                        url=ep.url,
                    )
                )
            except ValueError:
                machines.append(
                    LlmMachineStatus(
                        name=machine.full_name,
                        backend="erreur",
                        sanitized=False,
                        url="",
                    )
                )

    base_url = _ollama_base_url(infra)
    reachable, models = _fetch_ollama_ps(base_url)
    ollama_status = "actif" if reachable else "injoignable"

    return LlmStatus(
        gpu=gpu_info,
        machines=machines,
        ollama_status=ollama_status,
        ollama_models=models,
    )


def run_llm_bench(
    infra: Infrastructure,
    *,
    model: str = "",
    prompt: str = "Bonjour, comment ça va ?",
) -> BenchResult:
    """Benchmark d'inférence Ollama — mesure tokens/s et latence.

    Raises:
        ValueError: Ollama injoignable ou modèle indisponible.
    """
    base_url = _ollama_base_url(infra)

    reachable, models = _fetch_ollama_ps(base_url)
    if not reachable:
        msg = f"Ollama injoignable sur {base_url}"
        raise ValueError(msg)

    if not model:
        if not models:
            msg = "Aucun modèle chargé dans Ollama"
            raise ValueError(msg)
        model = models[0]

    gen_url = f"{base_url}/api/generate"
    payload = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
        }
    ).encode()

    req = Request(gen_url, data=payload, method="POST")  # noqa: S310
    req.add_header("Content-Type", "application/json")

    start = time.monotonic()
    try:
        response = urlopen(req, timeout=60)  # noqa: S310
        body = json.loads(response.read().decode())
    except (OSError, TimeoutError, json.JSONDecodeError) as e:
        msg = f"Erreur benchmark : {e}"
        raise ValueError(msg) from e

    duration = time.monotonic() - start

    eval_count = body.get("eval_count", 0)
    tokens_per_s = eval_count / duration if duration > 0 else 0.0

    return BenchResult(
        model=model,
        prompt=prompt,
        tokens=eval_count,
        duration_s=round(duration, 2),
        tokens_per_s=round(tokens_per_s, 1),
    )


# ---------------------------------------------------------------------------
# Helpers internes
# ---------------------------------------------------------------------------


def _ollama_base_url(infra: Infrastructure) -> str:
    """Résout l'URL base d'Ollama depuis l'infrastructure."""
    ip, port, _project, _instance = find_ollama_machine(infra)
    if not ip:
        ip = "localhost"
        port = DEFAULT_OLLAMA_PORT
    return f"http://{ip}:{port}"


def _fetch_ollama_ps(base_url: str) -> tuple[bool, list[str]]:
    """Fetch unique vers /api/ps — retourne (reachable, model_names)."""
    try:
        req = Request(f"{base_url}/api/ps", method="GET")  # noqa: S310
        response = urlopen(req, timeout=SERVICE_TIMEOUT)  # noqa: S310
        data = json.loads(response.read().decode())
        models = [m.get("name", "?") for m in data.get("models", [])]
        return True, models
    except (OSError, TimeoutError, json.JSONDecodeError):
        return False, []
