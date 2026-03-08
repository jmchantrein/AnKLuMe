"""Tests unitaires — Développement assisté par IA (Phase 11d)."""

from __future__ import annotations

from unittest.mock import patch

import yaml

from anklume.provisioner import BUILTIN_ROLES_DIR

from .conftest import make_domain, make_infra, make_machine

# ---------------------------------------------------------------------------
# Rôle code_sandbox
# ---------------------------------------------------------------------------


class TestCodeSandboxRoleExists:
    def test_role_directory_exists(self):
        role_dir = BUILTIN_ROLES_DIR / "code_sandbox"
        assert role_dir.is_dir()

    def test_has_tasks(self):
        tasks = BUILTIN_ROLES_DIR / "code_sandbox" / "tasks" / "main.yml"
        assert tasks.is_file()
        content = yaml.safe_load(tasks.read_text())
        assert isinstance(content, list)
        assert len(content) > 0

    def test_has_defaults(self):
        defaults = BUILTIN_ROLES_DIR / "code_sandbox" / "defaults" / "main.yml"
        assert defaults.is_file()
        content = yaml.safe_load(defaults.read_text())
        assert "sandbox_timeout" in content
        assert content["sandbox_timeout"] == 60

    def test_defaults_ephemeral(self):
        defaults = yaml.safe_load(
            (BUILTIN_ROLES_DIR / "code_sandbox" / "defaults" / "main.yml").read_text()
        )
        assert defaults["sandbox_ephemeral"] is True

    def test_defaults_network_disabled(self):
        defaults = yaml.safe_load(
            (BUILTIN_ROLES_DIR / "code_sandbox" / "defaults" / "main.yml").read_text()
        )
        assert defaults["sandbox_network"] is False


# ---------------------------------------------------------------------------
# Rôle opencode_server
# ---------------------------------------------------------------------------


class TestOpencodeServerRoleExists:
    def test_role_directory_exists(self):
        role_dir = BUILTIN_ROLES_DIR / "opencode_server"
        assert role_dir.is_dir()

    def test_has_tasks(self):
        tasks = BUILTIN_ROLES_DIR / "opencode_server" / "tasks" / "main.yml"
        assert tasks.is_file()
        content = yaml.safe_load(tasks.read_text())
        assert isinstance(content, list)
        assert len(content) > 0

    def test_has_defaults(self):
        defaults = BUILTIN_ROLES_DIR / "opencode_server" / "defaults" / "main.yml"
        assert defaults.is_file()
        content = yaml.safe_load(defaults.read_text())
        assert "opencode_port" in content
        assert content["opencode_port"] == 8091

    def test_has_handlers(self):
        handlers = BUILTIN_ROLES_DIR / "opencode_server" / "handlers" / "main.yml"
        assert handlers.is_file()

    def test_defaults_ollama_host(self):
        defaults = yaml.safe_load(
            (BUILTIN_ROLES_DIR / "opencode_server" / "defaults" / "main.yml").read_text()
        )
        assert defaults["opencode_ollama_host"] == "localhost"


# ---------------------------------------------------------------------------
# Module engine/ai_dev.py — dataclasses
# ---------------------------------------------------------------------------


class TestAiTestConfig:
    def test_default_values(self):
        from anklume.engine.ai_dev import AiTestConfig

        config = AiTestConfig()
        assert config.backend == "ollama"
        assert config.mode == "dry-run"
        assert config.max_retries == 3
        assert config.model == ""

    def test_custom_values(self):
        from anklume.engine.ai_dev import AiTestConfig

        config = AiTestConfig(backend="claude", mode="auto-apply", max_retries=5, model="opus")
        assert config.backend == "claude"
        assert config.mode == "auto-apply"
        assert config.max_retries == 5


class TestAiTestResult:
    def test_fields(self):
        from anklume.engine.ai_dev import AiTestResult

        result = AiTestResult(
            iteration=1,
            tests_passed=False,
            errors=["AssertionError"],
            fixes_proposed=["fix line 42"],
            fixes_applied=False,
        )
        assert result.iteration == 1
        assert result.tests_passed is False
        assert len(result.errors) == 1

    def test_passed_result(self):
        from anklume.engine.ai_dev import AiTestResult

        result = AiTestResult(
            iteration=1,
            tests_passed=True,
            errors=[],
            fixes_proposed=[],
            fixes_applied=False,
        )
        assert result.tests_passed is True


# ---------------------------------------------------------------------------
# run_ai_test_loop — logique
# ---------------------------------------------------------------------------


class TestRunAiTestLoop:
    def test_stops_when_tests_pass(self, tmp_path):
        from anklume.engine.ai_dev import AiTestConfig, run_ai_test_loop

        config = AiTestConfig(max_retries=3)

        with patch("anklume.engine.ai_dev._run_tests") as mock_tests:
            mock_tests.return_value = (True, [])
            results = run_ai_test_loop(config, project_dir=tmp_path)

        assert len(results) == 1
        assert results[0].tests_passed is True

    def test_retries_on_failure(self, tmp_path):
        from anklume.engine.ai_dev import AiTestConfig, run_ai_test_loop

        config = AiTestConfig(max_retries=3, mode="dry-run")

        with (
            patch("anklume.engine.ai_dev._run_tests") as mock_tests,
            patch("anklume.engine.ai_dev._analyze_errors") as mock_analyze,
        ):
            # Échoue 2 fois, réussit la 3e
            mock_tests.side_effect = [
                (False, ["Error 1"]),
                (False, ["Error 2"]),
                (True, []),
            ]
            mock_analyze.return_value = ["fix suggestion"]
            results = run_ai_test_loop(config, project_dir=tmp_path)

        assert len(results) == 3
        assert results[0].tests_passed is False
        assert results[2].tests_passed is True

    def test_max_retries_respected(self, tmp_path):
        from anklume.engine.ai_dev import AiTestConfig, run_ai_test_loop

        config = AiTestConfig(max_retries=2)

        with (
            patch("anklume.engine.ai_dev._run_tests", return_value=(False, ["Error"])),
            patch("anklume.engine.ai_dev._analyze_errors", return_value=["fix"]),
        ):
            results = run_ai_test_loop(config, project_dir=tmp_path)

        assert len(results) == 2
        assert all(not r.tests_passed for r in results)

    def test_dry_run_does_not_apply(self, tmp_path):
        from anklume.engine.ai_dev import AiTestConfig, run_ai_test_loop

        config = AiTestConfig(max_retries=1, mode="dry-run")

        with (
            patch("anklume.engine.ai_dev._run_tests", return_value=(False, ["Error"])),
            patch("anklume.engine.ai_dev._analyze_errors", return_value=["fix"]),
        ):
            results = run_ai_test_loop(config, project_dir=tmp_path)

        assert results[0].fixes_applied is False

    def test_invalid_backend_raises(self, tmp_path):
        import pytest

        from anklume.engine.ai_dev import AiTestConfig, run_ai_test_loop

        config = AiTestConfig(backend="gpt4")
        with pytest.raises(ValueError, match="backend"):
            run_ai_test_loop(config, project_dir=tmp_path)

    def test_invalid_mode_raises(self, tmp_path):
        import pytest

        from anklume.engine.ai_dev import AiTestConfig, run_ai_test_loop

        config = AiTestConfig(mode="yolo")
        with pytest.raises(ValueError, match="mode"):
            run_ai_test_loop(config, project_dir=tmp_path)


# ---------------------------------------------------------------------------
# Playbook avec rôles dev
# ---------------------------------------------------------------------------


class TestPlaybookWithDevRoles:
    def test_code_sandbox_in_playbook(self):
        from anklume.provisioner.playbook import generate_playbook

        domain = make_domain(
            "ai-tools",
            machines={
                "sandbox": make_machine("sandbox", "ai-tools", roles=["base", "code_sandbox"]),
            },
        )
        infra = make_infra(domains={"ai-tools": domain})
        plays = generate_playbook(infra)

        assert len(plays) == 1
        assert "code_sandbox" in plays[0]["roles"]

    def test_opencode_server_in_playbook(self):
        from anklume.provisioner.playbook import generate_playbook

        domain = make_domain(
            "ai-tools",
            machines={
                "coder": make_machine("coder", "ai-tools", roles=["base", "opencode_server"]),
            },
        )
        infra = make_infra(domains={"ai-tools": domain})
        plays = generate_playbook(infra)

        assert len(plays) == 1
        assert "opencode_server" in plays[0]["roles"]


# ---------------------------------------------------------------------------
# CLI anklume ai test
# ---------------------------------------------------------------------------


class TestCliAiTest:
    def test_command_registered(self):
        """La commande ai test est enregistrée dans la CLI."""
        from anklume.cli import ai_app

        commands = [cmd.name for cmd in ai_app.registered_commands]
        assert "test" in commands
