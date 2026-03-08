"""Tests unitaires — engine/ai.py + CLI ai + init ai-tools (Phase 10c)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import yaml

from anklume.cli._init import run_init
from anklume.engine.ai import AiServiceStatus, AiStatus, compute_ai_status
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


def _gpu_present() -> GpuInfo:
    return GpuInfo(detected=True, model="RTX PRO 5000", vram_total_mib=24576, vram_used_mib=512)


def _gpu_absent() -> GpuInfo:
    return GpuInfo(detected=False, model="", vram_total_mib=0, vram_used_mib=0)


def _ai_infra(*, gpu_server_ip: str = "10.100.3.1") -> Infrastructure:
    """Infrastructure avec un domaine ai-tools et gpu-server."""
    m = Machine(
        name="gpu-server",
        full_name="ai-tools-gpu-server",
        description="Serveur GPU",
        gpu=True,
        roles=["base", "ollama_server", "stt_server"],
        ip=gpu_server_ip,
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
    return Infrastructure(
        config=GlobalConfig(),
        domains={"ai-tools": d},
        policies=[],
    )


def _ai_infra_no_vars() -> Infrastructure:
    """Infrastructure ai-tools sans vars (ports par défaut)."""
    m = Machine(
        name="gpu-server",
        full_name="ai-tools-gpu-server",
        description="Serveur GPU",
        gpu=True,
        roles=["base", "ollama_server", "stt_server"],
        ip="10.100.3.1",
    )
    d = Domain(
        name="ai-tools",
        description="Services IA",
        machines={"gpu-server": m},
        subnet="10.100.3.0/24",
        gateway="10.100.3.254",
    )
    return Infrastructure(
        config=GlobalConfig(),
        domains={"ai-tools": d},
        policies=[],
    )


# ---------------------------------------------------------------------------
# AiServiceStatus
# ---------------------------------------------------------------------------


class TestAiServiceStatus:
    def test_reachable(self):
        s = AiServiceStatus(
            name="ollama",
            reachable=True,
            url="http://10.100.3.1:11434",
            detail="ok",
        )
        assert s.reachable is True
        assert s.name == "ollama"

    def test_unreachable(self):
        s = AiServiceStatus(name="stt", reachable=False, url="http://10.100.3.1:8000", detail="")
        assert s.reachable is False


class TestAiStatus:
    def test_fields(self):
        status = AiStatus(gpu=_gpu_present(), services=[])
        assert status.gpu.detected is True
        assert status.services == []


# ---------------------------------------------------------------------------
# compute_ai_status
# ---------------------------------------------------------------------------


class TestComputeAiStatus:
    def test_no_ai_domain(self):
        """Sans domaine ai-tools, retourne GPU info + services vides."""
        infra = Infrastructure(
            config=GlobalConfig(),
            domains={},
            policies=[],
        )
        with patch("anklume.engine.ai.detect_gpu", return_value=_gpu_absent()):
            status = compute_ai_status(infra)
        assert status.gpu.detected is False
        assert status.services == []

    def test_gpu_detected(self):
        infra = _ai_infra()
        with (
            patch("anklume.engine.ai.detect_gpu", return_value=_gpu_present()),
            patch("anklume.engine.ai._check_service", return_value=("", False)),
        ):
            status = compute_ai_status(infra)
        assert status.gpu.detected is True
        assert status.gpu.model == "RTX PRO 5000"

    def test_ollama_reachable(self):
        infra = _ai_infra()
        with (
            patch("anklume.engine.ai.detect_gpu", return_value=_gpu_present()),
            patch("anklume.engine.ai._check_service") as mock_check,
        ):
            mock_check.side_effect = lambda url, _: (
                ("qwen2:0.5b chargé", True) if "11434" in url else ("", False)
            )
            status = compute_ai_status(infra)

        ollama = next(s for s in status.services if s.name == "ollama")
        assert ollama.reachable is True
        assert "qwen2" in ollama.detail

    def test_stt_reachable(self):
        infra = _ai_infra()
        with (
            patch("anklume.engine.ai.detect_gpu", return_value=_gpu_present()),
            patch("anklume.engine.ai._check_service") as mock_check,
        ):
            mock_check.side_effect = lambda url, _: (
                ("actif", True) if "8000" in url else ("", False)
            )
            status = compute_ai_status(infra)

        stt = next(s for s in status.services if s.name == "stt")
        assert stt.reachable is True

    def test_services_unreachable(self):
        infra = _ai_infra()
        with (
            patch("anklume.engine.ai.detect_gpu", return_value=_gpu_present()),
            patch("anklume.engine.ai._check_service", return_value=("", False)),
        ):
            status = compute_ai_status(infra)

        assert len(status.services) == 2
        assert all(not s.reachable for s in status.services)

    def test_default_ports_used_when_no_vars(self):
        infra = _ai_infra_no_vars()
        with (
            patch("anklume.engine.ai.detect_gpu", return_value=_gpu_present()),
            patch("anklume.engine.ai._check_service", return_value=("", False)) as mock_check,
        ):
            compute_ai_status(infra)

        urls = [call[0][0] for call in mock_check.call_args_list]
        assert any("11434" in u for u in urls)
        assert any("8000" in u for u in urls)

    def test_disabled_ai_domain_no_services(self):
        infra = _ai_infra()
        infra.domains["ai-tools"].enabled = False
        with patch("anklume.engine.ai.detect_gpu", return_value=_gpu_present()):
            status = compute_ai_status(infra)
        assert status.services == []

    def test_custom_ports(self):
        m = Machine(
            name="gpu-server",
            full_name="ai-tools-gpu-server",
            description="GPU",
            gpu=True,
            roles=["ollama_server", "stt_server"],
            ip="10.100.3.1",
            vars={"ollama_port": 9999, "stt_port": 7777},
        )
        d = Domain(
            name="ai-tools",
            description="IA",
            machines={"gpu-server": m},
        )
        infra = Infrastructure(
            config=GlobalConfig(),
            domains={"ai-tools": d},
            policies=[],
        )
        with (
            patch("anklume.engine.ai.detect_gpu", return_value=_gpu_present()),
            patch("anklume.engine.ai._check_service", return_value=("", False)) as mock_check,
        ):
            compute_ai_status(infra)

        urls = [call[0][0] for call in mock_check.call_args_list]
        assert any("9999" in u for u in urls)
        assert any("7777" in u for u in urls)


# ---------------------------------------------------------------------------
# _check_service (unit)
# ---------------------------------------------------------------------------


class TestCheckService:
    def test_ollama_reachable(self):
        from anklume.engine.ai import _check_service

        response = MagicMock()
        response.status = 200
        response.read.return_value = json.dumps(
            {"models": [{"name": "qwen2:0.5b", "size": 3400000000}]}
        ).encode()

        with patch("anklume.engine.ai.urlopen", return_value=response):
            detail, ok = _check_service("http://10.100.3.1:11434/api/ps", "ollama")
        assert ok is True
        assert "qwen2" in detail

    def test_stt_reachable(self):
        from anklume.engine.ai import _check_service

        response = MagicMock()
        response.status = 200
        response.read.return_value = b'{"data": [{"id": "whisper-base"}]}'

        with patch("anklume.engine.ai.urlopen", return_value=response):
            _detail, ok = _check_service("http://10.100.3.1:8000/v1/models", "stt")
        assert ok is True

    def test_service_unreachable(self):
        from anklume.engine.ai import _check_service

        with patch("anklume.engine.ai.urlopen", side_effect=OSError("Connection refused")):
            _detail, ok = _check_service("http://10.100.3.1:11434/api/ps", "ollama")
        assert ok is False

    def test_service_timeout(self):
        from anklume.engine.ai import _check_service

        with patch("anklume.engine.ai.urlopen", side_effect=TimeoutError):
            _detail, ok = _check_service("http://10.100.3.1:11434/api/ps", "ollama")
        assert ok is False


# ---------------------------------------------------------------------------
# anklume init — domaine ai-tools
# ---------------------------------------------------------------------------


class TestInitAiTools:
    def test_ai_tools_domain_created(self, tmp_path):
        project = tmp_path / "test"
        run_init(str(project))
        assert (project / "domains" / "ai-tools.yml").exists()

    def test_ai_tools_domain_disabled_by_default(self, tmp_path):
        project = tmp_path / "test"
        run_init(str(project))
        content = yaml.safe_load((project / "domains" / "ai-tools.yml").read_text())
        assert content["enabled"] is False

    def test_ai_tools_has_gpu_server(self, tmp_path):
        project = tmp_path / "test"
        run_init(str(project))
        content = yaml.safe_load((project / "domains" / "ai-tools.yml").read_text())
        assert "gpu-server" in content["machines"]
        assert content["machines"]["gpu-server"]["gpu"] is True

    def test_ai_tools_has_ia_roles(self, tmp_path):
        project = tmp_path / "test"
        run_init(str(project))
        content = yaml.safe_load((project / "domains" / "ai-tools.yml").read_text())
        roles = content["machines"]["gpu-server"]["roles"]
        assert "ollama_server" in roles
        assert "stt_server" in roles

    def test_ai_tools_english(self, tmp_path):
        project = tmp_path / "test"
        run_init(str(project), lang="en")
        assert (project / "domains" / "ai-tools.yml").exists()

    def test_policies_mention_ai_tools(self, tmp_path):
        project = tmp_path / "test"
        run_init(str(project))
        content = (project / "policies.yml").read_text()
        assert "ai-tools" in content
        assert "11434" in content

    def test_init_still_parsable(self, tmp_path):
        """Le projet avec ai-tools est parsable (domaine désactivé)."""
        from anklume.engine.parser import parse_project

        project = tmp_path / "test"
        run_init(str(project))
        infra = parse_project(project)
        assert "ai-tools" in infra.domains
        assert infra.domains["ai-tools"].enabled is False
