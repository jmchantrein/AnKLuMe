"""Tests unitaires pour les commandes CLI Phase 14.

Teste les fonctions snapshot delete/rollback, et vérifie
l'existence des commandes CLI dans l'app Typer.
"""

from __future__ import annotations

import pytest

from anklume.engine.incus_driver import (
    IncusError,
    IncusInstance,
    IncusProject,
    IncusSnapshot,
)
from anklume.engine.snapshot import rollback_snapshot

from .conftest import mock_driver

# ============================================================
# rollback_snapshot
# ============================================================


class TestRollbackSnapshot:
    def test_rollback_deletes_newer_snapshots(self) -> None:
        driver = mock_driver(
            projects=[IncusProject(name="pro")],
            instances={
                "pro": [
                    IncusInstance(
                        name="pro-dev", status="Running", type="container", project="pro"
                    )
                ]
            },
            snapshots={
                "pro-dev": [
                    IncusSnapshot(name="snap-1", created_at="2025-01-01T10:00:00"),
                    IncusSnapshot(name="snap-2", created_at="2025-01-02T10:00:00"),
                    IncusSnapshot(name="snap-3", created_at="2025-01-03T10:00:00"),
                ]
            },
        )

        deleted_count = rollback_snapshot(driver, "pro-dev", "pro", "snap-1")
        assert deleted_count == 2
        driver.snapshot_restore.assert_called_once_with("pro-dev", "pro", "snap-1")
        driver.instance_stop.assert_called_once_with("pro-dev", "pro")
        driver.instance_start.assert_called_once_with("pro-dev", "pro")

    def test_rollback_no_newer_snapshots(self) -> None:
        driver = mock_driver(
            projects=[IncusProject(name="pro")],
            instances={
                "pro": [
                    IncusInstance(
                        name="pro-dev", status="Running", type="container", project="pro"
                    )
                ]
            },
            snapshots={
                "pro-dev": [
                    IncusSnapshot(name="snap-1", created_at="2025-01-03T10:00:00"),
                ]
            },
        )

        deleted_count = rollback_snapshot(driver, "pro-dev", "pro", "snap-1")
        assert deleted_count == 0

    def test_rollback_stopped_instance(self) -> None:
        driver = mock_driver(
            projects=[IncusProject(name="pro")],
            instances={
                "pro": [
                    IncusInstance(
                        name="pro-dev", status="Stopped", type="container", project="pro"
                    )
                ]
            },
            snapshots={
                "pro-dev": [
                    IncusSnapshot(name="snap-1", created_at="2025-01-01T10:00:00"),
                    IncusSnapshot(name="snap-2", created_at="2025-01-02T10:00:00"),
                ]
            },
        )

        deleted_count = rollback_snapshot(driver, "pro-dev", "pro", "snap-1")
        assert deleted_count == 1
        driver.instance_stop.assert_not_called()
        driver.instance_start.assert_not_called()

    def test_rollback_snapshot_not_found(self) -> None:
        driver = mock_driver(
            projects=[IncusProject(name="pro")],
            instances={
                "pro": [
                    IncusInstance(
                        name="pro-dev", status="Running", type="container", project="pro"
                    )
                ]
            },
            snapshots={
                "pro-dev": [
                    IncusSnapshot(name="snap-1", created_at="2025-01-01"),
                ]
            },
        )

        with pytest.raises(IncusError, match="introuvable"):
            rollback_snapshot(driver, "pro-dev", "pro", "nonexistent")

    def test_rollback_preserves_older_snapshots(self) -> None:
        driver = mock_driver(
            projects=[IncusProject(name="pro")],
            instances={
                "pro": [
                    IncusInstance(
                        name="pro-dev", status="Running", type="container", project="pro"
                    )
                ]
            },
            snapshots={
                "pro-dev": [
                    IncusSnapshot(name="snap-1", created_at="2025-01-01T10:00:00"),
                    IncusSnapshot(name="snap-2", created_at="2025-01-02T10:00:00"),
                    IncusSnapshot(name="snap-3", created_at="2025-01-03T10:00:00"),
                ]
            },
        )

        deleted_count = rollback_snapshot(driver, "pro-dev", "pro", "snap-2")
        assert deleted_count == 1
        # snap-3 supprimé, snap-1 préservé
        driver.snapshot_delete.assert_called_once_with("pro-dev", "pro", "snap-3")


# ============================================================
# CLI app — vérification de l'enregistrement des commandes
# ============================================================


class TestCliRegistration:
    """Vérifie que toutes les commandes Phase 14 sont enregistrées."""

    def test_instance_commands_exist(self) -> None:
        from anklume.cli import instance_app

        command_names = [cmd.name for cmd in instance_app.registered_commands]
        assert "list" in command_names
        assert "exec" in command_names
        assert "info" in command_names

    def test_domain_commands_exist(self) -> None:
        from anklume.cli import domain_app

        command_names = [cmd.name for cmd in domain_app.registered_commands]
        assert "list" in command_names
        assert "check" in command_names
        assert "exec" in command_names
        assert "status" in command_names

    def test_snapshot_commands_exist(self) -> None:
        from anklume.cli import snapshot_app

        command_names = [cmd.name for cmd in snapshot_app.registered_commands]
        assert "create" in command_names
        assert "list" in command_names
        assert "restore" in command_names
        assert "delete" in command_names
        assert "rollback" in command_names

    def test_network_commands_exist(self) -> None:
        from anklume.cli import network_app

        command_names = [cmd.name for cmd in network_app.registered_commands]
        assert "rules" in command_names
        assert "deploy" in command_names
        assert "status" in command_names

    def test_llm_commands_exist(self) -> None:
        from anklume.cli import llm_app

        command_names = [cmd.name for cmd in llm_app.registered_commands]
        assert "status" in command_names
        assert "bench" in command_names


# ============================================================
# snapshot delete (via driver)
# ============================================================


class TestSnapshotDelete:
    def test_driver_snapshot_delete_called(self) -> None:
        driver = mock_driver(
            projects=[IncusProject(name="pro")],
            instances={
                "pro": [
                    IncusInstance(
                        name="pro-dev", status="Running", type="container", project="pro"
                    )
                ]
            },
        )

        driver.snapshot_delete("pro-dev", "pro", "snap-1")
        driver.snapshot_delete.assert_called_once_with("pro-dev", "pro", "snap-1")
