"""Tests unitaires — rôles Ansible IA (ollama_server, stt_server) Phase 10b."""

from __future__ import annotations

from pathlib import Path

import yaml

from anklume.provisioner import BUILTIN_ROLES_DIR, has_provisionable_machines
from anklume.provisioner.inventory import generate_inventories
from anklume.provisioner.playbook import generate_host_vars, generate_playbook

from .conftest import make_domain, make_infra, make_machine

# ---------------------------------------------------------------------------
# Vérification existence physique des rôles
# ---------------------------------------------------------------------------


class TestRolesExist:
    def test_ollama_server_role_exists(self):
        role_dir = BUILTIN_ROLES_DIR / "ollama_server"
        assert role_dir.is_dir()

    def test_ollama_server_has_tasks(self):
        tasks = BUILTIN_ROLES_DIR / "ollama_server" / "tasks" / "main.yml"
        assert tasks.is_file()
        content = yaml.safe_load(tasks.read_text())
        assert isinstance(content, list)
        assert len(content) > 0

    def test_ollama_server_has_defaults(self):
        defaults = BUILTIN_ROLES_DIR / "ollama_server" / "defaults" / "main.yml"
        assert defaults.is_file()
        content = yaml.safe_load(defaults.read_text())
        assert "ollama_port" in content
        assert content["ollama_port"] == 11434

    def test_ollama_server_has_handlers(self):
        handlers = BUILTIN_ROLES_DIR / "ollama_server" / "handlers" / "main.yml"
        assert handlers.is_file()

    def test_stt_server_role_exists(self):
        role_dir = BUILTIN_ROLES_DIR / "stt_server"
        assert role_dir.is_dir()

    def test_stt_server_has_tasks(self):
        tasks = BUILTIN_ROLES_DIR / "stt_server" / "tasks" / "main.yml"
        assert tasks.is_file()
        content = yaml.safe_load(tasks.read_text())
        assert isinstance(content, list)
        assert len(content) > 0

    def test_stt_server_has_defaults(self):
        defaults = BUILTIN_ROLES_DIR / "stt_server" / "defaults" / "main.yml"
        assert defaults.is_file()
        content = yaml.safe_load(defaults.read_text())
        assert "stt_port" in content
        assert content["stt_port"] == 8000
        assert content["stt_language"] == "fr"

    def test_stt_server_has_handlers(self):
        handlers = BUILTIN_ROLES_DIR / "stt_server" / "handlers" / "main.yml"
        assert handlers.is_file()


# ---------------------------------------------------------------------------
# Contenu des rôles
# ---------------------------------------------------------------------------


class TestOllamaServerContent:
    def test_installs_ollama(self):
        tasks = yaml.safe_load(
            (BUILTIN_ROLES_DIR / "ollama_server" / "tasks" / "main.yml").read_text()
        )
        task_names = [t.get("name", "") for t in tasks]
        assert any("ollama" in n.lower() and "install" in n.lower() for n in task_names)

    def test_creates_systemd_service(self):
        tasks = yaml.safe_load(
            (BUILTIN_ROLES_DIR / "ollama_server" / "tasks" / "main.yml").read_text()
        )
        task_names = [t.get("name", "") for t in tasks]
        assert any("systemd" in n.lower() for n in task_names)

    def test_waits_for_ready(self):
        tasks = yaml.safe_load(
            (BUILTIN_ROLES_DIR / "ollama_server" / "tasks" / "main.yml").read_text()
        )
        task_names = [t.get("name", "") for t in tasks]
        assert any("attendre" in n.lower() or "prêt" in n.lower() for n in task_names)

    def test_gpu_detection(self):
        tasks = yaml.safe_load(
            (BUILTIN_ROLES_DIR / "ollama_server" / "tasks" / "main.yml").read_text()
        )
        task_names = [t.get("name", "") for t in tasks]
        assert any("gpu" in n.lower() for n in task_names)

    def test_default_model_pull(self):
        tasks = yaml.safe_load(
            (BUILTIN_ROLES_DIR / "ollama_server" / "tasks" / "main.yml").read_text()
        )
        task_names = [t.get("name", "") for t in tasks]
        assert any("modèle" in n.lower() or "model" in n.lower() for n in task_names)

    def test_defaults_gpu_enabled(self):
        defaults = yaml.safe_load(
            (BUILTIN_ROLES_DIR / "ollama_server" / "defaults" / "main.yml").read_text()
        )
        assert defaults["ollama_gpu_enabled"] is True


class TestSttServerContent:
    def test_installs_dependencies(self):
        tasks = yaml.safe_load(
            (BUILTIN_ROLES_DIR / "stt_server" / "tasks" / "main.yml").read_text()
        )
        task_names = [t.get("name", "") for t in tasks]
        assert any("dépendances" in n.lower() or "depend" in n.lower() for n in task_names)

    def test_installs_uv(self):
        tasks = yaml.safe_load(
            (BUILTIN_ROLES_DIR / "stt_server" / "tasks" / "main.yml").read_text()
        )
        task_names = [t.get("name", "") for t in tasks]
        assert any("uv" in n.lower() for n in task_names)

    def test_clones_speaches(self):
        tasks = yaml.safe_load(
            (BUILTIN_ROLES_DIR / "stt_server" / "tasks" / "main.yml").read_text()
        )
        task_names = [t.get("name", "") for t in tasks]
        assert any("speaches" in n.lower() and "clone" in n.lower() for n in task_names)

    def test_creates_systemd_service(self):
        tasks = yaml.safe_load(
            (BUILTIN_ROLES_DIR / "stt_server" / "tasks" / "main.yml").read_text()
        )
        task_names = [t.get("name", "") for t in tasks]
        assert any("systemd" in n.lower() for n in task_names)

    def test_gpu_detection(self):
        tasks = yaml.safe_load(
            (BUILTIN_ROLES_DIR / "stt_server" / "tasks" / "main.yml").read_text()
        )
        task_names = [t.get("name", "") for t in tasks]
        assert any("gpu" in n.lower() for n in task_names)

    def test_defaults_auto_device(self):
        defaults = yaml.safe_load(
            (BUILTIN_ROLES_DIR / "stt_server" / "defaults" / "main.yml").read_text()
        )
        assert defaults["stt_device"] == "auto"
        assert defaults["stt_compute_type"] == "auto"


# ---------------------------------------------------------------------------
# Génération playbook avec rôles IA
# ---------------------------------------------------------------------------


class TestPlaybookWithIaRoles:
    def test_ollama_role_in_playbook(self):
        domain = make_domain(
            "ai-tools",
            machines={
                "gpu-server": make_machine(
                    "gpu-server", "ai-tools", roles=["base", "ollama_server"]
                ),
            },
        )
        infra = make_infra(domains={"ai-tools": domain})
        plays = generate_playbook(infra)

        assert len(plays) == 1
        assert plays[0]["hosts"] == "ai-tools-gpu-server"
        assert "ollama_server" in plays[0]["roles"]
        assert "base" in plays[0]["roles"]

    def test_stt_role_in_playbook(self):
        domain = make_domain(
            "ai-tools",
            machines={
                "gpu-server": make_machine(
                    "gpu-server", "ai-tools", roles=["base", "stt_server"]
                ),
            },
        )
        infra = make_infra(domains={"ai-tools": domain})
        plays = generate_playbook(infra)

        assert len(plays) == 1
        assert "stt_server" in plays[0]["roles"]

    def test_both_roles_on_same_machine(self):
        domain = make_domain(
            "ai-tools",
            machines={
                "gpu-server": make_machine(
                    "gpu-server",
                    "ai-tools",
                    roles=["base", "ollama_server", "stt_server"],
                ),
            },
        )
        infra = make_infra(domains={"ai-tools": domain})
        plays = generate_playbook(infra)

        assert len(plays) == 1
        assert plays[0]["roles"] == ["base", "ollama_server", "stt_server"]

    def test_ia_machine_detected_as_provisionable(self):
        domain = make_domain(
            "ai-tools",
            machines={
                "gpu-server": make_machine(
                    "gpu-server", "ai-tools", roles=["ollama_server"]
                ),
            },
        )
        infra = make_infra(domains={"ai-tools": domain})
        assert has_provisionable_machines(infra)


# ---------------------------------------------------------------------------
# Host vars avec variables IA
# ---------------------------------------------------------------------------


class TestHostVarsWithIaVars:
    def test_ollama_vars_in_host_vars(self):
        domain = make_domain(
            "ai-tools",
            machines={
                "gpu-server": make_machine(
                    "gpu-server",
                    "ai-tools",
                    roles=["ollama_server"],
                    vars={"ollama_default_model": "qwen2:0.5b", "ollama_port": 11434},
                ),
            },
        )
        infra = make_infra(domains={"ai-tools": domain})
        host_vars = generate_host_vars(infra)

        assert "ai-tools-gpu-server" in host_vars
        assert host_vars["ai-tools-gpu-server"]["ollama_default_model"] == "qwen2:0.5b"
        assert host_vars["ai-tools-gpu-server"]["ollama_port"] == 11434

    def test_stt_vars_in_host_vars(self):
        domain = make_domain(
            "ai-tools",
            machines={
                "gpu-server": make_machine(
                    "gpu-server",
                    "ai-tools",
                    roles=["stt_server"],
                    vars={"stt_model": "large-v3", "stt_language": "fr"},
                ),
            },
        )
        infra = make_infra(domains={"ai-tools": domain})
        host_vars = generate_host_vars(infra)

        assert "ai-tools-gpu-server" in host_vars
        assert host_vars["ai-tools-gpu-server"]["stt_model"] == "large-v3"

    def test_mixed_ollama_and_stt_vars(self):
        domain = make_domain(
            "ai-tools",
            machines={
                "gpu-server": make_machine(
                    "gpu-server",
                    "ai-tools",
                    roles=["ollama_server", "stt_server"],
                    vars={
                        "ollama_default_model": "llama3:8b",
                        "stt_port": 8000,
                        "stt_language": "en",
                    },
                ),
            },
        )
        infra = make_infra(domains={"ai-tools": domain})
        host_vars = generate_host_vars(infra)

        hv = host_vars["ai-tools-gpu-server"]
        assert hv["ollama_default_model"] == "llama3:8b"
        assert hv["stt_port"] == 8000
        assert hv["stt_language"] == "en"

    def test_no_vars_no_host_vars(self):
        domain = make_domain(
            "ai-tools",
            machines={
                "gpu-server": make_machine(
                    "gpu-server", "ai-tools", roles=["ollama_server"]
                ),
            },
        )
        infra = make_infra(domains={"ai-tools": domain})
        host_vars = generate_host_vars(infra)

        assert "ai-tools-gpu-server" not in host_vars


# ---------------------------------------------------------------------------
# Inventaire avec domaine IA
# ---------------------------------------------------------------------------


class TestInventoryWithIaDomain:
    def test_ai_tools_domain_inventory(self):
        domain = make_domain(
            "ai-tools",
            machines={
                "gpu-server": make_machine(
                    "gpu-server", "ai-tools", roles=["ollama_server"]
                ),
            },
        )
        infra = make_infra(domains={"ai-tools": domain})
        inventories = generate_inventories(infra)

        assert "ai-tools" in inventories
        hosts = inventories["ai-tools"]["all"]["children"]["ai-tools"]["hosts"]
        assert "ai-tools-gpu-server" in hosts
        assert hosts["ai-tools-gpu-server"]["anklume_incus_project"] == "ai-tools"

    def test_multiple_ia_machines_inventory(self):
        domain = make_domain(
            "ai-tools",
            machines={
                "gpu-server": make_machine(
                    "gpu-server", "ai-tools", roles=["ollama_server", "stt_server"]
                ),
                "webui": make_machine("webui", "ai-tools", roles=["base"]),
            },
        )
        infra = make_infra(domains={"ai-tools": domain})
        inventories = generate_inventories(infra)

        hosts = inventories["ai-tools"]["all"]["children"]["ai-tools"]["hosts"]
        assert "ai-tools-gpu-server" in hosts
        assert "ai-tools-webui" in hosts


# ---------------------------------------------------------------------------
# Write playbook avec rôles IA (intégration filesystem)
# ---------------------------------------------------------------------------


class TestWritePlaybookWithIaRoles:
    def test_writes_site_yml_with_ia_roles(self, tmp_path: Path):
        from anklume.provisioner.playbook import write_playbook

        domain = make_domain(
            "ai-tools",
            machines={
                "gpu-server": make_machine(
                    "gpu-server",
                    "ai-tools",
                    roles=["base", "ollama_server", "stt_server"],
                ),
            },
        )
        infra = make_infra(domains={"ai-tools": domain})
        path = write_playbook(tmp_path, infra)

        assert path is not None
        content = path.read_text()
        assert "ollama_server" in content
        assert "stt_server" in content

        data = yaml.safe_load(content)
        assert len(data) == 1
        assert data[0]["hosts"] == "ai-tools-gpu-server"

    def test_writes_host_vars_with_ia_vars(self, tmp_path: Path):
        from anklume.provisioner.playbook import write_host_vars

        domain = make_domain(
            "ai-tools",
            machines={
                "gpu-server": make_machine(
                    "gpu-server",
                    "ai-tools",
                    roles=["ollama_server"],
                    vars={"ollama_default_model": "qwen2:0.5b"},
                ),
            },
        )
        infra = make_infra(domains={"ai-tools": domain})
        paths = write_host_vars(tmp_path, infra)

        assert len(paths) == 1
        assert paths[0].name == "ai-tools-gpu-server.yml"
        data = yaml.safe_load(paths[0].read_text())
        assert data["ollama_default_model"] == "qwen2:0.5b"
