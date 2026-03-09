"""Tests unitaires — rôle Ansible OpenClaw modernisé (Phase 16)."""

from __future__ import annotations

from unittest.mock import patch

from anklume.provisioner import BUILTIN_ROLES_DIR, has_provisionable_machines
from anklume.provisioner.playbook import generate_host_vars, generate_playbook

from .conftest import (
    make_domain,
    make_infra,
    make_machine,
    role_defaults,
    role_task_names,
    role_tasks,
)

# ---------------------------------------------------------------------------
# Vérification existence physique du rôle
# ---------------------------------------------------------------------------


class TestOpenclawRoleExists:
    def test_role_directory_exists(self):
        assert (BUILTIN_ROLES_DIR / "openclaw_server").is_dir()

    def test_has_tasks(self):
        tasks = role_tasks("openclaw_server")
        assert isinstance(tasks, list)
        assert len(tasks) > 0

    def test_has_defaults(self):
        defaults = role_defaults("openclaw_server")
        assert "openclaw_port" in defaults
        assert defaults["openclaw_port"] == 8090

    def test_has_handlers(self):
        assert (BUILTIN_ROLES_DIR / "openclaw_server" / "handlers" / "main.yml").is_file()

    def test_has_templates_dir(self):
        assert (BUILTIN_ROLES_DIR / "openclaw_server" / "templates").is_dir()

    def test_has_llm_conf_template(self):
        assert (BUILTIN_ROLES_DIR / "openclaw_server" / "templates" / "llm.conf.j2").is_file()


# ---------------------------------------------------------------------------
# Contenu des tâches — installation npm + daemon natif
# ---------------------------------------------------------------------------


class TestOpenclawTasks:
    def test_creates_user(self):
        names = role_task_names("openclaw_server")
        assert any("utilisateur" in n.lower() or "user" in n.lower() for n in names)

    def test_installs_nodejs(self):
        names = role_task_names("openclaw_server")
        assert any("node" in n.lower() for n in names)

    def test_installs_openclaw_npm(self):
        tasks = role_tasks("openclaw_server")
        found = any("openclaw" in str(t).lower() and "npm" in str(t).lower() for t in tasks)
        assert found, "Tâche d'installation npm OpenClaw introuvable"

    def test_runs_onboard(self):
        tasks = role_tasks("openclaw_server")
        found = any("onboard" in str(t).lower() for t in tasks)
        assert found, "Tâche openclaw onboard introuvable"

    def test_deploys_systemd_override(self):
        names = role_task_names("openclaw_server")
        assert any("override" in n.lower() or "llm.conf" in n.lower() for n in names)

    def test_starts_service(self):
        names = role_task_names("openclaw_server")
        assert any(
            "démarrer" in n.lower() or "activer" in n.lower() or "start" in n.lower() for n in names
        )

    def test_health_check(self):
        names = role_task_names("openclaw_server")
        assert any("prêt" in n.lower() or "health" in n.lower() for n in names)


# ---------------------------------------------------------------------------
# Defaults — variables modernisées
# ---------------------------------------------------------------------------


class TestOpenclawDefaults:
    def test_version_default(self):
        assert role_defaults("openclaw_server")["openclaw_version"] == "latest"

    def test_user_default(self):
        assert role_defaults("openclaw_server")["openclaw_user"] == "openclaw"

    def test_channels_default(self):
        assert role_defaults("openclaw_server")["openclaw_channels"] == []

    def test_llm_provider_default(self):
        assert role_defaults("openclaw_server")["openclaw_llm_provider"] == "ollama"

    def test_port_default(self):
        assert role_defaults("openclaw_server")["openclaw_port"] == 8090

    def test_llm_model_default(self):
        assert role_defaults("openclaw_server")["openclaw_llm_model"] == ""


# ---------------------------------------------------------------------------
# Template llm.conf.j2
# ---------------------------------------------------------------------------


class TestOpenclawTemplate:
    _tmpl: str | None = None

    @classmethod
    def _read_template(cls) -> str:
        if cls._tmpl is None:
            cls._tmpl = (
                BUILTIN_ROLES_DIR / "openclaw_server" / "templates" / "llm.conf.j2"
            ).read_text()
        return cls._tmpl

    def test_llm_conf_contains_provider(self):
        assert "OPENCLAW_LLM_PROVIDER" in self._read_template()

    def test_llm_conf_contains_url(self):
        assert "OPENCLAW_LLM_URL" in self._read_template()

    def test_llm_conf_contains_api_key(self):
        assert "OPENCLAW_LLM_API_KEY" in self._read_template()

    def test_llm_conf_contains_port(self):
        assert "OPENCLAW_PORT" in self._read_template()

    def test_llm_conf_is_systemd_override(self):
        assert "[Service]" in self._read_template()


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
# Host vars avec variables OpenClaw modernisées
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
                        "openclaw_llm_provider": "anthropic",
                        "openclaw_version": "1.2.0",
                    },
                ),
            },
        )
        infra = make_infra(domains={"ai-tools": domain})
        host_vars = generate_host_vars(infra)

        assert "ai-tools-assistant" in host_vars
        hv = host_vars["ai-tools-assistant"]
        assert hv["openclaw_channels"] == ["telegram"]
        assert hv["openclaw_llm_provider"] == "anthropic"
        assert hv["openclaw_version"] == "1.2.0"

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
