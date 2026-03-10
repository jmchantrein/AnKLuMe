"""Tests — environnement de développement (dev_env).

Couvre : DevEnvConfig, génération de domaines, politiques réseau,
LLM backends, sanitisation, preset anklume, rôle Ansible, CLI.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from anklume.engine.dev_env import (
    DevEnvConfig,
    anklume_self_dev_config,
    generate_dev_domain,
    generate_dev_policies,
)
from anklume.engine.llm_routing import (
    BACKEND_ANTHROPIC,
    BACKEND_LOCAL,
    BACKEND_OPENAI,
    SANITIZE_ALWAYS,
    SANITIZE_FALSE,
    SANITIZE_TRUE,
)

# ── DevEnvConfig ──


class TestDevEnvConfig:
    """Dataclass DevEnvConfig."""

    def test_defaults(self) -> None:
        c = DevEnvConfig()
        assert c.name == "dev"
        assert c.machine_type == "lxc"
        assert c.trust_level == "trusted"
        assert c.gpu is False
        assert c.llm is False
        assert c.claude_code is False
        assert c.mount_paths == {}
        assert c.memory == ""
        assert c.cpu == ""
        assert c.extra_packages == []
        assert c.llm_backend == BACKEND_LOCAL
        assert c.llm_model == ""
        assert c.sanitize == SANITIZE_FALSE

    def test_auto_description(self) -> None:
        c = DevEnvConfig(name="myproj")
        assert "myproj" in c.description

    def test_explicit_description(self) -> None:
        c = DevEnvConfig(name="foo", description="Mon projet")
        assert c.description == "Mon projet"

    def test_machine_type_vm(self) -> None:
        c = DevEnvConfig(machine_type="vm")
        assert c.machine_type == "vm"

    def test_llm_backend_openai(self) -> None:
        c = DevEnvConfig(llm_backend=BACKEND_OPENAI)
        assert c.llm_backend == BACKEND_OPENAI

    def test_sanitize_always(self) -> None:
        c = DevEnvConfig(sanitize=SANITIZE_ALWAYS)
        assert c.sanitize == SANITIZE_ALWAYS


# ── generate_dev_domain ──


class TestGenerateDevDomain:
    """Génération du YAML domaine."""

    def test_minimal(self) -> None:
        config = DevEnvConfig(name="test")
        result = generate_dev_domain(config)
        data = yaml.safe_load(result)
        assert data["trust_level"] == "trusted"
        assert "test" in data["machines"]
        m = data["machines"]["test"]
        assert m["type"] == "lxc"
        assert "base" in m["roles"]
        assert "dev-tools" in m["roles"]
        assert "dev_env" in m["roles"]

    def test_gpu_local_adds_ollama(self) -> None:
        config = DevEnvConfig(name="gpu-dev", gpu=True, llm_backend=BACKEND_LOCAL)
        result = generate_dev_domain(config)
        data = yaml.safe_load(result)
        m = data["machines"]["gpu-dev"]
        assert m["gpu"] is True
        assert "ollama_server" in m["roles"]

    def test_gpu_openai_no_ollama(self) -> None:
        """GPU + backend cloud : pas d'ollama_server."""
        config = DevEnvConfig(
            name="gpu-cloud",
            gpu=True,
            llm=True,
            llm_backend=BACKEND_OPENAI,
            llm_api_url="https://api.openai.com/v1",
            llm_api_key="sk-test",
        )
        result = generate_dev_domain(config)
        data = yaml.safe_load(result)
        m = data["machines"]["gpu-cloud"]
        assert "ollama_server" not in m["roles"]

    def test_claude_code_vars(self) -> None:
        config = DevEnvConfig(name="cc", claude_code=True)
        result = generate_dev_domain(config)
        data = yaml.safe_load(result)
        m = data["machines"]["cc"]
        assert m["vars"]["dev_env_install_claude_code"] is True

    def test_llm_enables_aider(self) -> None:
        config = DevEnvConfig(name="llm-dev", llm=True)
        result = generate_dev_domain(config)
        data = yaml.safe_load(result)
        m = data["machines"]["llm-dev"]
        assert m["vars"]["dev_env_install_aider"] is True

    def test_mount_paths(self) -> None:
        config = DevEnvConfig(name="mnt", mount_paths={"code": "/home/dev/code"})
        result = generate_dev_domain(config)
        data = yaml.safe_load(result)
        m = data["machines"]["mnt"]
        assert m["persistent"]["code"] == "/home/dev/code"

    def test_resource_limits(self) -> None:
        config = DevEnvConfig(name="res", memory="8GiB", cpu="6")
        result = generate_dev_domain(config)
        data = yaml.safe_load(result)
        m = data["machines"]["res"]
        assert m["config"]["limits.memory"] == "8GiB"
        assert m["config"]["limits.cpu"] == "6"

    def test_git_config(self) -> None:
        config = DevEnvConfig(name="gitcfg", git_name="Dev", git_email="dev@test.com")
        result = generate_dev_domain(config)
        data = yaml.safe_load(result)
        m = data["machines"]["gitcfg"]
        assert m["vars"]["dev_env_git_name"] == "Dev"
        assert m["vars"]["dev_env_git_email"] == "dev@test.com"

    def test_extra_packages(self) -> None:
        config = DevEnvConfig(name="pkgs", extra_packages=["shellcheck", "ansible"])
        result = generate_dev_domain(config)
        data = yaml.safe_load(result)
        m = data["machines"]["pkgs"]
        assert "shellcheck" in m["vars"]["dev_env_extra_packages"]

    def test_vm_type(self) -> None:
        config = DevEnvConfig(name="vmdev", machine_type="vm")
        result = generate_dev_domain(config)
        data = yaml.safe_load(result)
        assert data["machines"]["vmdev"]["type"] == "vm"

    def test_header_comment(self) -> None:
        config = DevEnvConfig(name="hdr")
        result = generate_dev_domain(config)
        assert result.startswith("# Domaine hdr")
        assert "anklume dev env" in result

    def test_no_gpu_key_when_false(self) -> None:
        config = DevEnvConfig(name="nogpu", gpu=False)
        result = generate_dev_domain(config)
        data = yaml.safe_load(result)
        assert "gpu" not in data["machines"]["nogpu"]

    def test_no_vars_when_empty(self) -> None:
        config = DevEnvConfig(name="novar")
        result = generate_dev_domain(config)
        data = yaml.safe_load(result)
        assert "vars" not in data["machines"]["novar"]

    def test_no_config_when_empty(self) -> None:
        config = DevEnvConfig(name="nocfg")
        result = generate_dev_domain(config)
        data = yaml.safe_load(result)
        assert "config" not in data["machines"]["nocfg"]

    def test_no_persistent_when_empty(self) -> None:
        config = DevEnvConfig(name="nomnt")
        result = generate_dev_domain(config)
        data = yaml.safe_load(result)
        assert "persistent" not in data["machines"]["nomnt"]


# ── LLM backend ──


class TestLlmBackend:
    """Configuration du backend LLM dans le domaine généré."""

    def test_openai_backend_vars(self) -> None:
        config = DevEnvConfig(
            name="oai",
            llm=True,
            llm_backend=BACKEND_OPENAI,
            llm_api_url="https://api.openai.com/v1",
            llm_api_key="sk-test",
            llm_model="gpt-4o",
        )
        result = generate_dev_domain(config)
        data = yaml.safe_load(result)
        v = data["machines"]["oai"]["vars"]
        assert v["llm_backend"] == BACKEND_OPENAI
        assert v["llm_api_url"] == "https://api.openai.com/v1"
        assert v["llm_api_key"] == "sk-test"
        assert v["llm_model"] == "gpt-4o"

    def test_anthropic_backend_vars(self) -> None:
        config = DevEnvConfig(
            name="anth",
            llm=True,
            llm_backend=BACKEND_ANTHROPIC,
            llm_api_url="https://api.anthropic.com/v1",
            llm_api_key="sk-ant-test",
        )
        result = generate_dev_domain(config)
        data = yaml.safe_load(result)
        v = data["machines"]["anth"]["vars"]
        assert v["llm_backend"] == BACKEND_ANTHROPIC

    def test_local_backend_no_llm_backend_var(self) -> None:
        """Backend local : pas de var llm_backend (c'est le défaut)."""
        config = DevEnvConfig(name="loc", llm=True, llm_backend=BACKEND_LOCAL)
        result = generate_dev_domain(config)
        data = yaml.safe_load(result)
        v = data["machines"]["loc"]["vars"]
        assert "llm_backend" not in v

    def test_local_model_as_ollama_default(self) -> None:
        """Modèle local → var ollama_default_model."""
        config = DevEnvConfig(
            name="lmod",
            llm=True,
            llm_backend=BACKEND_LOCAL,
            llm_model="qwen2:7b",
        )
        result = generate_dev_domain(config)
        data = yaml.safe_load(result)
        v = data["machines"]["lmod"]["vars"]
        assert v["ollama_default_model"] == "qwen2:7b"
        assert "llm_model" not in v

    def test_cloud_model_as_llm_model(self) -> None:
        """Modèle cloud → var llm_model."""
        config = DevEnvConfig(
            name="cmod",
            llm=True,
            llm_backend=BACKEND_OPENAI,
            llm_api_url="https://api.openai.com/v1",
            llm_api_key="sk-x",
            llm_model="gpt-4o-mini",
        )
        result = generate_dev_domain(config)
        data = yaml.safe_load(result)
        v = data["machines"]["cmod"]["vars"]
        assert v["llm_model"] == "gpt-4o-mini"
        assert "ollama_default_model" not in v


# ── Sanitisation ──


class TestSanitize:
    """Sanitisation LLM dans le domaine généré."""

    def test_sanitize_false_no_machine(self) -> None:
        config = DevEnvConfig(name="nosani", sanitize=SANITIZE_FALSE)
        result = generate_dev_domain(config)
        data = yaml.safe_load(result)
        assert "sanitizer" not in data["machines"]

    def test_sanitize_true_adds_machine(self) -> None:
        config = DevEnvConfig(name="sani", sanitize=SANITIZE_TRUE)
        result = generate_dev_domain(config)
        data = yaml.safe_load(result)
        assert "sanitizer" in data["machines"]
        san = data["machines"]["sanitizer"]
        assert "llm_sanitizer" in san["roles"]
        assert san["type"] == "lxc"

    def test_sanitize_always_adds_machine(self) -> None:
        config = DevEnvConfig(name="saniall", sanitize=SANITIZE_ALWAYS)
        result = generate_dev_domain(config)
        data = yaml.safe_load(result)
        assert "sanitizer" in data["machines"]

    def test_sanitize_var_injected(self) -> None:
        config = DevEnvConfig(name="sanvar", sanitize=SANITIZE_TRUE)
        result = generate_dev_domain(config)
        data = yaml.safe_load(result)
        v = data["machines"]["sanvar"]["vars"]
        assert v["ai_sanitize"] == SANITIZE_TRUE

    def test_sanitize_always_var(self) -> None:
        config = DevEnvConfig(name="sanall", sanitize=SANITIZE_ALWAYS)
        result = generate_dev_domain(config)
        data = yaml.safe_load(result)
        v = data["machines"]["sanall"]["vars"]
        assert v["ai_sanitize"] == SANITIZE_ALWAYS

    def test_sanitizer_defaults(self) -> None:
        config = DevEnvConfig(name="sandfl", sanitize=SANITIZE_TRUE)
        result = generate_dev_domain(config)
        data = yaml.safe_load(result)
        sv = data["machines"]["sanitizer"]["vars"]
        assert sv["sanitizer_mode"] == "mask"
        assert sv["sanitizer_audit"] is True

    def test_sanitize_false_no_var(self) -> None:
        config = DevEnvConfig(name="sanno")
        result = generate_dev_domain(config)
        data = yaml.safe_load(result)
        assert "vars" not in data["machines"]["sanno"]

    def test_full_cloud_with_sanitize(self) -> None:
        config = DevEnvConfig(
            name="cloudsani",
            llm=True,
            llm_backend=BACKEND_OPENAI,
            llm_api_url="https://api.openai.com/v1",
            llm_api_key="sk-test",
            llm_model="gpt-4o",
            sanitize=SANITIZE_TRUE,
        )
        result = generate_dev_domain(config)
        data = yaml.safe_load(result)
        v = data["machines"]["cloudsani"]["vars"]
        assert v["llm_backend"] == BACKEND_OPENAI
        assert v["ai_sanitize"] == SANITIZE_TRUE
        assert "sanitizer" in data["machines"]


# ── generate_dev_policies ──


class TestGenerateDevPolicies:
    """Génération des politiques réseau."""

    def test_no_llm_empty(self) -> None:
        config = DevEnvConfig(name="dev", llm=False)
        assert generate_dev_policies(config) == ""

    def test_llm_local_no_gpu_ollama_policy(self) -> None:
        """LLM local sans GPU → policy Ollama distant."""
        config = DevEnvConfig(name="mydev", llm=True, llm_backend=BACKEND_LOCAL, gpu=False)
        data = yaml.safe_load(generate_dev_policies(config))
        ports = {p["ports"][0] for p in data["policies"]}
        assert 11434 in ports
        assert 8000 in ports

    def test_llm_local_with_gpu_no_ollama_policy(self) -> None:
        """LLM local avec GPU → pas de policy Ollama (c'est local)."""
        config = DevEnvConfig(name="mydev", llm=True, llm_backend=BACKEND_LOCAL, gpu=True)
        data = yaml.safe_load(generate_dev_policies(config))
        ports = {p["ports"][0] for p in data["policies"]}
        assert 11434 not in ports
        assert 8000 in ports

    def test_llm_cloud_no_ollama_policy(self) -> None:
        """Backend cloud → pas de policy Ollama."""
        config = DevEnvConfig(name="mydev", llm=True, llm_backend=BACKEND_OPENAI, gpu=False)
        data = yaml.safe_load(generate_dev_policies(config))
        ports = {p["ports"][0] for p in data["policies"]}
        assert 11434 not in ports
        assert 8000 in ports

    def test_custom_ai_domain(self) -> None:
        config = DevEnvConfig(name="dev", llm=True)
        data = yaml.safe_load(generate_dev_policies(config, ai_domain="custom-ai"))
        assert all(p["to"] == "custom-ai" for p in data["policies"])

    def test_from_matches_domain(self) -> None:
        config = DevEnvConfig(name="proj-dev", llm=True)
        data = yaml.safe_load(generate_dev_policies(config))
        assert all(p["from"] == "proj-dev" for p in data["policies"])


# ── Preset anklume ──


class TestAnklumeSelfDev:
    """Preset d'auto-développement anklume."""

    def test_preset_config(self) -> None:
        c = anklume_self_dev_config()
        assert c.name == "ank-dev"
        assert c.machine_type == "lxc"
        assert c.trust_level == "trusted"
        assert c.claude_code is True
        assert c.llm is True
        assert "anklume" in c.mount_paths
        assert c.sanitize == SANITIZE_TRUE

    def test_preset_generates_valid_yaml(self) -> None:
        c = anklume_self_dev_config()
        result = generate_dev_domain(c)
        data = yaml.safe_load(result)
        m = data["machines"]["ank-dev"]
        assert "base" in m["roles"]
        assert "dev_env" in m["roles"]
        assert m["vars"]["dev_env_install_claude_code"] is True
        assert m["config"]["limits.memory"] == "4GiB"
        assert m["persistent"]["anklume"] == "/home/dev/AnKLuMe"

    def test_preset_has_sanitizer(self) -> None:
        c = anklume_self_dev_config()
        result = generate_dev_domain(c)
        data = yaml.safe_load(result)
        assert "sanitizer" in data["machines"]
        assert data["machines"]["ank-dev"]["vars"]["ai_sanitize"] == SANITIZE_TRUE

    def test_preset_extra_packages(self) -> None:
        c = anklume_self_dev_config()
        assert "shellcheck" in c.extra_packages
        assert "ansible" in c.extra_packages

    def test_preset_domain_yaml_parseable(self) -> None:
        c = anklume_self_dev_config()
        data = yaml.safe_load(generate_dev_domain(c))
        assert "machines" in data
        assert "description" in data


# ── Rôle Ansible dev_env ──


_ROLE_DIR = (
    Path(__file__).resolve().parent.parent / "src" / "anklume" / "provisioner" / "roles" / "dev_env"
)


@pytest.fixture(scope="module")
def role_defaults() -> dict:
    """Parse defaults/main.yml une seule fois pour tout le module."""
    return yaml.safe_load((_ROLE_DIR / "defaults" / "main.yml").read_text())


class TestDevEnvRole:
    """Vérifie la structure du rôle Ansible dev_env."""

    def test_role_dir_exists(self) -> None:
        assert _ROLE_DIR.is_dir()

    def test_tasks_main_exists(self) -> None:
        assert (_ROLE_DIR / "tasks" / "main.yml").is_file()

    def test_defaults_main_exists(self) -> None:
        assert (_ROLE_DIR / "defaults" / "main.yml").is_file()

    def test_defaults_parseable(self, role_defaults: dict) -> None:
        assert "dev_env_install_uv" in role_defaults
        assert "dev_env_install_claude_code" in role_defaults
        assert "dev_env_install_node" in role_defaults
        assert "dev_env_extra_packages" in role_defaults

    def test_defaults_claude_code_off(self, role_defaults: dict) -> None:
        assert role_defaults["dev_env_install_claude_code"] is False

    def test_defaults_uv_on(self, role_defaults: dict) -> None:
        assert role_defaults["dev_env_install_uv"] is True

    def test_tasks_contains_key_steps(self) -> None:
        content = (_ROLE_DIR / "tasks" / "main.yml").read_text()
        assert "uv" in content
        assert "Node.js" in content
        assert "Claude Code" in content
        assert "lazygit" in content
        assert "ripgrep" in content

    def test_defaults_aider_off(self, role_defaults: dict) -> None:
        assert role_defaults["dev_env_install_aider"] is False

    def test_defaults_lazygit_on(self, role_defaults: dict) -> None:
        assert role_defaults["dev_env_install_lazygit"] is True

    def test_defaults_node_version(self, role_defaults: dict) -> None:
        assert role_defaults["dev_env_node_version"] == "22"


# ── CLI ──


@pytest.fixture()
def anklume_project(tmp_path: Path) -> Path:
    """Projet anklume minimal avec domains/."""
    (tmp_path / "domains").mkdir()
    (tmp_path / "anklume.yml").write_text("schema_version: 1\n")
    return tmp_path


class TestDevEnvCLI:
    """Vérifie l'enregistrement et le comportement de la commande CLI."""

    def test_dev_env_registered(self) -> None:
        from anklume.cli import dev_app

        commands = [cmd.name for cmd in dev_app.registered_commands]
        assert "env" in commands

    def test_dev_env_import(self) -> None:
        from anklume.cli._dev_env import run_dev_env

        assert callable(run_dev_env)

    def test_cli_writes_domain_file(self, anklume_project: Path) -> None:
        from anklume.cli._dev_env import run_dev_env

        config = DevEnvConfig(name="testenv")
        run_dev_env(config, output=str(anklume_project))

        domain_file = anklume_project / "domains" / "testenv.yml"
        assert domain_file.exists()
        data = yaml.safe_load(domain_file.read_text())
        assert "machines" in data
        assert "testenv" in data["machines"]

    def test_cli_preset_anklume(self, anklume_project: Path) -> None:
        from anklume.cli._dev_env import run_dev_env

        config = anklume_self_dev_config()
        run_dev_env(config, output=str(anklume_project))

        domain_file = anklume_project / "domains" / "ank-dev.yml"
        assert domain_file.exists()
        data = yaml.safe_load(domain_file.read_text())
        assert "ank-dev" in data["machines"]
        assert "sanitizer" in data["machines"]

    def test_cli_rejects_duplicate(self, anklume_project: Path) -> None:
        (anklume_project / "domains" / "dup.yml").write_text("existing: true\n")

        from click.exceptions import Exit

        from anklume.cli._dev_env import run_dev_env

        with pytest.raises((SystemExit, Exit)):
            run_dev_env(DevEnvConfig(name="dup"), output=str(anklume_project))

    def test_cli_rejects_missing_domains_dir(self, tmp_path: Path) -> None:
        from click.exceptions import Exit

        from anklume.cli._dev_env import run_dev_env

        with pytest.raises((SystemExit, Exit)):
            run_dev_env(DevEnvConfig(name="test"), output=str(tmp_path))

    def test_cli_with_sanitize(self, anklume_project: Path) -> None:
        from anklume.cli._dev_env import run_dev_env

        config = DevEnvConfig(name="santest", llm=True, sanitize=SANITIZE_TRUE)
        run_dev_env(config, output=str(anklume_project))

        domain_file = anklume_project / "domains" / "santest.yml"
        assert domain_file.exists()
        data = yaml.safe_load(domain_file.read_text())
        assert "sanitizer" in data["machines"]
        assert data["machines"]["santest"]["vars"]["ai_sanitize"] == SANITIZE_TRUE

    def test_cli_with_llm_backend(self, anklume_project: Path) -> None:
        from anklume.cli._dev_env import run_dev_env

        config = DevEnvConfig(
            name="clouddev",
            llm=True,
            llm_backend=BACKEND_OPENAI,
            llm_api_url="https://api.openai.com/v1",
            llm_api_key="sk-123",
            llm_model="gpt-4o",
        )
        run_dev_env(config, output=str(anklume_project))

        domain_file = anklume_project / "domains" / "clouddev.yml"
        assert domain_file.exists()
        data = yaml.safe_load(domain_file.read_text())
        v = data["machines"]["clouddev"]["vars"]
        assert v["llm_backend"] == BACKEND_OPENAI
        assert v["llm_model"] == "gpt-4o"

    def test_cli_rejects_invalid_backend(self, anklume_project: Path) -> None:
        from click.exceptions import Exit

        from anklume.cli._dev_env import run_dev_env

        with pytest.raises((SystemExit, Exit)):
            run_dev_env(
                DevEnvConfig(name="bad", llm_backend="invalid"),
                output=str(anklume_project),
            )

    def test_cli_rejects_invalid_sanitize(self, anklume_project: Path) -> None:
        from click.exceptions import Exit

        from anklume.cli._dev_env import run_dev_env

        with pytest.raises((SystemExit, Exit)):
            run_dev_env(
                DevEnvConfig(name="bad", sanitize="invalid"),
                output=str(anklume_project),
            )
