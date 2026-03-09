"""Tests unitaires — rôle Ansible admin_bootstrap (Phase 16)."""

from __future__ import annotations

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


class TestAdminBootstrapRoleExists:
    def test_role_directory_exists(self):
        assert (BUILTIN_ROLES_DIR / "admin_bootstrap").is_dir()

    def test_has_tasks(self):
        tasks = role_tasks("admin_bootstrap")
        assert isinstance(tasks, list)
        assert len(tasks) > 0

    def test_has_defaults(self):
        defaults = role_defaults("admin_bootstrap")
        assert isinstance(defaults, dict)


# ---------------------------------------------------------------------------
# Defaults — variables
# ---------------------------------------------------------------------------


class TestAdminBootstrapDefaults:
    def test_locale_default(self):
        assert role_defaults("admin_bootstrap")["bootstrap_locale"] == "fr_FR.UTF-8"

    def test_timezone_default(self):
        assert role_defaults("admin_bootstrap")["bootstrap_timezone"] == "Europe/Paris"

    def test_packages_default(self):
        pkgs = role_defaults("admin_bootstrap")["bootstrap_packages"]
        assert isinstance(pkgs, list)
        assert "vim" in pkgs
        assert "htop" in pkgs
        assert "tree" in pkgs
        assert "jq" in pkgs
        assert "unzip" in pkgs

    def test_upgrade_default(self):
        assert role_defaults("admin_bootstrap")["bootstrap_upgrade"] is True


# ---------------------------------------------------------------------------
# Contenu des tâches
# ---------------------------------------------------------------------------


class TestAdminBootstrapTasks:
    def test_updates_apt_cache(self):
        names = role_task_names("admin_bootstrap")
        assert any("cache" in n.lower() or "apt" in n.lower() for n in names)

    def test_upgrades_packages(self):
        names = role_task_names("admin_bootstrap")
        assert any("upgrade" in n.lower() or "mise à jour" in n.lower() for n in names)

    def test_configures_locale(self):
        names = role_task_names("admin_bootstrap")
        assert any("locale" in n.lower() for n in names)

    def test_configures_timezone(self):
        names = role_task_names("admin_bootstrap")
        assert any("timezone" in n.lower() or "fuseau" in n.lower() for n in names)

    def test_installs_packages(self):
        tasks = role_tasks("admin_bootstrap")
        found = any("bootstrap_packages" in str(t) for t in tasks)
        assert found, "Tâche d'installation des paquets utilitaires introuvable"


# ---------------------------------------------------------------------------
# Playbook avec admin_bootstrap
# ---------------------------------------------------------------------------


class TestPlaybookWithAdminBootstrap:
    def test_admin_bootstrap_in_playbook(self):
        domain = make_domain(
            "pro",
            machines={
                "workstation": make_machine(
                    "workstation", "pro", roles=["base", "admin_bootstrap"]
                ),
            },
        )
        infra = make_infra(domains={"pro": domain})
        plays = generate_playbook(infra)

        assert len(plays) == 1
        assert "admin_bootstrap" in plays[0]["roles"]

    def test_admin_bootstrap_detected_as_provisionable(self):
        domain = make_domain(
            "pro",
            machines={
                "workstation": make_machine("workstation", "pro", roles=["admin_bootstrap"]),
            },
        )
        infra = make_infra(domains={"pro": domain})
        assert has_provisionable_machines(infra)

    def test_combined_with_openclaw(self):
        """admin_bootstrap + openclaw_server dans la même machine."""
        domain = make_domain(
            "ai-tools",
            machines={
                "assistant": make_machine(
                    "assistant",
                    "ai-tools",
                    roles=["base", "admin_bootstrap", "openclaw_server"],
                ),
            },
        )
        infra = make_infra(domains={"ai-tools": domain})
        plays = generate_playbook(infra)

        assert len(plays) == 1
        roles = plays[0]["roles"]
        assert "base" in roles
        assert "admin_bootstrap" in roles
        assert "openclaw_server" in roles


# ---------------------------------------------------------------------------
# Host vars avec variables admin_bootstrap
# ---------------------------------------------------------------------------


class TestHostVarsWithAdminBootstrapVars:
    def test_bootstrap_vars_in_host_vars(self):
        domain = make_domain(
            "pro",
            machines={
                "workstation": make_machine(
                    "workstation",
                    "pro",
                    roles=["base", "admin_bootstrap"],
                    vars={
                        "bootstrap_timezone": "America/New_York",
                        "bootstrap_packages": ["vim", "git", "tmux"],
                        "bootstrap_upgrade": False,
                    },
                ),
            },
        )
        infra = make_infra(domains={"pro": domain})
        host_vars = generate_host_vars(infra)

        assert "pro-workstation" in host_vars
        hv = host_vars["pro-workstation"]
        assert hv["bootstrap_timezone"] == "America/New_York"
        assert hv["bootstrap_packages"] == ["vim", "git", "tmux"]
        assert hv["bootstrap_upgrade"] is False

    def test_no_vars_no_host_vars(self):
        domain = make_domain(
            "pro",
            machines={
                "workstation": make_machine("workstation", "pro", roles=["admin_bootstrap"]),
            },
        )
        infra = make_infra(domains={"pro": domain})
        host_vars = generate_host_vars(infra)

        assert "pro-workstation" not in host_vars
