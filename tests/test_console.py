"""Tests pour engine/console.py — console tmux colorée."""

from __future__ import annotations

from unittest.mock import MagicMock

from anklume.engine.console import (
    SESSION_NAME,
    TRUST_COLORS,
    ConsoleConfig,
    ConsolePane,
    build_console_config,
    launch_console,
)
from anklume.engine.incus_driver import IncusInstance, IncusProject
from tests.conftest import make_domain, make_infra, make_machine, mock_driver


def _console_driver(
    *,
    projects: list[IncusProject] | None = None,
    instances: dict[str, list[IncusInstance]] | None = None,
) -> MagicMock:
    """Crée un driver mocké pour console."""
    return mock_driver(projects=projects, instances=instances)


class TestTrustColors:
    """Tests pour les couleurs par trust level."""

    def test_all_trust_levels_have_color(self):
        """Chaque trust level a une couleur."""
        for level in ("admin", "trusted", "semi-trusted", "untrusted", "disposable"):
            assert level in TRUST_COLORS

    def test_colors_are_tmux_format(self):
        """Les couleurs sont au format tmux (colour + nombre)."""
        for color in TRUST_COLORS.values():
            assert color.startswith("colour")
            int(color.replace("colour", ""))  # ValueError si pas un nombre


class TestBuildConsoleConfig:
    """Tests pour build_console_config."""

    def test_single_domain(self):
        """Configuration pour un seul domaine."""
        domain = make_domain(
            "pro",
            machines={
                "dev": make_machine("dev", "pro", ip="10.100.20.1"),
                "mail": make_machine("mail", "pro", ip="10.100.20.2"),
            },
        )
        infra = make_infra(domains={"pro": domain})
        driver = _console_driver(
            projects=[IncusProject(name="pro")],
            instances={
                "pro": [
                    IncusInstance(
                        name="pro-dev", status="Running", type="container", project="pro"
                    ),
                    IncusInstance(
                        name="pro-mail", status="Running", type="container", project="pro"
                    ),
                ]
            },
        )

        config = build_console_config(infra, driver)

        assert isinstance(config, ConsoleConfig)
        assert config.session_name == SESSION_NAME
        assert "pro" in config.windows
        assert len(config.windows["pro"]) == 2

    def test_only_running_instances(self):
        """Seules les instances running sont incluses."""
        domain = make_domain(
            "pro",
            machines={
                "dev": make_machine("dev", "pro"),
                "mail": make_machine("mail", "pro"),
            },
        )
        infra = make_infra(domains={"pro": domain})
        driver = _console_driver(
            projects=[IncusProject(name="pro")],
            instances={
                "pro": [
                    IncusInstance(
                        name="pro-dev", status="Running", type="container", project="pro"
                    ),
                    IncusInstance(
                        name="pro-mail", status="Stopped", type="container", project="pro"
                    ),
                ]
            },
        )

        config = build_console_config(infra, driver)

        assert len(config.windows["pro"]) == 1
        assert config.windows["pro"][0].instance == "pro-dev"

    def test_filter_by_domain(self):
        """Filtrage par domaine."""
        d1 = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro")},
        )
        d2 = make_domain(
            "perso",
            machines={"browser": make_machine("browser", "perso")},
        )
        infra = make_infra(domains={"pro": d1, "perso": d2})
        driver = _console_driver(
            projects=[IncusProject(name="pro"), IncusProject(name="perso")],
            instances={
                "pro": [
                    IncusInstance(name="pro-dev", status="Running", type="container", project="pro")
                ],
                "perso": [
                    IncusInstance(
                        name="perso-browser",
                        status="Running",
                        type="container",
                        project="perso",
                    )
                ],
            },
        )

        config = build_console_config(infra, driver, domain="pro")

        assert "pro" in config.windows
        assert "perso" not in config.windows
        assert config.session_name == "anklume-pro"

    def test_disabled_domain_excluded(self):
        """Les domaines désactivés sont exclus."""
        d1 = make_domain(
            "pro",
            enabled=True,
            machines={"dev": make_machine("dev", "pro")},
        )
        d2 = make_domain(
            "disabled",
            enabled=False,
            machines={"x": make_machine("x", "disabled")},
        )
        infra = make_infra(domains={"pro": d1, "disabled": d2})
        driver = _console_driver(
            projects=[IncusProject(name="pro")],
            instances={
                "pro": [
                    IncusInstance(name="pro-dev", status="Running", type="container", project="pro")
                ],
            },
        )

        config = build_console_config(infra, driver)

        assert "pro" in config.windows
        assert "disabled" not in config.windows

    def test_empty_domain_excluded(self):
        """Un domaine sans instance running est exclu."""
        domain = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro")},
        )
        infra = make_infra(domains={"pro": domain})
        driver = _console_driver(
            projects=[IncusProject(name="pro")],
            instances={
                "pro": [
                    IncusInstance(name="pro-dev", status="Stopped", type="container", project="pro")
                ],
            },
        )

        config = build_console_config(infra, driver)

        assert "pro" not in config.windows

    def test_pane_has_correct_command(self):
        """Chaque panneau a la bonne commande incus exec."""
        domain = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro")},
        )
        infra = make_infra(domains={"pro": domain})
        driver = _console_driver(
            projects=[IncusProject(name="pro")],
            instances={
                "pro": [
                    IncusInstance(name="pro-dev", status="Running", type="container", project="pro")
                ],
            },
        )

        config = build_console_config(infra, driver)
        pane = config.windows["pro"][0]

        assert isinstance(pane, ConsolePane)
        assert "incus exec" in pane.command
        assert "pro-dev" in pane.command
        assert "--project" in pane.command
        assert "pro" in pane.command

    def test_pane_trust_level(self):
        """Le panneau porte le trust level du domaine."""
        domain = make_domain(
            "anon",
            machines={"browser": make_machine("browser", "anon")},
        )
        domain.trust_level = "untrusted"
        infra = make_infra(domains={"anon": domain})
        driver = _console_driver(
            projects=[IncusProject(name="anon")],
            instances={
                "anon": [
                    IncusInstance(
                        name="anon-browser",
                        status="Running",
                        type="container",
                        project="anon",
                    )
                ],
            },
        )

        config = build_console_config(infra, driver)

        assert config.windows["anon"][0].trust_level == "untrusted"


class TestLaunchConsole:
    """Tests pour launch_console."""

    def test_launch_creates_session(self, monkeypatch):
        """La session tmux est créée."""
        calls = []
        monkeypatch.setattr(
            "anklume.engine.console.subprocess.run",
            lambda cmd, **kw: calls.append(cmd),
        )

        config = ConsoleConfig(
            session_name="test",
            windows={
                "pro": [
                    ConsolePane(
                        instance="pro-dev",
                        domain="pro",
                        trust_level="semi-trusted",
                        command="incus exec pro-dev --project pro -- bash",
                    )
                ]
            },
        )

        launch_console(config, detach=True)

        # Vérifie qu'au moins un appel tmux a été fait
        assert any("tmux" in str(c) for c in calls)

    def test_launch_empty_config(self, monkeypatch):
        """Config vide : pas de session créée."""
        calls = []
        monkeypatch.setattr(
            "anklume.engine.console.subprocess.run",
            lambda cmd, **kw: calls.append(cmd),
        )

        config = ConsoleConfig(session_name="test", windows={})

        launch_console(config, detach=True)

        # Aucun appel tmux
        assert len(calls) == 0


class TestSessionName:
    """Tests pour le nommage des sessions."""

    def test_default_session_name(self):
        """Le nom de session par défaut est 'anklume'."""
        assert SESSION_NAME == "anklume"

    def test_domain_filter_changes_name(self):
        """Le filtrage par domaine change le nom de session."""
        domain = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro")},
        )
        infra = make_infra(domains={"pro": domain})
        driver = _console_driver(
            projects=[IncusProject(name="pro")],
            instances={
                "pro": [
                    IncusInstance(name="pro-dev", status="Running", type="container", project="pro")
                ],
            },
        )

        config = build_console_config(infra, driver, domain="pro")

        assert config.session_name == "anklume-pro"
