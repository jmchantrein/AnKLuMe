"""Tests unitaires pour engine/e2e_real.py — logique de génération et parsing."""

from __future__ import annotations

import shutil

import pytest
import yaml

from anklume.engine.e2e_real import (
    ANKLUME_VM_PATH,
    SANDBOX_DOMAIN,
    SANDBOX_INSTANCE,
    SANDBOX_PROJECT,
    E2eRealConfig,
    E2eRealResult,
    _parse_pytest_summary,
    generate_e2e_project,
)


class TestConstants:
    """Constantes du module e2e_real."""

    def test_sandbox_domain_name(self):
        assert SANDBOX_DOMAIN == "e2e-sandbox"

    def test_sandbox_instance_name(self):
        assert SANDBOX_INSTANCE == "e2e-sandbox-runner"

    def test_sandbox_project_name(self):
        assert SANDBOX_PROJECT == SANDBOX_DOMAIN

    def test_vm_path(self):
        assert ANKLUME_VM_PATH == "/opt/anklume"


class TestE2eRealConfig:
    """Dataclass E2eRealConfig."""

    def test_defaults(self):
        config = E2eRealConfig()
        assert config.memory == "8GiB"
        assert config.cpu == "8"
        assert config.keep_vm is False
        assert config.test_filter == ""
        assert config.verbose is False
        assert config.timeout == 600

    def test_custom_values(self):
        config = E2eRealConfig(
            memory="16GiB",
            cpu="12",
            keep_vm=True,
            test_filter="nftables",
            verbose=True,
            timeout=300,
        )
        assert config.memory == "16GiB"
        assert config.cpu == "12"
        assert config.keep_vm is True
        assert config.test_filter == "nftables"
        assert config.timeout == 300


class TestE2eRealResult:
    """Dataclass E2eRealResult."""

    def test_defaults(self):
        result = E2eRealResult()
        assert result.exit_code == 1
        assert result.stdout == ""
        assert result.duration_s == 0.0
        assert result.tests_passed == 0
        assert result.tests_failed == 0
        assert result.tests_errors == 0
        assert result.errors == []

    def test_success_result(self):
        result = E2eRealResult(
            exit_code=0,
            tests_passed=15,
            duration_s=42.5,
        )
        assert result.exit_code == 0
        assert result.tests_passed == 15


class TestGenerateProject:
    """Génération du projet sandbox."""

    @pytest.fixture()
    def sandbox_project(self):
        config = E2eRealConfig()
        project_dir = generate_e2e_project(config)
        yield project_dir
        shutil.rmtree(project_dir, ignore_errors=True)

    def test_creates_valid_project(self, sandbox_project):
        assert (sandbox_project / "anklume.yml").exists()
        assert (sandbox_project / "domains" / f"{SANDBOX_DOMAIN}.yml").exists()
        assert (sandbox_project / "policies.yml").exists()

    def test_anklume_yml_content(self, sandbox_project):
        data = yaml.safe_load((sandbox_project / "anklume.yml").read_text())
        assert data["schema_version"] == 1
        assert data["addressing"]["base"] == "10.200"
        assert data["defaults"]["os_image"] == "images:debian/13"

    def test_domain_yml_content(self):
        config = E2eRealConfig(memory="16GiB", cpu="12")
        project_dir = generate_e2e_project(config)
        try:
            data = yaml.safe_load((project_dir / "domains" / f"{SANDBOX_DOMAIN}.yml").read_text())
            assert data["trust_level"] == "admin"
            runner = data["machines"]["runner"]
            assert runner["type"] == "vm"
            assert "e2e_runner" in runner["roles"]
            assert runner["config"]["limits.memory"] == "16GiB"
            assert runner["config"]["limits.cpu"] == "12"
            assert runner["config"]["security.nesting"] == "true"
        finally:
            shutil.rmtree(project_dir, ignore_errors=True)

    def test_policies_empty(self, sandbox_project):
        data = yaml.safe_load((sandbox_project / "policies.yml").read_text())
        assert data["policies"] == []


class TestParsePytestSummary:
    """Extraction des résultats pytest depuis stdout."""

    def test_all_passed(self):
        stdout = "============ 15 passed in 42.5s ============"
        passed, failed, errors = _parse_pytest_summary(stdout)
        assert passed == 15
        assert failed == 0
        assert errors == 0

    def test_mixed_results(self):
        stdout = "============ 10 passed, 3 failed, 2 error in 60s ============"
        passed, failed, errors = _parse_pytest_summary(stdout)
        assert passed == 10
        assert failed == 3
        assert errors == 2

    def test_all_failed(self):
        stdout = "============ 5 failed in 30s ============"
        passed, failed, _errors = _parse_pytest_summary(stdout)
        assert passed == 0
        assert failed == 5

    def test_empty_output(self):
        passed, failed, errors = _parse_pytest_summary("")
        assert passed == 0
        assert failed == 0
        assert errors == 0


class TestRoleExists:
    """Vérification de l'existence du rôle e2e_runner."""

    def test_tasks_file_exists(self):
        from anklume.provisioner import BUILTIN_ROLES_DIR

        tasks = BUILTIN_ROLES_DIR / "e2e_runner" / "tasks" / "main.yml"
        assert tasks.exists()

    def test_defaults_file_exists(self):
        from anklume.provisioner import BUILTIN_ROLES_DIR

        defaults = BUILTIN_ROLES_DIR / "e2e_runner" / "defaults" / "main.yml"
        assert defaults.exists()

    def test_tasks_content(self):
        from anklume.provisioner import BUILTIN_ROLES_DIR

        tasks_file = BUILTIN_ROLES_DIR / "e2e_runner" / "tasks" / "main.yml"
        content = tasks_file.read_text()
        assert "Installer Incus" in content
        assert "Initialiser Incus" in content
        assert "Installer uv" in content
        assert "nftables" in content

    def test_defaults_content(self):
        from anklume.provisioner import BUILTIN_ROLES_DIR

        defaults_file = BUILTIN_ROLES_DIR / "e2e_runner" / "defaults" / "main.yml"
        data = yaml.safe_load(defaults_file.read_text())
        assert data["e2e_runner_incus_init"] is True
        assert data["e2e_runner_anklume_path"] == "/opt/anklume"


class TestCliRegistration:
    """Vérification de l'enregistrement CLI."""

    def test_dev_test_real_command_exists(self):
        from anklume.cli import dev_app

        commands = [cmd.name for cmd in dev_app.registered_commands]
        assert "test-real" in commands
