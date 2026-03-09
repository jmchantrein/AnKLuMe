"""Tests unitaires pour engine/llm_ops.py — opérations LLM.

Testé avec GPU et Ollama mockés — vérifie compute_llm_status
et run_llm_bench.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from anklume.engine.gpu import GpuInfo
from anklume.engine.llm_ops import (
    BenchResult,
    LlmMachineStatus,
    LlmStatus,
    compute_llm_status,
    run_llm_bench,
)

from .conftest import make_domain, make_infra, make_machine

_MOD = "anklume.engine.llm_ops"

# ============================================================
# compute_llm_status
# ============================================================


class TestComputeLlmStatus:
    def test_empty_infra(self) -> None:
        infra = make_infra()

        with (
            patch(f"{_MOD}.detect_gpu") as mock_gpu,
            patch(f"{_MOD}._fetch_ollama_ps", return_value=(False, [])),
        ):
            mock_gpu.return_value = GpuInfo(
                detected=False, model="", vram_total_mib=0, vram_used_mib=0
            )
            result = compute_llm_status(infra)

        assert result.gpu.detected is False
        assert result.machines == []
        assert result.ollama_status == "injoignable"

    def test_consumer_machine_detected(self) -> None:
        machine = make_machine(
            "assistant",
            "pro",
            ip="10.100.1.5",
            roles=["base", "openclaw_server"],
        )
        domain = make_domain("pro", machines={"assistant": machine})
        infra = make_infra(domains={"pro": domain})

        with (
            patch(f"{_MOD}.detect_gpu") as mock_gpu,
            patch(f"{_MOD}._fetch_ollama_ps", return_value=(True, ["llama3:8b"])),
        ):
            mock_gpu.return_value = GpuInfo(
                detected=True,
                model="RTX 5000",
                vram_total_mib=24576,
                vram_used_mib=2048,
            )
            result = compute_llm_status(infra)

        assert result.gpu.detected is True
        assert len(result.machines) == 1
        m = result.machines[0]
        assert m.name == "pro-assistant"
        assert m.backend == "local"
        assert result.ollama_status == "actif"
        assert result.ollama_models == ["llama3:8b"]

    def test_non_consumer_machine_excluded(self) -> None:
        machine = make_machine("dev", "pro", roles=["base", "openssh_server"])
        domain = make_domain("pro", machines={"dev": machine})
        infra = make_infra(domains={"pro": domain})

        with (
            patch(f"{_MOD}.detect_gpu") as mock_gpu,
            patch(f"{_MOD}._fetch_ollama_ps", return_value=(False, [])),
        ):
            mock_gpu.return_value = GpuInfo(
                detected=False, model="", vram_total_mib=0, vram_used_mib=0
            )
            result = compute_llm_status(infra)

        assert result.machines == []

    def test_multiple_consumers(self) -> None:
        m1 = make_machine("chat", "pro", ip="10.100.1.3", roles=["base", "lobechat"])
        m2 = make_machine(
            "assistant", "pro", ip="10.100.1.5", roles=["base", "openclaw_server"]
        )
        domain = make_domain("pro", machines={"chat": m1, "assistant": m2})
        infra = make_infra(domains={"pro": domain})

        with (
            patch(f"{_MOD}.detect_gpu") as mock_gpu,
            patch(f"{_MOD}._fetch_ollama_ps", return_value=(True, [])),
        ):
            mock_gpu.return_value = GpuInfo(
                detected=False, model="", vram_total_mib=0, vram_used_mib=0
            )
            result = compute_llm_status(infra)

        assert len(result.machines) == 2
        names = {m.name for m in result.machines}
        assert "pro-chat" in names
        assert "pro-assistant" in names

    def test_invalid_config_handled(self) -> None:
        """Machine avec config LLM invalide → backend 'erreur'."""
        machine = make_machine(
            "assistant",
            "pro",
            ip="10.100.1.5",
            roles=["base", "openclaw_server"],
            vars={"llm_backend": "invalid_backend"},
        )
        domain = make_domain("pro", machines={"assistant": machine})
        infra = make_infra(domains={"pro": domain})

        with (
            patch(f"{_MOD}.detect_gpu") as mock_gpu,
            patch(f"{_MOD}._fetch_ollama_ps", return_value=(False, [])),
        ):
            mock_gpu.return_value = GpuInfo(
                detected=False, model="", vram_total_mib=0, vram_used_mib=0
            )
            result = compute_llm_status(infra)

        assert len(result.machines) == 1
        assert result.machines[0].backend == "erreur"


# ============================================================
# run_llm_bench
# ============================================================


class TestRunLlmBench:
    def test_ollama_unreachable(self) -> None:
        infra = make_infra()

        with (
            patch(f"{_MOD}._ollama_base_url", return_value="http://localhost:11434"),
            patch(f"{_MOD}._fetch_ollama_ps", return_value=(False, [])),
        ):
            with pytest.raises(ValueError, match="injoignable"):
                run_llm_bench(infra)

    def test_no_model_loaded(self) -> None:
        infra = make_infra()

        with (
            patch(f"{_MOD}._ollama_base_url", return_value="http://localhost:11434"),
            patch(f"{_MOD}._fetch_ollama_ps", return_value=(True, [])),
        ):
            with pytest.raises(ValueError, match="Aucun modèle"):
                run_llm_bench(infra)

    def test_bench_success(self) -> None:
        infra = make_infra()

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(
            {
                "eval_count": 42,
            }
        ).encode()
        mock_response.status = 200

        with (
            patch(
                f"{_MOD}._ollama_base_url",
                return_value="http://10.100.3.1:11434",
            ),
            patch(f"{_MOD}._fetch_ollama_ps", return_value=(True, ["llama3:8b"])),
            patch(f"{_MOD}.urlopen", return_value=mock_response),
        ):
            result = run_llm_bench(infra, model="llama3:8b", prompt="test")

        assert result.model == "llama3:8b"
        assert result.prompt == "test"
        assert result.tokens == 42
        assert result.duration_s >= 0
        assert result.tokens_per_s >= 0

    def test_bench_with_explicit_model(self) -> None:
        infra = make_infra()

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(
            {
                "eval_count": 100,
            }
        ).encode()

        with (
            patch(
                f"{_MOD}._ollama_base_url",
                return_value="http://localhost:11434",
            ),
            patch(f"{_MOD}._fetch_ollama_ps", return_value=(True, ["custom-model"])),
            patch(f"{_MOD}.urlopen", return_value=mock_response),
        ):
            result = run_llm_bench(infra, model="custom-model")

        assert result.model == "custom-model"
        assert result.tokens == 100


# ============================================================
# Dataclasses
# ============================================================


class TestDataclasses:
    def test_llm_machine_status(self) -> None:
        m = LlmMachineStatus(
            name="pro-assistant",
            backend="openai",
            sanitized=True,
            url="http://10.100.1.5:8089",
        )
        assert m.sanitized is True

    def test_llm_status_defaults(self) -> None:
        gpu = GpuInfo(detected=False, model="", vram_total_mib=0, vram_used_mib=0)
        s = LlmStatus(gpu=gpu)
        assert s.machines == []
        assert s.ollama_status == "injoignable"
        assert s.ollama_models == []

    def test_bench_result(self) -> None:
        r = BenchResult(
            model="llama3",
            prompt="hello",
            tokens=50,
            duration_s=1.5,
            tokens_per_s=33.3,
        )
        assert r.tokens_per_s == 33.3
