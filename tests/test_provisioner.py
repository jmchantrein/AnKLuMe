"""Tests unitaires pour le provisioner Ansible.

Le provisioner est testé avec des mocks (pas de vrai Ansible).
On vérifie : génération d'inventaire, playbook, host_vars,
détection Ansible, orchestration du provisioning.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from anklume.provisioner import (
    ProvisionResult,
    has_provisionable_machines,
    provision,
)
from anklume.provisioner.inventory import generate_inventories, write_inventories
from anklume.provisioner.playbook import (
    generate_host_vars,
    generate_playbook,
    write_host_vars,
    write_playbook,
)
from anklume.provisioner.runner import (
    ansible_available,
    install_galaxy_requirements,
    run_playbook,
)

from .conftest import make_domain, make_infra, make_machine

# ============================================================
# has_provisionable_machines
# ============================================================


class TestHasProvisionableMachines:
    def test_no_machines(self) -> None:
        infra = make_infra()
        assert not has_provisionable_machines(infra)

    def test_machines_without_roles(self) -> None:
        domain = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro")},
        )
        infra = make_infra(domains={"pro": domain})
        assert not has_provisionable_machines(infra)

    def test_machines_with_roles(self) -> None:
        domain = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro", roles=["base"])},
        )
        infra = make_infra(domains={"pro": domain})
        assert has_provisionable_machines(infra)

    def test_disabled_domain_ignored(self) -> None:
        domain = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro", roles=["base"])},
            enabled=False,
        )
        infra = make_infra(domains={"pro": domain})
        assert not has_provisionable_machines(infra)

    def test_mixed_roles_and_no_roles(self) -> None:
        domain = make_domain(
            "pro",
            machines={
                "dev": make_machine("dev", "pro", roles=["base"]),
                "desktop": make_machine("desktop", "pro"),
            },
        )
        infra = make_infra(domains={"pro": domain})
        assert has_provisionable_machines(infra)


# ============================================================
# generate_inventories
# ============================================================


class TestGenerateInventories:
    def test_single_domain(self) -> None:
        domain = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro")},
        )
        infra = make_infra(domains={"pro": domain})
        result = generate_inventories(infra)

        assert "pro" in result
        inv = result["pro"]
        hosts = inv["all"]["children"]["pro"]["hosts"]
        assert "pro-dev" in hosts
        assert hosts["pro-dev"]["ansible_connection"] == "anklume_incus"
        assert hosts["pro-dev"]["anklume_incus_project"] == "pro"

    def test_multiple_machines(self) -> None:
        domain = make_domain(
            "pro",
            machines={
                "dev": make_machine("dev", "pro"),
                "desktop": make_machine("desktop", "pro"),
            },
        )
        infra = make_infra(domains={"pro": domain})
        result = generate_inventories(infra)

        hosts = result["pro"]["all"]["children"]["pro"]["hosts"]
        assert "pro-dev" in hosts
        assert "pro-desktop" in hosts

    def test_multiple_domains(self) -> None:
        d1 = make_domain("pro", machines={"dev": make_machine("dev", "pro")})
        d2 = make_domain("perso", machines={"web": make_machine("web", "perso")})
        infra = make_infra(domains={"pro": d1, "perso": d2})
        result = generate_inventories(infra)

        assert "pro" in result
        assert "perso" in result

    def test_disabled_domain_skipped(self) -> None:
        domain = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro")},
            enabled=False,
        )
        infra = make_infra(domains={"pro": domain})
        result = generate_inventories(infra)

        assert "pro" not in result

    def test_empty_domain_still_generated(self) -> None:
        domain = make_domain("pro")
        infra = make_infra(domains={"pro": domain})
        result = generate_inventories(infra)

        assert "pro" in result
        hosts = result["pro"]["all"]["children"]["pro"]["hosts"]
        assert hosts == {}


class TestWriteInventories:
    def test_writes_files(self, tmp_path: Path) -> None:
        domain = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro")},
        )
        infra = make_infra(domains={"pro": domain})
        paths = write_inventories(tmp_path, infra)

        assert len(paths) == 1
        assert paths[0].exists()
        assert paths[0].name == "pro.yml"
        assert paths[0].parent.name == "inventory"

        content = paths[0].read_text()
        assert "Généré par anklume" in content
        data = yaml.safe_load(content)
        assert "all" in data

    def test_creates_directories(self, tmp_path: Path) -> None:
        domain = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro")},
        )
        infra = make_infra(domains={"pro": domain})
        write_inventories(tmp_path, infra)

        assert (tmp_path / "ansible" / "inventory").is_dir()


# ============================================================
# generate_playbook
# ============================================================


class TestGeneratePlaybook:
    def test_machines_with_roles(self) -> None:
        domain = make_domain(
            "pro",
            machines={
                "dev": make_machine("dev", "pro", roles=["base", "dev-tools"]),
            },
        )
        infra = make_infra(domains={"pro": domain})
        plays = generate_playbook(infra)

        assert len(plays) == 1
        assert plays[0]["hosts"] == "pro-dev"
        assert plays[0]["become"] is True
        assert plays[0]["roles"] == ["base", "dev-tools"]

    def test_machines_without_roles_skipped(self) -> None:
        domain = make_domain(
            "pro",
            machines={
                "dev": make_machine("dev", "pro", roles=["base"]),
                "desktop": make_machine("desktop", "pro"),
            },
        )
        infra = make_infra(domains={"pro": domain})
        plays = generate_playbook(infra)

        assert len(plays) == 1
        assert plays[0]["hosts"] == "pro-dev"

    def test_no_roles_anywhere(self) -> None:
        domain = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro")},
        )
        infra = make_infra(domains={"pro": domain})
        plays = generate_playbook(infra)

        assert plays == []

    def test_multiple_domains(self) -> None:
        d1 = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro", roles=["base"])},
        )
        d2 = make_domain(
            "perso",
            machines={"web": make_machine("web", "perso", roles=["base", "desktop"])},
        )
        infra = make_infra(domains={"pro": d1, "perso": d2})
        plays = generate_playbook(infra)

        assert len(plays) == 2
        hosts = {p["hosts"] for p in plays}
        assert hosts == {"pro-dev", "perso-web"}

    def test_disabled_domain_skipped(self) -> None:
        domain = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro", roles=["base"])},
            enabled=False,
        )
        infra = make_infra(domains={"pro": domain})
        plays = generate_playbook(infra)

        assert plays == []

    def test_plays_sorted_by_domain_then_machine(self) -> None:
        d1 = make_domain(
            "pro",
            machines={
                "dev": make_machine("dev", "pro", roles=["base"]),
                "desktop": make_machine("desktop", "pro", roles=["desktop"]),
            },
        )
        d2 = make_domain(
            "ai-tools",
            machines={"gpu": make_machine("gpu", "ai-tools", roles=["base"])},
        )
        infra = make_infra(domains={"pro": d1, "ai-tools": d2})
        plays = generate_playbook(infra)

        assert len(plays) == 3
        assert plays[0]["hosts"] == "ai-tools-gpu"
        assert plays[1]["hosts"] == "pro-desktop"
        assert plays[2]["hosts"] == "pro-dev"


class TestWritePlaybook:
    def test_writes_site_yml(self, tmp_path: Path) -> None:
        domain = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro", roles=["base"])},
        )
        infra = make_infra(domains={"pro": domain})
        path = write_playbook(tmp_path, infra)

        assert path is not None
        assert path.name == "site.yml"
        content = path.read_text()
        assert "Généré par anklume" in content

    def test_returns_none_if_no_plays(self, tmp_path: Path) -> None:
        domain = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro")},
        )
        infra = make_infra(domains={"pro": domain})
        path = write_playbook(tmp_path, infra)

        assert path is None


# ============================================================
# generate_host_vars / write_host_vars
# ============================================================


class TestGenerateHostVars:
    def test_machine_with_vars(self) -> None:
        domain = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro", vars={"pkg": "nodejs"})},
        )
        infra = make_infra(domains={"pro": domain})
        result = generate_host_vars(infra)

        assert "pro-dev" in result
        assert result["pro-dev"]["pkg"] == "nodejs"

    def test_machine_without_vars(self) -> None:
        domain = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro")},
        )
        infra = make_infra(domains={"pro": domain})
        result = generate_host_vars(infra)

        assert "pro-dev" not in result

    def test_disabled_domain_skipped(self) -> None:
        domain = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro", vars={"x": 1})},
            enabled=False,
        )
        infra = make_infra(domains={"pro": domain})
        result = generate_host_vars(infra)

        assert result == {}

    def test_multiple_machines_with_vars(self) -> None:
        domain = make_domain(
            "pro",
            machines={
                "dev": make_machine("dev", "pro", vars={"a": 1}),
                "desktop": make_machine("desktop", "pro", vars={"b": 2}),
            },
        )
        infra = make_infra(domains={"pro": domain})
        result = generate_host_vars(infra)

        assert result["pro-dev"] == {"a": 1}
        assert result["pro-desktop"] == {"b": 2}


class TestWriteHostVars:
    def test_writes_files(self, tmp_path: Path) -> None:
        domain = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro", vars={"pkg": "nodejs"})},
        )
        infra = make_infra(domains={"pro": domain})
        paths = write_host_vars(tmp_path, infra)

        assert len(paths) == 1
        assert paths[0].name == "pro-dev.yml"
        content = paths[0].read_text()
        assert "Généré par anklume" in content

    def test_no_vars_no_files(self, tmp_path: Path) -> None:
        domain = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro")},
        )
        infra = make_infra(domains={"pro": domain})
        paths = write_host_vars(tmp_path, infra)

        assert paths == []


# ============================================================
# ansible_available
# ============================================================


class TestAnsibleAvailable:
    def test_available(self) -> None:
        with patch("shutil.which", return_value="/usr/bin/ansible-playbook"):
            assert ansible_available() is True

    def test_not_available(self) -> None:
        with patch("shutil.which", return_value=None):
            assert ansible_available() is False


# ============================================================
# install_galaxy_requirements
# ============================================================


class TestInstallGalaxyRequirements:
    def test_no_requirements_file(self, tmp_path: Path) -> None:
        """Sans requirements.yml → True (skip silencieux)."""
        result = install_galaxy_requirements(tmp_path, tmp_path / "galaxy_roles")
        assert result is True
        assert not (tmp_path / "galaxy_roles").exists()

    def test_success(self, tmp_path: Path) -> None:
        """requirements.yml présent, ansible-galaxy réussit."""
        (tmp_path / "requirements.yml").write_text("---\nroles:\n  - name: geerlingguy.docker\n")
        galaxy_dir = tmp_path / "galaxy_roles"

        result_mock = MagicMock()
        result_mock.returncode = 0
        result_mock.stdout = "ok"
        result_mock.stderr = ""

        with (
            patch("shutil.which", return_value="/usr/bin/ansible-galaxy"),
            patch("subprocess.run", return_value=result_mock) as mock_run,
        ):
            result = install_galaxy_requirements(tmp_path, galaxy_dir)

        assert result is True
        assert galaxy_dir.is_dir()
        cmd = mock_run.call_args[0][0]
        assert "ansible-galaxy" in cmd[0]
        assert "-r" in cmd
        assert str(tmp_path / "requirements.yml") in cmd

    def test_failure(self, tmp_path: Path) -> None:
        """ansible-galaxy échoue → False."""
        (tmp_path / "requirements.yml").write_text("---\nroles:\n  - name: bad.role\n")
        galaxy_dir = tmp_path / "galaxy_roles"

        result_mock = MagicMock()
        result_mock.returncode = 1
        result_mock.stdout = ""
        result_mock.stderr = "ERROR! role not found"

        with (
            patch("shutil.which", return_value="/usr/bin/ansible-galaxy"),
            patch("subprocess.run", return_value=result_mock),
        ):
            result = install_galaxy_requirements(tmp_path, galaxy_dir)

        assert result is False

    def test_ansible_galaxy_absent(self, tmp_path: Path) -> None:
        """ansible-galaxy absent → True (skip avec warning)."""
        (tmp_path / "requirements.yml").write_text("---\nroles:\n  - name: geerlingguy.docker\n")

        with patch("shutil.which", return_value=None):
            result = install_galaxy_requirements(tmp_path, tmp_path / "galaxy_roles")

        assert result is True


# ============================================================
# run_playbook (galaxy_roles_dir)
# ============================================================


class TestRunPlaybookGalaxyPath:
    def test_galaxy_roles_in_path(self, tmp_path: Path) -> None:
        """galaxy_roles_dir apparaît dans ANSIBLE_ROLES_PATH."""
        ansible_dir = tmp_path / "ansible"
        ansible_dir.mkdir()
        (ansible_dir / "site.yml").write_text("---\n")
        (ansible_dir / "inventory").mkdir()
        galaxy = tmp_path / "ansible_roles_galaxy"
        galaxy.mkdir()

        result_mock = MagicMock()
        result_mock.returncode = 0
        result_mock.stdout = ""
        result_mock.stderr = ""

        with patch("subprocess.run", return_value=result_mock) as mock:
            run_playbook(
                project_dir=tmp_path,
                builtin_roles_dir=Path("/builtin"),
                custom_roles_dir=None,
                galaxy_roles_dir=galaxy,
                plugin_dir=Path("/plugins"),
            )

        env = mock.call_args[1].get("env", {})
        roles_path = env.get("ANSIBLE_ROLES_PATH", "")
        assert str(galaxy) in roles_path

    def test_galaxy_between_custom_and_builtin(self, tmp_path: Path) -> None:
        """Ordre : custom > galaxy > builtin."""
        ansible_dir = tmp_path / "ansible"
        ansible_dir.mkdir()
        (ansible_dir / "site.yml").write_text("---\n")
        (ansible_dir / "inventory").mkdir()
        custom = tmp_path / "ansible_roles_custom"
        custom.mkdir()
        galaxy = tmp_path / "ansible_roles_galaxy"
        galaxy.mkdir()

        result_mock = MagicMock()
        result_mock.returncode = 0
        result_mock.stdout = ""
        result_mock.stderr = ""

        with patch("subprocess.run", return_value=result_mock) as mock:
            run_playbook(
                project_dir=tmp_path,
                builtin_roles_dir=Path("/builtin"),
                custom_roles_dir=custom,
                galaxy_roles_dir=galaxy,
                plugin_dir=Path("/plugins"),
            )

        env = mock.call_args[1].get("env", {})
        roles_path = env.get("ANSIBLE_ROLES_PATH", "")
        custom_idx = roles_path.index(str(custom))
        galaxy_idx = roles_path.index(str(galaxy))
        builtin_idx = roles_path.index("/builtin")
        assert custom_idx < galaxy_idx < builtin_idx


# ============================================================
# run_playbook
# ============================================================


class TestRunPlaybook:
    def test_success(self, tmp_path: Path) -> None:
        ansible_dir = tmp_path / "ansible"
        ansible_dir.mkdir()
        (ansible_dir / "site.yml").write_text("---\n- hosts: all\n")
        (ansible_dir / "inventory").mkdir()

        result_mock = MagicMock()
        result_mock.returncode = 0
        result_mock.stdout = "ok=1"
        result_mock.stderr = ""

        with patch("subprocess.run", return_value=result_mock) as mock:
            result = run_playbook(
                project_dir=tmp_path,
                builtin_roles_dir=Path("/builtin"),
                custom_roles_dir=tmp_path / "ansible_roles_custom",
                plugin_dir=Path("/plugins"),
            )

        assert result.success
        cmd = mock.call_args[0][0]
        assert "ansible-playbook" in cmd[0]

    def test_failure(self, tmp_path: Path) -> None:
        ansible_dir = tmp_path / "ansible"
        ansible_dir.mkdir()
        (ansible_dir / "site.yml").write_text("---\n")
        (ansible_dir / "inventory").mkdir()

        result_mock = MagicMock()
        result_mock.returncode = 2
        result_mock.stdout = ""
        result_mock.stderr = "ERROR!"

        with patch("subprocess.run", return_value=result_mock):
            result = run_playbook(
                project_dir=tmp_path,
                builtin_roles_dir=Path("/builtin"),
                custom_roles_dir=None,
                plugin_dir=Path("/plugins"),
            )

        assert not result.success
        assert "ERROR!" in result.error

    def test_roles_path_includes_custom_and_builtin(self, tmp_path: Path) -> None:
        ansible_dir = tmp_path / "ansible"
        ansible_dir.mkdir()
        (ansible_dir / "site.yml").write_text("---\n")
        (ansible_dir / "inventory").mkdir()
        custom = tmp_path / "ansible_roles_custom"
        custom.mkdir()

        result_mock = MagicMock()
        result_mock.returncode = 0
        result_mock.stdout = ""
        result_mock.stderr = ""

        with patch("subprocess.run", return_value=result_mock) as mock:
            run_playbook(
                project_dir=tmp_path,
                builtin_roles_dir=Path("/builtin"),
                custom_roles_dir=custom,
                plugin_dir=Path("/plugins"),
            )

        env = mock.call_args[1].get("env", {})
        roles_path = env.get("ANSIBLE_ROLES_PATH", "")
        assert str(custom) in roles_path
        assert "/builtin" in roles_path

    def test_custom_roles_first_in_path(self, tmp_path: Path) -> None:
        """Rôles custom prioritaires sur les builtin."""
        ansible_dir = tmp_path / "ansible"
        ansible_dir.mkdir()
        (ansible_dir / "site.yml").write_text("---\n")
        (ansible_dir / "inventory").mkdir()
        custom = tmp_path / "ansible_roles_custom"
        custom.mkdir()

        result_mock = MagicMock()
        result_mock.returncode = 0
        result_mock.stdout = ""
        result_mock.stderr = ""

        with patch("subprocess.run", return_value=result_mock) as mock:
            run_playbook(
                project_dir=tmp_path,
                builtin_roles_dir=Path("/builtin"),
                custom_roles_dir=custom,
                plugin_dir=Path("/plugins"),
            )

        env = mock.call_args[1].get("env", {})
        roles_path = env.get("ANSIBLE_ROLES_PATH", "")
        custom_idx = roles_path.index(str(custom))
        builtin_idx = roles_path.index("/builtin")
        assert custom_idx < builtin_idx

    def test_plugin_dir_in_env(self, tmp_path: Path) -> None:
        ansible_dir = tmp_path / "ansible"
        ansible_dir.mkdir()
        (ansible_dir / "site.yml").write_text("---\n")
        (ansible_dir / "inventory").mkdir()

        result_mock = MagicMock()
        result_mock.returncode = 0
        result_mock.stdout = ""
        result_mock.stderr = ""

        with patch("subprocess.run", return_value=result_mock) as mock:
            run_playbook(
                project_dir=tmp_path,
                builtin_roles_dir=Path("/builtin"),
                custom_roles_dir=None,
                plugin_dir=Path("/plugins"),
            )

        env = mock.call_args[1].get("env", {})
        assert "/plugins" in env.get("ANSIBLE_CONNECTION_PLUGINS", "")


# ============================================================
# provision (orchestration)
# ============================================================


class TestProvision:
    def test_no_roles_skips(self, tmp_path: Path) -> None:
        domain = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro")},
        )
        infra = make_infra(domains={"pro": domain})

        result = provision(infra, tmp_path)

        assert result.skipped
        assert "aucune machine" in result.skip_reason.lower()

    def test_ansible_not_available_skips(self, tmp_path: Path) -> None:
        domain = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro", roles=["base"])},
        )
        infra = make_infra(domains={"pro": domain})

        with patch("anklume.provisioner.ansible_available", return_value=False):
            result = provision(infra, tmp_path)

        assert result.skipped
        assert "ansible" in result.skip_reason.lower()

    def test_generates_files_and_runs(self, tmp_path: Path) -> None:
        domain = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro", roles=["base"])},
        )
        infra = make_infra(domains={"pro": domain})

        run_result = ProvisionResult(success=True, output="ok=1")

        with (
            patch("anklume.provisioner.ansible_available", return_value=True),
            patch("anklume.provisioner.run_playbook", return_value=run_result),
        ):
            result = provision(infra, tmp_path)

        assert result.success
        assert not result.skipped
        assert (tmp_path / "ansible" / "inventory" / "pro.yml").exists()
        assert (tmp_path / "ansible" / "site.yml").exists()

    def test_generates_host_vars(self, tmp_path: Path) -> None:
        domain = make_domain(
            "pro",
            machines={
                "dev": make_machine("dev", "pro", roles=["base"], vars={"pkg": "git"}),
            },
        )
        infra = make_infra(domains={"pro": domain})

        run_result = ProvisionResult(success=True, output="")

        with (
            patch("anklume.provisioner.ansible_available", return_value=True),
            patch("anklume.provisioner.run_playbook", return_value=run_result),
        ):
            provision(infra, tmp_path)

        assert (tmp_path / "ansible" / "host_vars" / "pro-dev.yml").exists()

    def test_no_host_vars_if_no_vars(self, tmp_path: Path) -> None:
        domain = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro", roles=["base"])},
        )
        infra = make_infra(domains={"pro": domain})

        run_result = ProvisionResult(success=True, output="")

        with (
            patch("anklume.provisioner.ansible_available", return_value=True),
            patch("anklume.provisioner.run_playbook", return_value=run_result),
        ):
            provision(infra, tmp_path)

        assert not (tmp_path / "ansible" / "host_vars").exists()

    def test_ansible_failure_reported(self, tmp_path: Path) -> None:
        domain = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro", roles=["base"])},
        )
        infra = make_infra(domains={"pro": domain})

        run_result = ProvisionResult(success=False, error="UNREACHABLE")

        with (
            patch("anklume.provisioner.ansible_available", return_value=True),
            patch("anklume.provisioner.run_playbook", return_value=run_result),
        ):
            result = provision(infra, tmp_path)

        assert not result.success
        assert "UNREACHABLE" in result.error
