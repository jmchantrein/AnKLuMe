"""Tests GPU — benchmark Ollama dans un conteneur LXC avec GPU passthrough.

Crée un conteneur avec GPU, installe Ollama, exécute un benchmark
d'inférence LLM et vérifie les performances minimales.

Prérequis : GPU NVIDIA disponible, Incus configuré.
Skippé automatiquement si aucun GPU détecté.
"""

from __future__ import annotations

import json
import subprocess
import time

import pytest

from .incus_helpers import cleanup_project, incus_run

GPU_PROJECT = "e2e-gpu"
GPU_INSTANCE = "e2e-gpu-bench"
BENCH_MODEL = "qwen2:0.5b"
MIN_TOKENS_PER_SEC = 10  # seuil minimum raisonnable


def _has_gpu() -> bool:
    """Vérifie si un GPU NVIDIA est disponible sur l'hôte."""
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _incus_exec(args: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    """Exécute une commande dans le conteneur GPU."""
    return subprocess.run(
        [
            "incus",
            "exec",
            GPU_INSTANCE,
            "--project",
            GPU_PROJECT,
            "--",
            *args,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _flush_vram() -> None:
    """Décharger les modèles Ollama pour libérer la VRAM."""
    # Arrêter llama-server si actif
    subprocess.run(
        [
            "incus",
            "exec",
            "gpu-server",
            "--project",
            "ai-tools",
            "--",
            "systemctl",
            "stop",
            "llama-server",
        ],
        capture_output=True,
    )

    # Décharger tous les modèles Ollama
    try:
        result = subprocess.run(
            ["curl", "-s", "http://10.100.3.1:11434/api/ps"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            for model in data.get("models", []):
                subprocess.run(
                    [
                        "curl",
                        "-s",
                        "http://10.100.3.1:11434/api/generate",
                        "-d",
                        json.dumps({"model": model["name"], "keep_alive": 0}),
                    ],
                    capture_output=True,
                    timeout=10,
                )
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        pass  # pas d'Ollama actif, rien à décharger


@pytest.fixture()
def gpu_env():
    """Fixture pour le test GPU — cleanup + flush VRAM."""
    if not _has_gpu():
        pytest.skip("Aucun GPU NVIDIA détecté")

    _flush_vram()
    cleanup_project(GPU_PROJECT)

    yield

    cleanup_project(GPU_PROJECT)


class TestGPUBenchmark:
    """Benchmark Ollama dans un conteneur LXC avec GPU passthrough."""

    @pytest.mark.slow
    @pytest.mark.gpu
    def test_ollama_benchmark(self, gpu_env):
        """Crée un conteneur GPU, installe Ollama, benchmark d'inférence."""
        # 1. Créer le projet
        incus_run(
            [
                "project",
                "create",
                GPU_PROJECT,
                "-c",
                "features.images=false",
                "-c",
                "features.profiles=false",
            ]
        )

        # 2. Créer le conteneur avec NVIDIA runtime + GPU device
        incus_run(
            [
                "launch",
                "images:debian/13",
                GPU_INSTANCE,
                "--project",
                GPU_PROJECT,
                "-c",
                "nvidia.runtime=true",
                "-c",
                "nvidia.driver.capabilities=compute,utility",
            ]
        )

        # 3. Ajouter le GPU physique
        incus_run(
            [
                "config",
                "device",
                "add",
                GPU_INSTANCE,
                "gpu",
                "gpu",
                "gputype=physical",
                "--project",
                GPU_PROJECT,
            ]
        )

        # 4. Attendre que le conteneur soit prêt
        time.sleep(5)

        # 5. Vérifier que le GPU est visible dans le conteneur
        result = _incus_exec(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"])
        assert result.returncode == 0, f"GPU non visible dans le conteneur :\n{result.stderr}"
        gpu_name = result.stdout.strip()
        print(f"GPU détecté dans le conteneur : {gpu_name}")

        # 6. Installer curl + Ollama
        result = _incus_exec(
            [
                "bash",
                "-c",
                "apt-get update -qq > /dev/null 2>&1 && "
                "apt-get install -y -qq curl zstd > /dev/null 2>&1 && "
                "curl -fsSL https://ollama.com/install.sh | sh",
            ],
            timeout=180,
        )
        assert result.returncode == 0, f"Installation Ollama échouée :\n{result.stderr}"

        # 7. Démarrer Ollama en arrière-plan et attendre
        _incus_exec(
            ["bash", "-c", "ollama serve > /var/log/ollama.log 2>&1 &"],
        )
        for _ in range(60):
            check = _incus_exec(
                ["curl", "-sf", "http://localhost:11434/api/tags"],
                timeout=5,
            )
            if check.returncode == 0:
                break
            time.sleep(1)
        else:
            # Debug : récupérer les logs Ollama
            logs = _incus_exec(["cat", "/var/log/ollama.log"], timeout=5)
            pytest.fail(
                f"Ollama n'a pas démarré dans les 60s.\nLogs :\n{logs.stdout}\n{logs.stderr}"
            )

        # 8. Tirer le modèle de benchmark
        result = _incus_exec(
            ["ollama", "pull", BENCH_MODEL],
            timeout=300,
        )
        assert result.returncode == 0, f"Pull {BENCH_MODEL} échoué :\n{result.stderr}"

        # 9. Benchmark : générer du texte via l'API
        prompt = "Count from 1 to 50, one number per line."
        payload = json.dumps(
            {
                "model": BENCH_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": 128},
            }
        )

        result = _incus_exec(
            [
                "curl",
                "-s",
                "http://localhost:11434/api/generate",
                "-d",
                payload,
            ],
            timeout=120,
        )
        assert result.returncode == 0, f"Benchmark échoué :\n{result.stderr}"

        response = json.loads(result.stdout)
        eval_count = response.get("eval_count", 0)
        eval_duration_ns = response.get("eval_duration", 1)
        tokens_per_sec = eval_count / (eval_duration_ns / 1e9)

        print(f"\n{'=' * 50}")
        print(f"  Benchmark Ollama — {BENCH_MODEL}")
        print(f"  GPU : {gpu_name}")
        print(f"  Tokens générés : {eval_count}")
        print(f"  Vitesse : {tokens_per_sec:.1f} tok/s")
        print(f"{'=' * 50}")

        assert tokens_per_sec > MIN_TOKENS_PER_SEC, (
            f"Performance insuffisante : {tokens_per_sec:.1f} tok/s "
            f"(minimum : {MIN_TOKENS_PER_SEC} tok/s)"
        )
