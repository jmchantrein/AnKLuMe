"""Tests pour engine/golden.py — golden images."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from anklume.engine.golden import (
    GOLDEN_PREFIX,
    GoldenImage,
    create_golden,
    delete_golden,
    list_golden,
)
from anklume.engine.incus_driver import IncusImage, IncusInstance, IncusProject
from tests.conftest import make_domain, make_infra, make_machine, mock_driver


def _golden_driver(
    *,
    projects: list[IncusProject] | None = None,
    instances: dict[str, list[IncusInstance]] | None = None,
    images: list[IncusImage] | None = None,
) -> MagicMock:
    """Crée un driver mocké pour golden images."""
    driver = mock_driver(projects=projects, instances=instances)
    driver.image_list.return_value = images or []
    driver.image_publish.return_value = {
        "fingerprint": "a1b2c3d4e5f6a1b2",
        "size": 850_000_000,
    }
    driver.image_alias_exists.return_value = False
    driver.image_delete.return_value = None
    return driver


class TestCreateGolden:
    """Tests pour create_golden."""

    def test_create_basic(self):
        """Publication d'une instance comme golden image."""
        domain = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro", ip="10.100.20.1")},
        )
        infra = make_infra(domains={"pro": domain})
        driver = _golden_driver(
            projects=[IncusProject(name="pro")],
            instances={
                "pro": [
                    IncusInstance(
                        name="pro-dev",
                        status="Running",
                        type="container",
                        project="pro",
                    )
                ]
            },
        )

        result = create_golden(driver, infra, "pro-dev")

        assert isinstance(result, GoldenImage)
        assert result.alias == f"{GOLDEN_PREFIX}pro-dev"
        assert result.fingerprint == "a1b2c3d4e5f6a1b2"
        assert result.instance == "pro-dev"
        driver.instance_stop.assert_called_once_with("pro-dev", "pro")
        driver.image_publish.assert_called_once()
        driver.instance_start.assert_called_once_with("pro-dev", "pro")

    def test_create_custom_alias(self):
        """Alias personnalisé via --alias."""
        domain = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro")},
        )
        infra = make_infra(domains={"pro": domain})
        driver = _golden_driver(
            projects=[IncusProject(name="pro")],
            instances={
                "pro": [
                    IncusInstance(
                        name="pro-dev",
                        status="Running",
                        type="container",
                        project="pro",
                    )
                ]
            },
        )

        result = create_golden(driver, infra, "pro-dev", alias="my-image")

        assert result.alias == "my-image"

    def test_create_stopped_instance(self):
        """Une instance déjà arrêtée est publiée sans stop/start inutile."""
        domain = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro")},
        )
        infra = make_infra(domains={"pro": domain})
        driver = _golden_driver(
            projects=[IncusProject(name="pro")],
            instances={
                "pro": [
                    IncusInstance(
                        name="pro-dev",
                        status="Stopped",
                        type="container",
                        project="pro",
                    )
                ]
            },
        )

        create_golden(driver, infra, "pro-dev")

        driver.instance_stop.assert_not_called()
        driver.instance_start.assert_not_called()
        driver.image_publish.assert_called_once()

    def test_create_unknown_instance(self):
        """Erreur si l'instance est inconnue."""
        infra = make_infra(domains={})
        driver = _golden_driver()

        with pytest.raises(ValueError, match="unknown-inst"):
            create_golden(driver, infra, "unknown-inst")

    def test_create_default_alias(self):
        """L'alias par défaut est golden/<full_name>."""
        domain = make_domain(
            "perso",
            machines={"browser": make_machine("browser", "perso")},
        )
        infra = make_infra(domains={"perso": domain})
        driver = _golden_driver(
            projects=[IncusProject(name="perso")],
            instances={
                "perso": [
                    IncusInstance(
                        name="perso-browser",
                        status="Running",
                        type="container",
                        project="perso",
                    )
                ]
            },
        )

        result = create_golden(driver, infra, "perso-browser")

        assert result.alias == "golden/perso-browser"


class TestListGolden:
    """Tests pour list_golden."""

    def test_list_filters_golden_prefix(self):
        """Seules les images golden/* sont retournées."""
        driver = _golden_driver(
            images=[
                IncusImage(
                    fingerprint="aaa",
                    aliases=["golden/pro-dev"],
                    size=100,
                    created_at="2026-03-09",
                ),
                IncusImage(
                    fingerprint="bbb",
                    aliases=["custom-image"],
                    size=200,
                    created_at="2026-03-08",
                ),
                IncusImage(
                    fingerprint="ccc",
                    aliases=["golden/perso-browser"],
                    size=300,
                    created_at="2026-03-07",
                ),
            ]
        )

        result = list_golden(driver)

        assert len(result) == 2
        assert result[0].alias == "golden/pro-dev"
        assert result[1].alias == "golden/perso-browser"

    def test_list_empty(self):
        """Liste vide si aucune golden image."""
        driver = _golden_driver(images=[])

        result = list_golden(driver)

        assert result == []

    def test_list_no_alias(self):
        """Image sans alias ignorée."""
        driver = _golden_driver(
            images=[
                IncusImage(
                    fingerprint="aaa",
                    aliases=[],
                    size=100,
                ),
            ]
        )

        result = list_golden(driver)

        assert result == []


class TestDeleteGolden:
    """Tests pour delete_golden."""

    def test_delete_existing(self):
        """Suppression d'une golden image existante."""
        driver = _golden_driver(
            images=[
                IncusImage(
                    fingerprint="aaa",
                    aliases=["golden/pro-dev"],
                    size=100,
                ),
            ]
        )

        delete_golden(driver, "golden/pro-dev")

        driver.image_delete.assert_called_once_with("aaa", "default")

    def test_delete_unknown(self):
        """Erreur si l'alias est inconnu."""
        driver = _golden_driver(images=[])

        with pytest.raises(ValueError, match="golden/unknown"):
            delete_golden(driver, "golden/unknown")


class TestDriverImageMethods:
    """Tests pour les méthodes image du driver."""

    def test_image_publish_called_with_correct_args(self):
        """image_publish reçoit instance, project et alias."""
        domain = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro")},
        )
        infra = make_infra(domains={"pro": domain})
        driver = _golden_driver(
            projects=[IncusProject(name="pro")],
            instances={
                "pro": [
                    IncusInstance(
                        name="pro-dev",
                        status="Stopped",
                        type="container",
                        project="pro",
                    )
                ]
            },
        )

        create_golden(driver, infra, "pro-dev")

        driver.image_publish.assert_called_once_with(
            "pro-dev",
            "pro",
            alias="golden/pro-dev",
        )

    def test_image_list_called(self):
        """list_golden appelle image_list."""
        driver = _golden_driver(images=[])

        list_golden(driver)

        driver.image_list.assert_called_once()
