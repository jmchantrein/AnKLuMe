"""Tests pour engine/disposable.py — conteneurs jetables."""

from __future__ import annotations

from unittest.mock import MagicMock

from anklume.engine.disposable import (
    DISP_PREFIX,
    DISP_PROJECT,
    DispContainer,
    cleanup_disposables,
    destroy_disposable,
    generate_disp_name,
    launch_disposable,
    list_disposables,
)
from anklume.engine.incus_driver import IncusInstance
from tests.conftest import mock_driver


def _disp_driver(instances: list[IncusInstance] | None = None) -> MagicMock:
    """Crée un driver mocké pour disposable (sans side_effect sur instance_list)."""
    driver = mock_driver()
    driver.instance_list.side_effect = None
    driver.instance_list.return_value = instances or []
    return driver


class TestGenerateDispName:
    """Tests pour generate_disp_name."""

    def test_format(self):
        """Le nom suit le format disp-XXXXXXXX (8 hex)."""
        name = generate_disp_name()
        assert name.startswith(DISP_PREFIX)
        assert len(name) == len(DISP_PREFIX) + 8

    def test_unique(self):
        """Deux appels génèrent des noms différents."""
        names = {generate_disp_name() for _ in range(20)}
        assert len(names) == 20

    def test_hex_suffix(self):
        """Le suffixe est hexadécimal."""
        name = generate_disp_name()
        suffix = name[len(DISP_PREFIX) :]
        int(suffix, 16)  # ValueError si pas hex


class TestLaunchDisposable:
    """Tests pour launch_disposable."""

    def test_launch_basic(self):
        """Lancement d'un conteneur jetable."""
        driver = _disp_driver()

        result = launch_disposable(driver, "images:debian/13")

        assert isinstance(result, DispContainer)
        assert result.name.startswith(DISP_PREFIX)
        assert result.image == "images:debian/13"
        assert result.project == DISP_PROJECT
        assert result.status == "Running"
        driver.instance_create.assert_called_once()
        driver.instance_start.assert_called_once()

    def test_launch_custom_project(self):
        """Lancement dans un projet personnalisé."""
        driver = _disp_driver()

        result = launch_disposable(driver, "images:ubuntu/24.04", project="test")

        assert result.project == "test"

    def test_launch_creates_then_starts(self):
        """L'instance est créée puis démarrée dans cet ordre."""
        driver = _disp_driver()
        calls = []
        driver.instance_create.side_effect = lambda **kwargs: calls.append("create")
        driver.instance_start.side_effect = lambda n, p: calls.append("start")

        launch_disposable(driver, "images:debian/13")

        assert calls == ["create", "start"]


class TestListDisposables:
    """Tests pour list_disposables."""

    def test_list_filters_disp_prefix(self):
        """Seules les instances disp-* sont retournées."""
        driver = _disp_driver(
            [
                IncusInstance(
                    name="disp-abcd", status="Running", type="container", project="default"
                ),
                IncusInstance(
                    name="pro-dev", status="Running", type="container", project="default"
                ),
                IncusInstance(
                    name="disp-ef01", status="Stopped", type="container", project="default"
                ),
            ]
        )

        result = list_disposables(driver)

        assert len(result) == 2
        assert result[0].name == "disp-abcd"
        assert result[1].name == "disp-ef01"

    def test_list_empty(self):
        """Liste vide si aucun conteneur jetable."""
        driver = _disp_driver(
            [
                IncusInstance(
                    name="pro-dev", status="Running", type="container", project="default"
                ),
            ]
        )

        result = list_disposables(driver)

        assert result == []

    def test_list_preserves_status(self):
        """L'état des conteneurs est préservé."""
        driver = _disp_driver(
            [
                IncusInstance(
                    name="disp-abcd", status="Stopped", type="container", project="default"
                ),
            ]
        )

        result = list_disposables(driver)

        assert result[0].status == "Stopped"


class TestDestroyDisposable:
    """Tests pour destroy_disposable."""

    def test_destroy_running(self):
        """Un conteneur running est arrêté puis supprimé."""
        driver = _disp_driver(
            [
                IncusInstance(
                    name="disp-abcd", status="Running", type="container", project="default"
                ),
            ]
        )

        destroy_disposable(driver, "disp-abcd")

        driver.instance_stop.assert_called_once_with("disp-abcd", DISP_PROJECT)
        driver.instance_delete.assert_called_once_with("disp-abcd", DISP_PROJECT)

    def test_destroy_stopped(self):
        """Un conteneur stopped est directement supprimé."""
        driver = _disp_driver(
            [
                IncusInstance(
                    name="disp-abcd", status="Stopped", type="container", project="default"
                ),
            ]
        )

        destroy_disposable(driver, "disp-abcd")

        driver.instance_stop.assert_not_called()
        driver.instance_delete.assert_called_once()

    def test_destroy_nonexistent(self):
        """Noop si le conteneur n'existe pas."""
        driver = _disp_driver()

        destroy_disposable(driver, "disp-xxxx")

        driver.instance_stop.assert_not_called()
        driver.instance_delete.assert_not_called()


class TestCleanupDisposables:
    """Tests pour cleanup_disposables."""

    def test_cleanup_all(self):
        """Supprime tous les conteneurs jetables."""
        driver = _disp_driver(
            [
                IncusInstance(
                    name="disp-aaaa", status="Running", type="container", project="default"
                ),
                IncusInstance(
                    name="disp-bbbb", status="Stopped", type="container", project="default"
                ),
                IncusInstance(
                    name="pro-dev", status="Running", type="container", project="default"
                ),
            ]
        )

        count = cleanup_disposables(driver)

        assert count == 2

    def test_cleanup_empty(self):
        """Retourne 0 si aucun conteneur jetable."""
        driver = _disp_driver()

        count = cleanup_disposables(driver)

        assert count == 0
