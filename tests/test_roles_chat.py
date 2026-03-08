"""Tests unitaires — rôles Ansible chat (open_webui, lobechat) Phase 11a."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import yaml

from anklume.provisioner import BUILTIN_ROLES_DIR, has_provisionable_machines
from anklume.provisioner.inventory import generate_inventories
from anklume.provisioner.playbook import generate_host_vars, generate_playbook

from .conftest import make_domain, make_infra, make_machine

# ---------------------------------------------------------------------------
# Vérification existence physique des rôles
# ---------------------------------------------------------------------------


class TestOpenWebuiRoleExists:
    def test_role_directory_exists(self):
        role_dir = BUILTIN_ROLES_DIR / "open_webui"
        assert role_dir.is_dir()

    def test_has_tasks(self):
        tasks = BUILTIN_ROLES_DIR / "open_webui" / "tasks" / "main.yml"
        assert tasks.is_file()
        content = yaml.safe_load(tasks.read_text())
        assert isinstance(content, list)
        assert len(content) > 0

    def test_has_defaults(self):
        defaults = BUILTIN_ROLES_DIR / "open_webui" / "defaults" / "main.yml"
        assert defaults.is_file()
        content = yaml.safe_load(defaults.read_text())
        assert "open_webui_port" in content
        assert content["open_webui_port"] == 3000

    def test_has_handlers(self):
        handlers = BUILTIN_ROLES_DIR / "open_webui" / "handlers" / "main.yml"
        assert handlers.is_file()


class TestLobechatRoleExists:
    def test_role_directory_exists(self):
        role_dir = BUILTIN_ROLES_DIR / "lobechat"
        assert role_dir.is_dir()

    def test_has_tasks(self):
        tasks = BUILTIN_ROLES_DIR / "lobechat" / "tasks" / "main.yml"
        assert tasks.is_file()
        content = yaml.safe_load(tasks.read_text())
        assert isinstance(content, list)
        assert len(content) > 0

    def test_has_defaults(self):
        defaults = BUILTIN_ROLES_DIR / "lobechat" / "defaults" / "main.yml"
        assert defaults.is_file()
        content = yaml.safe_load(defaults.read_text())
        assert "lobechat_port" in content
        assert content["lobechat_port"] == 3210

    def test_has_handlers(self):
        handlers = BUILTIN_ROLES_DIR / "lobechat" / "handlers" / "main.yml"
        assert handlers.is_file()


# ---------------------------------------------------------------------------
# Contenu des rôles
# ---------------------------------------------------------------------------


class TestOpenWebuiContent:
    def test_installs_open_webui(self):
        tasks = yaml.safe_load(
            (BUILTIN_ROLES_DIR / "open_webui" / "tasks" / "main.yml").read_text()
        )
        task_names = [t.get("name", "") for t in tasks]
        assert any("open" in n.lower() and "webui" in n.lower() for n in task_names)

    def test_creates_systemd_service(self):
        tasks = yaml.safe_load(
            (BUILTIN_ROLES_DIR / "open_webui" / "tasks" / "main.yml").read_text()
        )
        task_names = [t.get("name", "") for t in tasks]
        assert any("systemd" in n.lower() for n in task_names)

    def test_waits_for_ready(self):
        tasks = yaml.safe_load(
            (BUILTIN_ROLES_DIR / "open_webui" / "tasks" / "main.yml").read_text()
        )
        task_names = [t.get("name", "") for t in tasks]
        assert any("attendre" in n.lower() or "prêt" in n.lower() for n in task_names)

    def test_defaults_ollama_url(self):
        defaults = yaml.safe_load(
            (BUILTIN_ROLES_DIR / "open_webui" / "defaults" / "main.yml").read_text()
        )
        assert "open_webui_ollama_url" in defaults
        assert "11434" in defaults["open_webui_ollama_url"]


class TestLobechatContent:
    def test_installs_nodejs(self):
        tasks = yaml.safe_load((BUILTIN_ROLES_DIR / "lobechat" / "tasks" / "main.yml").read_text())
        task_names = [t.get("name", "") for t in tasks]
        assert any("node" in n.lower() for n in task_names)

    def test_clones_lobechat(self):
        tasks = yaml.safe_load((BUILTIN_ROLES_DIR / "lobechat" / "tasks" / "main.yml").read_text())
        task_names = [t.get("name", "") for t in tasks]
        assert any("lobechat" in n.lower() and "clone" in n.lower() for n in task_names)

    def test_creates_systemd_service(self):
        tasks = yaml.safe_load((BUILTIN_ROLES_DIR / "lobechat" / "tasks" / "main.yml").read_text())
        task_names = [t.get("name", "") for t in tasks]
        assert any("systemd" in n.lower() for n in task_names)

    def test_waits_for_ready(self):
        tasks = yaml.safe_load((BUILTIN_ROLES_DIR / "lobechat" / "tasks" / "main.yml").read_text())
        task_names = [t.get("name", "") for t in tasks]
        assert any("attendre" in n.lower() or "prêt" in n.lower() for n in task_names)

    def test_defaults_ollama_url(self):
        defaults = yaml.safe_load(
            (BUILTIN_ROLES_DIR / "lobechat" / "defaults" / "main.yml").read_text()
        )
        assert "lobechat_ollama_url" in defaults
        assert "11434" in defaults["lobechat_ollama_url"]


# ---------------------------------------------------------------------------
# Playbook avec rôles chat
# ---------------------------------------------------------------------------


class TestPlaybookWithChatRoles:
    def test_open_webui_role_in_playbook(self):
        domain = make_domain(
            "ai-tools",
            machines={
                "webui": make_machine("webui", "ai-tools", roles=["base", "open_webui"]),
            },
        )
        infra = make_infra(domains={"ai-tools": domain})
        plays = generate_playbook(infra)

        assert len(plays) == 1
        assert plays[0]["hosts"] == "ai-tools-webui"
        assert "open_webui" in plays[0]["roles"]

    def test_lobechat_role_in_playbook(self):
        domain = make_domain(
            "ai-tools",
            machines={
                "chat": make_machine("chat", "ai-tools", roles=["base", "lobechat"]),
            },
        )
        infra = make_infra(domains={"ai-tools": domain})
        plays = generate_playbook(infra)

        assert len(plays) == 1
        assert "lobechat" in plays[0]["roles"]

    def test_both_chat_roles_separate_machines(self):
        domain = make_domain(
            "ai-tools",
            machines={
                "webui": make_machine("webui", "ai-tools", roles=["base", "open_webui"]),
                "chat": make_machine("chat", "ai-tools", roles=["base", "lobechat"]),
            },
        )
        infra = make_infra(domains={"ai-tools": domain})
        plays = generate_playbook(infra)

        assert len(plays) == 2
        all_roles = [r for p in plays for r in p["roles"]]
        assert "open_webui" in all_roles
        assert "lobechat" in all_roles

    def test_chat_machine_detected_as_provisionable(self):
        domain = make_domain(
            "ai-tools",
            machines={
                "webui": make_machine("webui", "ai-tools", roles=["open_webui"]),
            },
        )
        infra = make_infra(domains={"ai-tools": domain})
        assert has_provisionable_machines(infra)


# ---------------------------------------------------------------------------
# Host vars avec variables chat
# ---------------------------------------------------------------------------


class TestHostVarsWithChatVars:
    def test_open_webui_vars_in_host_vars(self):
        domain = make_domain(
            "ai-tools",
            machines={
                "webui": make_machine(
                    "webui",
                    "ai-tools",
                    roles=["open_webui"],
                    vars={
                        "open_webui_port": 3000,
                        "open_webui_ollama_url": "http://gpu-server:11434",
                    },
                ),
            },
        )
        infra = make_infra(domains={"ai-tools": domain})
        host_vars = generate_host_vars(infra)

        assert "ai-tools-webui" in host_vars
        assert host_vars["ai-tools-webui"]["open_webui_port"] == 3000

    def test_lobechat_vars_in_host_vars(self):
        domain = make_domain(
            "ai-tools",
            machines={
                "chat": make_machine(
                    "chat",
                    "ai-tools",
                    roles=["lobechat"],
                    vars={"lobechat_port": 3210, "lobechat_ollama_url": "http://gpu-server:11434"},
                ),
            },
        )
        infra = make_infra(domains={"ai-tools": domain})
        host_vars = generate_host_vars(infra)

        assert "ai-tools-chat" in host_vars
        assert host_vars["ai-tools-chat"]["lobechat_port"] == 3210

    def test_no_vars_no_host_vars(self):
        domain = make_domain(
            "ai-tools",
            machines={
                "webui": make_machine("webui", "ai-tools", roles=["open_webui"]),
            },
        )
        infra = make_infra(domains={"ai-tools": domain})
        host_vars = generate_host_vars(infra)

        assert "ai-tools-webui" not in host_vars


# ---------------------------------------------------------------------------
# Inventaire avec machines chat
# ---------------------------------------------------------------------------


class TestInventoryWithChatMachines:
    def test_webui_machine_in_inventory(self):
        domain = make_domain(
            "ai-tools",
            machines={
                "webui": make_machine("webui", "ai-tools", roles=["open_webui"]),
            },
        )
        infra = make_infra(domains={"ai-tools": domain})
        inventories = generate_inventories(infra)

        assert "ai-tools" in inventories
        hosts = inventories["ai-tools"]["all"]["children"]["ai-tools"]["hosts"]
        assert "ai-tools-webui" in hosts

    def test_mixed_gpu_and_chat_machines(self):
        domain = make_domain(
            "ai-tools",
            machines={
                "gpu-server": make_machine(
                    "gpu-server", "ai-tools", roles=["ollama_server", "stt_server"]
                ),
                "webui": make_machine("webui", "ai-tools", roles=["base", "open_webui"]),
                "chat": make_machine("chat", "ai-tools", roles=["base", "lobechat"]),
            },
        )
        infra = make_infra(domains={"ai-tools": domain})
        inventories = generate_inventories(infra)

        hosts = inventories["ai-tools"]["all"]["children"]["ai-tools"]["hosts"]
        assert "ai-tools-gpu-server" in hosts
        assert "ai-tools-webui" in hosts
        assert "ai-tools-chat" in hosts


# ---------------------------------------------------------------------------
# Write playbook avec rôles chat (intégration filesystem)
# ---------------------------------------------------------------------------


class TestWritePlaybookWithChatRoles:
    def test_writes_site_yml_with_chat_roles(self, tmp_path: Path):
        from anklume.provisioner.playbook import write_playbook

        domain = make_domain(
            "ai-tools",
            machines={
                "webui": make_machine(
                    "webui",
                    "ai-tools",
                    roles=["base", "open_webui"],
                ),
            },
        )
        infra = make_infra(domains={"ai-tools": domain})
        path = write_playbook(tmp_path, infra)

        assert path is not None
        content = path.read_text()
        assert "open_webui" in content

    def test_writes_host_vars_with_chat_vars(self, tmp_path: Path):
        from anklume.provisioner.playbook import write_host_vars

        domain = make_domain(
            "ai-tools",
            machines={
                "webui": make_machine(
                    "webui",
                    "ai-tools",
                    roles=["open_webui"],
                    vars={"open_webui_port": 3000},
                ),
            },
        )
        infra = make_infra(domains={"ai-tools": domain})
        paths = write_host_vars(tmp_path, infra)

        assert len(paths) == 1
        assert paths[0].name == "ai-tools-webui.yml"
        data = yaml.safe_load(paths[0].read_text())
        assert data["open_webui_port"] == 3000


# ---------------------------------------------------------------------------
# Service definitions dans engine/ai.py
# ---------------------------------------------------------------------------


class TestChatServiceDefs:
    def test_open_webui_role_constant_exists(self):
        from anklume.engine.ai import ROLE_OPEN_WEBUI

        assert ROLE_OPEN_WEBUI == "open_webui"

    def test_lobechat_role_constant_exists(self):
        from anklume.engine.ai import ROLE_LOBECHAT

        assert ROLE_LOBECHAT == "lobechat"

    def test_open_webui_in_service_defs(self):
        from anklume.engine.ai import _SERVICE_DEFS

        roles = [d["role"] for d in _SERVICE_DEFS]
        assert "open_webui" in roles

    def test_lobechat_in_service_defs(self):
        from anklume.engine.ai import _SERVICE_DEFS

        roles = [d["role"] for d in _SERVICE_DEFS]
        assert "lobechat" in roles

    def test_open_webui_default_port(self):
        from anklume.engine.ai import _SERVICE_DEFS

        svc = next(d for d in _SERVICE_DEFS if d["role"] == "open_webui")
        assert svc["default_port"] == 3000

    def test_lobechat_default_port(self):
        from anklume.engine.ai import _SERVICE_DEFS

        svc = next(d for d in _SERVICE_DEFS if d["role"] == "lobechat")
        assert svc["default_port"] == 3210


# ---------------------------------------------------------------------------
# ai status détecte les services chat
# ---------------------------------------------------------------------------


class TestAiStatusWithChat:
    def test_detects_open_webui_service(self):
        from anklume.engine.ai import compute_ai_status
        from anklume.engine.gpu import GpuInfo
        from anklume.engine.models import Domain, GlobalConfig, Infrastructure, Machine

        m = Machine(
            name="webui",
            full_name="ai-tools-webui",
            description="WebUI",
            roles=["open_webui"],
            ip="10.100.3.2",
            vars={"open_webui_port": 3000},
        )
        d = Domain(
            name="ai-tools",
            description="IA",
            machines={"webui": m},
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

        webui_svcs = [s for s in status.services if s.name == "open_webui"]
        assert len(webui_svcs) == 1
        assert webui_svcs[0].reachable is True

    def test_detects_lobechat_service(self):
        from anklume.engine.ai import compute_ai_status
        from anklume.engine.gpu import GpuInfo
        from anklume.engine.models import Domain, GlobalConfig, Infrastructure, Machine

        m = Machine(
            name="chat",
            full_name="ai-tools-chat",
            description="Chat",
            roles=["lobechat"],
            ip="10.100.3.3",
        )
        d = Domain(
            name="ai-tools",
            description="IA",
            machines={"chat": m},
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

        chat_svcs = [s for s in status.services if s.name == "lobechat"]
        assert len(chat_svcs) == 1
        assert chat_svcs[0].reachable is True


# ---------------------------------------------------------------------------
# anklume init — machines chat dans ai-tools
# ---------------------------------------------------------------------------


class TestInitChatMachines:
    def test_ai_tools_mentions_open_webui(self, tmp_path):
        from anklume.cli._init import run_init

        project = tmp_path / "test"
        run_init(str(project))
        content = (project / "domains" / "ai-tools.yml").read_text()
        assert "open_webui" in content

    def test_ai_tools_mentions_open_webui_en(self, tmp_path):
        from anklume.cli._init import run_init

        project = tmp_path / "test"
        run_init(str(project), lang="en")
        content = (project / "domains" / "ai-tools.yml").read_text()
        assert "open_webui" in content

    def test_policies_mention_chat_ports(self, tmp_path):
        from anklume.cli._init import run_init

        project = tmp_path / "test"
        run_init(str(project))
        content = (project / "policies.yml").read_text()
        assert "3000" in content
