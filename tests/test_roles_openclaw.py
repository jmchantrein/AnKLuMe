"""Tests unitaires — rôle Ansible OpenClaw (Phase 11c)."""

from __future__ import annotations

from unittest.mock import patch

import yaml

from anklume.provisioner import BUILTIN_ROLES_DIR, has_provisionable_machines
from anklume.provisioner.playbook import generate_host_vars, generate_playbook

from .conftest import make_domain, make_infra, make_machine

# ---------------------------------------------------------------------------
# Vérification existence physique du rôle
# ---------------------------------------------------------------------------


class TestOpenclawRoleExists:
    def test_role_directory_exists(self):
        role_dir = BUILTIN_ROLES_DIR / "openclaw_server"
        assert role_dir.is_dir()

    def test_has_tasks(self):
        tasks = BUILTIN_ROLES_DIR / "openclaw_server" / "tasks" / "main.yml"
        assert tasks.is_file()
        content = yaml.safe_load(tasks.read_text())
        assert isinstance(content, list)
        assert len(content) > 0

    def test_has_defaults(self):
        defaults = BUILTIN_ROLES_DIR / "openclaw_server" / "defaults" / "main.yml"
        assert defaults.is_file()
        content = yaml.safe_load(defaults.read_text())
        assert "openclaw_port" in content
        assert content["openclaw_port"] == 8090

    def test_has_handlers(self):
        handlers = BUILTIN_ROLES_DIR / "openclaw_server" / "handlers" / "main.yml"
        assert handlers.is_file()


# ---------------------------------------------------------------------------
# Contenu du rôle
# ---------------------------------------------------------------------------


class TestOpenclawContent:
    def test_installs_dependencies(self):
        tasks = yaml.safe_load(
            (BUILTIN_ROLES_DIR / "openclaw_server" / "tasks" / "main.yml").read_text()
        )
        task_names = [t.get("name", "") for t in tasks]
        assert any("dépendances" in n.lower() or "depend" in n.lower() for n in task_names)

    def test_installs_openclaw(self):
        tasks = yaml.safe_load(
            (BUILTIN_ROLES_DIR / "openclaw_server" / "tasks" / "main.yml").read_text()
        )
        task_names = [t.get("name", "") for t in tasks]
        assert any("openclaw" in n.lower() and "install" in n.lower() for n in task_names)

    def test_creates_systemd_service(self):
        tasks = yaml.safe_load(
            (BUILTIN_ROLES_DIR / "openclaw_server" / "tasks" / "main.yml").read_text()
        )
        task_names = [t.get("name", "") for t in tasks]
        assert any("systemd" in n.lower() for n in task_names)

    def test_creates_data_directory(self):
        tasks = yaml.safe_load(
            (BUILTIN_ROLES_DIR / "openclaw_server" / "tasks" / "main.yml").read_text()
        )
        task_names = [t.get("name", "") for t in tasks]
        assert any("répertoire" in n.lower() or "données" in n.lower() for n in task_names)

    def test_defaults_ollama_host(self):
        defaults = yaml.safe_load(
            (BUILTIN_ROLES_DIR / "openclaw_server" / "defaults" / "main.yml").read_text()
        )
        assert defaults["openclaw_ollama_host"] == "localhost"

    def test_defaults_heartbeat_interval(self):
        defaults = yaml.safe_load(
            (BUILTIN_ROLES_DIR / "openclaw_server" / "defaults" / "main.yml").read_text()
        )
        assert defaults["openclaw_heartbeat_interval"] == "30m"

    def test_defaults_channels_empty(self):
        defaults = yaml.safe_load(
            (BUILTIN_ROLES_DIR / "openclaw_server" / "defaults" / "main.yml").read_text()
        )
        assert defaults["openclaw_channels"] == []


# ---------------------------------------------------------------------------
# Playbook avec rôle OpenClaw
# ---------------------------------------------------------------------------


class TestPlaybookWithOpenclaw:
    def test_openclaw_role_in_playbook(self):
        domain = make_domain(
            "ai-tools",
            machines={
                "assistant": make_machine(
                    "assistant", "ai-tools", roles=["base", "openclaw_server"]
                ),
            },
        )
        infra = make_infra(domains={"ai-tools": domain})
        plays = generate_playbook(infra)

        assert len(plays) == 1
        assert plays[0]["hosts"] == "ai-tools-assistant"
        assert "openclaw_server" in plays[0]["roles"]

    def test_openclaw_detected_as_provisionable(self):
        domain = make_domain(
            "ai-tools",
            machines={
                "assistant": make_machine("assistant", "ai-tools", roles=["openclaw_server"]),
            },
        )
        infra = make_infra(domains={"ai-tools": domain})
        assert has_provisionable_machines(infra)


# ---------------------------------------------------------------------------
# Host vars avec variables OpenClaw
# ---------------------------------------------------------------------------


class TestHostVarsWithOpenclawVars:
    def test_openclaw_vars_in_host_vars(self):
        domain = make_domain(
            "ai-tools",
            machines={
                "assistant": make_machine(
                    "assistant",
                    "ai-tools",
                    roles=["openclaw_server"],
                    vars={
                        "openclaw_channels": ["telegram"],
                        "openclaw_ollama_host": "gpu-server",
                        "openclaw_heartbeat_interval": "15m",
                    },
                ),
            },
        )
        infra = make_infra(domains={"ai-tools": domain})
        host_vars = generate_host_vars(infra)

        assert "ai-tools-assistant" in host_vars
        hv = host_vars["ai-tools-assistant"]
        assert hv["openclaw_channels"] == ["telegram"]
        assert hv["openclaw_ollama_host"] == "gpu-server"

    def test_no_vars_no_host_vars(self):
        domain = make_domain(
            "ai-tools",
            machines={
                "assistant": make_machine("assistant", "ai-tools", roles=["openclaw_server"]),
            },
        )
        infra = make_infra(domains={"ai-tools": domain})
        host_vars = generate_host_vars(infra)

        assert "ai-tools-assistant" not in host_vars


# ---------------------------------------------------------------------------
# Service definition dans engine/ai.py
# ---------------------------------------------------------------------------


class TestOpenclawServiceDef:
    def test_openclaw_role_constant_exists(self):
        from anklume.engine.ai import ROLE_OPENCLAW_SERVER

        assert ROLE_OPENCLAW_SERVER == "openclaw_server"

    def test_openclaw_in_service_defs(self):
        from anklume.engine.ai import _SERVICE_DEFS

        roles = [d["role"] for d in _SERVICE_DEFS]
        assert "openclaw_server" in roles

    def test_openclaw_default_port(self):
        from anklume.engine.ai import _SERVICE_DEFS

        svc = next(d for d in _SERVICE_DEFS if d["role"] == "openclaw_server")
        assert svc["default_port"] == 8090


# ---------------------------------------------------------------------------
# ai status détecte OpenClaw
# ---------------------------------------------------------------------------


class TestAiStatusWithOpenclaw:
    def test_detects_openclaw_service(self):
        from anklume.engine.ai import compute_ai_status
        from anklume.engine.gpu import GpuInfo
        from anklume.engine.models import Domain, GlobalConfig, Infrastructure, Machine

        m = Machine(
            name="assistant",
            full_name="ai-tools-assistant",
            description="Assistant",
            roles=["openclaw_server"],
            ip="10.100.3.5",
        )
        d = Domain(
            name="ai-tools",
            description="IA",
            machines={"assistant": m},
        )
        infra = Infrastructure(
            config=GlobalConfig(),
            domains={"ai-tools": d},
            policies=[],
        )
        gpu = GpuInfo(detected=False, model="", vram_total_mib=0, vram_used_mib=0)

        with (
            patch("anklume.engine.ai.detect_gpu", return_value=gpu),
            patch("anklume.engine.ai._check_service", return_value=("actif", True)),
        ):
            status = compute_ai_status(infra)

        openclaw_svcs = [s for s in status.services if s.name == "openclaw"]
        assert len(openclaw_svcs) == 1
        assert openclaw_svcs[0].reachable is True
