"""Tests unitaires — Gestion VRAM et accès exclusif (Phase 10e)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from anklume.engine.ai import (
    AiAccessState,
    FlushResult,
    flush_vram,
    read_ai_access,
    switch_ai_access,
    write_ai_access,
)
from anklume.engine.gpu import GpuInfo
from anklume.engine.models import (
    Domain,
    GlobalConfig,
    Infrastructure,
    Machine,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _gpu_present(vram_used: int = 4096) -> GpuInfo:
    return GpuInfo(
        detected=True, model="RTX PRO 5000",
        vram_total_mib=24576, vram_used_mib=vram_used,
    )


def _gpu_absent() -> GpuInfo:
    return GpuInfo(detected=False, model="", vram_total_mib=0, vram_used_mib=0)


def _ai_infra(*, ai_access_policy: str = "exclusive") -> Infrastructure:
    """Infrastructure avec domaine ai-tools."""
    m = Machine(
        name="gpu-server",
        full_name="ai-tools-gpu-server",
        description="Serveur GPU",
        gpu=True,
        roles=["base", "ollama_server", "stt_server"],
        ip="10.100.3.1",
        vars={"ollama_port": 11434, "stt_port": 8000},
    )
    d = Domain(
        name="ai-tools",
        description="Services IA",
        trust_level="trusted",
        machines={"gpu-server": m},
        subnet="10.100.3.0/24",
        gateway="10.100.3.254",
    )
    pro = Domain(
        name="pro",
        description="Professionnel",
        machines={},
    )
    config = GlobalConfig(ai_access_policy=ai_access_policy)
    return Infrastructure(
        config=config,
        domains={"ai-tools": d, "pro": pro},
        policies=[],
    )


# ---------------------------------------------------------------------------
# FlushResult
# ---------------------------------------------------------------------------


class TestFlushResult:
    def test_fields(self):
        r = FlushResult(
            models_unloaded=["qwen2:0.5b"],
            llama_server_stopped=True,
            vram_before_mib=4096,
            vram_after_mib=512,
        )
        assert r.models_unloaded == ["qwen2:0.5b"]
        assert r.llama_server_stopped is True
        assert r.vram_before_mib == 4096
        assert r.vram_after_mib == 512

    def test_empty_flush(self):
        r = FlushResult(
            models_unloaded=[],
            llama_server_stopped=False,
            vram_before_mib=0,
            vram_after_mib=0,
        )
        assert r.models_unloaded == []
        assert r.llama_server_stopped is False


# ---------------------------------------------------------------------------
# flush_vram
# ---------------------------------------------------------------------------


class TestFlushVram:
    def test_unloads_models(self):
        infra = _ai_infra()
        ps_response = MagicMock()
        ps_response.status = 200
        ps_response.read.return_value = json.dumps({
            "models": [{"name": "qwen2:0.5b"}, {"name": "llama3:8b"}],
        }).encode()

        generate_response = MagicMock()
        generate_response.status = 200
        generate_response.read.return_value = b"{}"

        with (
            patch("anklume.engine.ai.detect_gpu", return_value=_gpu_present()),
            patch("anklume.engine.ai.urlopen") as mock_urlopen,
            patch("anklume.engine.ai._stop_llama_server", return_value=False),
        ):
            mock_urlopen.side_effect = [ps_response, generate_response, generate_response]
            result = flush_vram(infra)

        assert "qwen2:0.5b" in result.models_unloaded
        assert "llama3:8b" in result.models_unloaded
        assert len(result.models_unloaded) == 2

    def test_no_models_loaded(self):
        infra = _ai_infra()
        ps_response = MagicMock()
        ps_response.status = 200
        ps_response.read.return_value = json.dumps({"models": []}).encode()

        with (
            patch("anklume.engine.ai.detect_gpu", return_value=_gpu_present(vram_used=512)),
            patch("anklume.engine.ai.urlopen", return_value=ps_response),
            patch("anklume.engine.ai._stop_llama_server", return_value=False),
        ):
            result = flush_vram(infra)

        assert result.models_unloaded == []

    def test_ollama_unreachable(self):
        infra = _ai_infra()

        with (
            patch("anklume.engine.ai.detect_gpu", return_value=_gpu_present()),
            patch("anklume.engine.ai.urlopen", side_effect=OSError("refused")),
            patch("anklume.engine.ai._stop_llama_server", return_value=False),
        ):
            result = flush_vram(infra)

        assert result.models_unloaded == []

    def test_llama_server_stopped(self):
        infra = _ai_infra()
        ps_response = MagicMock()
        ps_response.status = 200
        ps_response.read.return_value = json.dumps({"models": []}).encode()

        with (
            patch("anklume.engine.ai.detect_gpu", return_value=_gpu_present()),
            patch("anklume.engine.ai.urlopen", return_value=ps_response),
            patch("anklume.engine.ai._stop_llama_server", return_value=True),
        ):
            result = flush_vram(infra)

        assert result.llama_server_stopped is True

    def test_no_gpu_detected(self):
        infra = _ai_infra()

        with patch("anklume.engine.ai.detect_gpu", return_value=_gpu_absent()):
            result = flush_vram(infra)

        assert result.models_unloaded == []
        assert result.vram_before_mib == 0

    def test_no_ai_domain(self):
        infra = Infrastructure(
            config=GlobalConfig(),
            domains={},
            policies=[],
        )

        with patch("anklume.engine.ai.detect_gpu", return_value=_gpu_present()):
            result = flush_vram(infra)

        assert result.models_unloaded == []

    def test_vram_before_after(self):
        infra = _ai_infra()
        ps_response = MagicMock()
        ps_response.status = 200
        ps_response.read.return_value = json.dumps({"models": []}).encode()

        gpu_before = _gpu_present(vram_used=8000)
        gpu_after = _gpu_present(vram_used=512)

        with (
            patch("anklume.engine.ai.detect_gpu", side_effect=[gpu_before, gpu_after]),
            patch("anklume.engine.ai.urlopen", return_value=ps_response),
            patch("anklume.engine.ai._stop_llama_server", return_value=False),
        ):
            result = flush_vram(infra)

        assert result.vram_before_mib == 8000
        assert result.vram_after_mib == 512


# ---------------------------------------------------------------------------
# AiAccessState
# ---------------------------------------------------------------------------


class TestAiAccessState:
    def test_fields(self):
        state = AiAccessState(
            domain="ai-tools",
            timestamp="2026-03-08T14:30:00",
            previous=None,
        )
        assert state.domain == "ai-tools"
        assert state.previous is None

    def test_with_previous(self):
        state = AiAccessState(
            domain="pro",
            timestamp="2026-03-08T15:00:00",
            previous="ai-tools",
        )
        assert state.previous == "ai-tools"


# ---------------------------------------------------------------------------
# read_ai_access / write_ai_access
# ---------------------------------------------------------------------------


class TestReadAiAccess:
    def test_no_file(self, tmp_path):
        state = read_ai_access(state_path=tmp_path / "ai-access.json")
        assert state.domain is None

    def test_valid_file(self, tmp_path):
        state_file = tmp_path / "ai-access.json"
        state_file.write_text(json.dumps({
            "domain": "ai-tools",
            "timestamp": "2026-03-08T14:30:00",
            "previous": None,
        }))
        state = read_ai_access(state_path=state_file)
        assert state.domain == "ai-tools"
        assert state.timestamp == "2026-03-08T14:30:00"

    def test_corrupted_file(self, tmp_path):
        state_file = tmp_path / "ai-access.json"
        state_file.write_text("not json")
        state = read_ai_access(state_path=state_file)
        assert state.domain is None


class TestWriteAiAccess:
    def test_creates_file(self, tmp_path):
        state_file = tmp_path / "ai-access.json"
        state = write_ai_access("pro", state_path=state_file)
        assert state.domain == "pro"
        assert state_file.exists()
        data = json.loads(state_file.read_text())
        assert data["domain"] == "pro"

    def test_overwrites_previous(self, tmp_path):
        state_file = tmp_path / "ai-access.json"
        write_ai_access("ai-tools", state_path=state_file)
        state = write_ai_access("pro", state_path=state_file)
        assert state.domain == "pro"
        assert state.previous == "ai-tools"

    def test_creates_parent_directory(self, tmp_path):
        state_file = tmp_path / "subdir" / "ai-access.json"
        state = write_ai_access("ai-tools", state_path=state_file)
        assert state.domain == "ai-tools"
        assert state_file.exists()

    def test_timestamp_present(self, tmp_path):
        state_file = tmp_path / "ai-access.json"
        state = write_ai_access("ai-tools", state_path=state_file)
        assert state.timestamp != ""
        assert "T" in state.timestamp


# ---------------------------------------------------------------------------
# switch_ai_access
# ---------------------------------------------------------------------------


class TestSwitchAiAccess:
    def test_switch_to_valid_domain(self, tmp_path):
        infra = _ai_infra()
        state_file = tmp_path / "ai-access.json"
        ps_response = MagicMock()
        ps_response.status = 200
        ps_response.read.return_value = json.dumps({"models": []}).encode()

        with (
            patch("anklume.engine.ai.detect_gpu", return_value=_gpu_present(vram_used=512)),
            patch("anklume.engine.ai.urlopen", return_value=ps_response),
            patch("anklume.engine.ai._stop_llama_server", return_value=False),
            patch("anklume.engine.ai.DEFAULT_STATE_PATH", state_file),
        ):
            state = switch_ai_access(infra, "pro")

        assert state.domain == "pro"

    def test_switch_nonexistent_domain_raises(self):
        infra = _ai_infra()

        with pytest.raises(ValueError, match="inexistant"):
            switch_ai_access(infra, "fantome")

    def test_switch_disabled_domain_raises(self):
        infra = _ai_infra()
        infra.domains["pro"].enabled = False

        with pytest.raises(ValueError, match="désactivé"):
            switch_ai_access(infra, "pro")

    def test_switch_open_policy_raises(self):
        infra = _ai_infra(ai_access_policy="open")

        with pytest.raises(ValueError, match="open"):
            switch_ai_access(infra, "pro")

    def test_switch_records_previous(self, tmp_path):
        infra = _ai_infra()
        state_file = tmp_path / "ai-access.json"
        write_ai_access("ai-tools", state_path=state_file)

        ps_response = MagicMock()
        ps_response.status = 200
        ps_response.read.return_value = json.dumps({"models": []}).encode()

        with (
            patch("anklume.engine.ai.detect_gpu", return_value=_gpu_present(vram_used=512)),
            patch("anklume.engine.ai.urlopen", return_value=ps_response),
            patch("anklume.engine.ai._stop_llama_server", return_value=False),
            patch("anklume.engine.ai.DEFAULT_STATE_PATH", state_file),
        ):
            state = switch_ai_access(infra, "pro")

        assert state.previous == "ai-tools"

    def test_switch_calls_flush(self, tmp_path):
        infra = _ai_infra()
        state_file = tmp_path / "ai-access.json"

        with (
            patch("anklume.engine.ai.flush_vram") as mock_flush,
            patch("anklume.engine.ai.DEFAULT_STATE_PATH", state_file),
        ):
            mock_flush.return_value = FlushResult(
                models_unloaded=[], llama_server_stopped=False,
                vram_before_mib=0, vram_after_mib=0,
            )
            switch_ai_access(infra, "pro")

        mock_flush.assert_called_once_with(infra)


# ---------------------------------------------------------------------------
# ai_access_policy dans GlobalConfig
# ---------------------------------------------------------------------------


class TestAiAccessPolicy:
    def test_default_exclusive(self):
        config = GlobalConfig()
        assert config.ai_access_policy == "exclusive"

    def test_open_policy(self):
        config = GlobalConfig(ai_access_policy="open")
        assert config.ai_access_policy == "open"


# ---------------------------------------------------------------------------
# Parser ai_access_policy
# ---------------------------------------------------------------------------


class TestParserAiAccessPolicy:
    def test_parse_from_yaml(self, tmp_path):
        from anklume.engine.parser import parse_project

        (tmp_path / "anklume.yml").write_text(
            "schema_version: 1\nai_access_policy: open\n"
        )
        (tmp_path / "domains").mkdir()
        infra = parse_project(tmp_path)
        assert infra.config.ai_access_policy == "open"

    def test_parse_absent_defaults_exclusive(self, tmp_path):
        from anklume.engine.parser import parse_project

        (tmp_path / "anklume.yml").write_text("schema_version: 1\n")
        (tmp_path / "domains").mkdir()
        infra = parse_project(tmp_path)
        assert infra.config.ai_access_policy == "exclusive"


# ---------------------------------------------------------------------------
# _stop_llama_server (unit)
# ---------------------------------------------------------------------------


class TestStopLlamaServer:
    def test_stops_running_server(self):
        from anklume.engine.ai import _stop_llama_server

        health_response = MagicMock()
        health_response.status = 200

        with (
            patch("anklume.engine.ai.urlopen", return_value=health_response),
            patch("anklume.engine.ai._incus_exec_stop_llama") as mock_exec,
        ):
            mock_exec.return_value = True
            result = _stop_llama_server(
                "10.100.3.1", 8081, "ai-tools", "ai-tools-gpu-server",
            )

        assert result is True

    def test_server_not_running(self):
        from anklume.engine.ai import _stop_llama_server

        with patch("anklume.engine.ai.urlopen", side_effect=OSError):
            result = _stop_llama_server(
                "10.100.3.1", 8081, "ai-tools", "ai-tools-gpu-server",
            )

        assert result is False
