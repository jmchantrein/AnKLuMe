"""Tests unitaires pour engine/incus_driver.py.

Le driver est testé en mockant subprocess.run — pas besoin
d'une installation Incus réelle.
"""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import pytest

from anklume.engine.incus_driver import (
    IncusDriver,
    IncusError,
    IncusNetwork,
    IncusProject,
)

# --- Helpers ---


def _ok(stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    """Simule un appel subprocess réussi."""
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr=stderr)


def _fail(returncode: int = 1, stderr: str = "error") -> subprocess.CompletedProcess:
    """Simule un appel subprocess échoué."""
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout="", stderr=stderr)


def _json_ok(data: list | dict) -> subprocess.CompletedProcess:
    """Simule un appel subprocess réussi avec sortie JSON."""
    return _ok(stdout=json.dumps(data))


@pytest.fixture
def driver() -> IncusDriver:
    return IncusDriver()


# ============================================================
# Projets
# ============================================================


class TestProjectList:
    def test_returns_projects(self, driver: IncusDriver) -> None:
        raw = [
            {"name": "default", "description": "Default Incus project"},
            {"name": "pro", "description": "Domaine pro"},
        ]
        with patch("subprocess.run", return_value=_json_ok(raw)) as mock:
            result = driver.project_list()
        assert len(result) == 2
        assert result[0] == IncusProject(name="default", description="Default Incus project")
        assert result[1] == IncusProject(name="pro", description="Domaine pro")
        # Vérifie la commande appelée
        cmd = mock.call_args[0][0]
        assert "project" in cmd
        assert "list" in cmd
        assert "--format" in cmd
        assert "json" in cmd

    def test_empty_list(self, driver: IncusDriver) -> None:
        with patch("subprocess.run", return_value=_json_ok([])):
            result = driver.project_list()
        assert result == []

    def test_error_raises_incus_error(self, driver: IncusDriver) -> None:
        with patch("subprocess.run", return_value=_fail(stderr="permission denied")):
            with pytest.raises(IncusError) as exc_info:
                driver.project_list()
        assert "permission denied" in str(exc_info.value)


class TestProjectCreate:
    def test_creates_project(self, driver: IncusDriver) -> None:
        with patch("subprocess.run", return_value=_ok()) as mock:
            driver.project_create("pro", description="Domaine pro")
        cmd = mock.call_args[0][0]
        assert "project" in cmd
        assert "create" in cmd
        assert "pro" in cmd

    def test_sets_features(self, driver: IncusDriver) -> None:
        """Le projet doit désactiver features.images et features.profiles."""
        with patch("subprocess.run", return_value=_ok()) as mock:
            driver.project_create("pro")
        cmd = mock.call_args[0][0]
        cmd_str = " ".join(cmd)
        assert "features.images=false" in cmd_str
        assert "features.profiles=false" in cmd_str

    def test_error_raises(self, driver: IncusDriver) -> None:
        with patch("subprocess.run", return_value=_fail(stderr="already exists")):
            with pytest.raises(IncusError):
                driver.project_create("pro")


class TestProjectExists:
    def test_exists(self, driver: IncusDriver) -> None:
        raw = [{"name": "default", "description": ""}, {"name": "pro", "description": ""}]
        with patch("subprocess.run", return_value=_json_ok(raw)):
            assert driver.project_exists("pro") is True

    def test_not_exists(self, driver: IncusDriver) -> None:
        raw = [{"name": "default", "description": ""}]
        with patch("subprocess.run", return_value=_json_ok(raw)):
            assert driver.project_exists("pro") is False


# ============================================================
# Réseaux
# ============================================================


class TestNetworkList:
    def test_returns_networks(self, driver: IncusDriver) -> None:
        raw = [
            {"name": "net-pro", "type": "bridge", "config": {"ipv4.address": "10.120.0.254/24"}},
        ]
        with patch("subprocess.run", return_value=_json_ok(raw)) as mock:
            result = driver.network_list("pro")
        assert len(result) == 1
        assert result[0] == IncusNetwork(
            name="net-pro", type="bridge", config={"ipv4.address": "10.120.0.254/24"}
        )
        cmd = mock.call_args[0][0]
        assert "--project" in cmd
        assert "pro" in cmd

    def test_empty(self, driver: IncusDriver) -> None:
        with patch("subprocess.run", return_value=_json_ok([])):
            assert driver.network_list("pro") == []


class TestNetworkCreate:
    def test_creates_bridge(self, driver: IncusDriver) -> None:
        with patch("subprocess.run", return_value=_ok()) as mock:
            driver.network_create(
                "net-pro", "pro", config={"ipv4.address": "10.120.0.254/24", "ipv4.nat": "true"}
            )
        cmd = mock.call_args[0][0]
        assert "network" in cmd
        assert "create" in cmd
        assert "net-pro" in cmd
        assert "--project" in cmd

    def test_error_raises(self, driver: IncusDriver) -> None:
        with patch("subprocess.run", return_value=_fail()):
            with pytest.raises(IncusError):
                driver.network_create("net-pro", "pro")


class TestNetworkExists:
    def test_exists(self, driver: IncusDriver) -> None:
        raw = [{"name": "net-pro", "type": "bridge", "config": {}}]
        with patch("subprocess.run", return_value=_json_ok(raw)):
            assert driver.network_exists("net-pro", "pro") is True

    def test_not_exists(self, driver: IncusDriver) -> None:
        with patch("subprocess.run", return_value=_json_ok([])):
            assert driver.network_exists("net-pro", "pro") is False


# ============================================================
# Instances
# ============================================================


class TestInstanceList:
    def test_returns_instances(self, driver: IncusDriver) -> None:
        raw = [
            {
                "name": "pro-dev",
                "status": "Running",
                "type": "container",
                "project": "pro",
                "profiles": ["default"],
                "config": {},
            },
        ]
        with patch("subprocess.run", return_value=_json_ok(raw)) as mock:
            result = driver.instance_list("pro")
        assert len(result) == 1
        assert result[0].name == "pro-dev"
        assert result[0].status == "Running"
        assert result[0].type == "container"
        cmd = mock.call_args[0][0]
        assert "--project" in cmd

    def test_empty(self, driver: IncusDriver) -> None:
        with patch("subprocess.run", return_value=_json_ok([])):
            assert driver.instance_list("pro") == []


class TestInstanceCreate:
    def test_creates_container(self, driver: IncusDriver) -> None:
        with patch("subprocess.run", return_value=_ok()) as mock:
            driver.instance_create(
                name="pro-dev",
                project="pro",
                image="images:debian/13",
                instance_type="container",
            )
        cmd = mock.call_args[0][0]
        assert "init" in cmd
        assert "images:debian/13" in cmd
        assert "pro-dev" in cmd
        assert "--project" in cmd

    def test_creates_vm(self, driver: IncusDriver) -> None:
        with patch("subprocess.run", return_value=_ok()) as mock:
            driver.instance_create(
                name="pro-desktop",
                project="pro",
                image="images:debian/13",
                instance_type="virtual-machine",
            )
        cmd = mock.call_args[0][0]
        assert "--vm" in cmd

    def test_with_profiles(self, driver: IncusDriver) -> None:
        with patch("subprocess.run", return_value=_ok()) as mock:
            driver.instance_create(
                name="pro-dev",
                project="pro",
                image="images:debian/13",
                profiles=["default", "gpu-passthrough"],
            )
        cmd = mock.call_args[0][0]
        # Vérifie que les profils sont passés avec -p
        cmd_str = " ".join(cmd)
        assert "-p" in cmd_str

    def test_with_config(self, driver: IncusDriver) -> None:
        with patch("subprocess.run", return_value=_ok()) as mock:
            driver.instance_create(
                name="pro-dev",
                project="pro",
                image="images:debian/13",
                config={"security.protection.delete": "true"},
            )
        cmd = mock.call_args[0][0]
        cmd_str = " ".join(cmd)
        assert "security.protection.delete=true" in cmd_str

    def test_with_network(self, driver: IncusDriver) -> None:
        with patch("subprocess.run", return_value=_ok()) as mock:
            driver.instance_create(
                name="pro-dev",
                project="pro",
                image="images:debian/13",
                network="net-pro",
            )
        cmd = mock.call_args[0][0]
        cmd_str = " ".join(cmd)
        assert "--network" in cmd_str
        assert "net-pro" in cmd_str

    def test_error_raises(self, driver: IncusDriver) -> None:
        with patch("subprocess.run", return_value=_fail(stderr="not found")):
            with pytest.raises(IncusError):
                driver.instance_create("pro-dev", "pro", "images:debian/13")


class TestInstanceStart:
    def test_starts(self, driver: IncusDriver) -> None:
        with patch("subprocess.run", return_value=_ok()) as mock:
            driver.instance_start("pro-dev", "pro")
        cmd = mock.call_args[0][0]
        assert "start" in cmd
        assert "pro-dev" in cmd

    def test_error_raises(self, driver: IncusDriver) -> None:
        with patch("subprocess.run", return_value=_fail()):
            with pytest.raises(IncusError):
                driver.instance_start("pro-dev", "pro")


class TestInstanceStop:
    def test_stops(self, driver: IncusDriver) -> None:
        with patch("subprocess.run", return_value=_ok()) as mock:
            driver.instance_stop("pro-dev", "pro")
        cmd = mock.call_args[0][0]
        assert "stop" in cmd
        assert "pro-dev" in cmd


class TestInstanceDelete:
    def test_deletes(self, driver: IncusDriver) -> None:
        with patch("subprocess.run", return_value=_ok()) as mock:
            driver.instance_delete("pro-dev", "pro")
        cmd = mock.call_args[0][0]
        assert "delete" in cmd
        assert "pro-dev" in cmd


# ============================================================
# Snapshots
# ============================================================


class TestSnapshotCreate:
    def test_creates_snapshot(self, driver: IncusDriver) -> None:
        with patch("subprocess.run", return_value=_ok()) as mock:
            driver.snapshot_create("pro-dev", "pro", "anklume-pre-20260307-143022")
        cmd = mock.call_args[0][0]
        assert "snapshot" in cmd
        assert "create" in cmd
        assert "pro-dev" in cmd
        assert "anklume-pre-20260307-143022" in cmd
        assert "--project" in cmd

    def test_error_raises(self, driver: IncusDriver) -> None:
        with patch("subprocess.run", return_value=_fail(stderr="not found")):
            with pytest.raises(IncusError):
                driver.snapshot_create("pro-dev", "pro", "snap1")


class TestSnapshotList:
    def test_returns_snapshots(self, driver: IncusDriver) -> None:
        from anklume.engine.incus_driver import IncusSnapshot

        raw = [
            {"name": "anklume-pre-20260307-143022", "created_at": "2026-03-07T14:30:22Z"},
            {"name": "anklume-post-20260307-143025", "created_at": "2026-03-07T14:30:25Z"},
        ]
        with patch("subprocess.run", return_value=_json_ok(raw)) as mock:
            result = driver.snapshot_list("pro-dev", "pro")
        assert len(result) == 2
        assert isinstance(result[0], IncusSnapshot)
        assert result[0].name == "anklume-pre-20260307-143022"
        assert result[0].created_at == "2026-03-07T14:30:22Z"
        cmd = mock.call_args[0][0]
        assert "snapshot" in cmd
        assert "list" in cmd
        assert "pro-dev" in cmd
        assert "--project" in cmd

    def test_empty(self, driver: IncusDriver) -> None:
        with patch("subprocess.run", return_value=_json_ok([])):
            result = driver.snapshot_list("pro-dev", "pro")
        assert result == []


class TestSnapshotRestore:
    def test_restores(self, driver: IncusDriver) -> None:
        with patch("subprocess.run", return_value=_ok()) as mock:
            driver.snapshot_restore("pro-dev", "pro", "snap1")
        cmd = mock.call_args[0][0]
        assert "snapshot" in cmd
        assert "restore" in cmd
        assert "pro-dev" in cmd
        assert "snap1" in cmd
        assert "--project" in cmd

    def test_error_raises(self, driver: IncusDriver) -> None:
        with patch("subprocess.run", return_value=_fail(stderr="snapshot not found")):
            with pytest.raises(IncusError):
                driver.snapshot_restore("pro-dev", "pro", "nonexistent")


class TestSnapshotDelete:
    def test_deletes(self, driver: IncusDriver) -> None:
        with patch("subprocess.run", return_value=_ok()) as mock:
            driver.snapshot_delete("pro-dev", "pro", "snap1")
        cmd = mock.call_args[0][0]
        assert "snapshot" in cmd
        assert "delete" in cmd
        assert "pro-dev" in cmd
        assert "snap1" in cmd
        assert "--project" in cmd


# ============================================================
# IncusError
# ============================================================


class TestIncusError:
    def test_message_format(self) -> None:
        err = IncusError(command=["incus", "start", "foo"], returncode=1, stderr="not found")
        assert "incus start foo" in str(err)
        assert "not found" in str(err)
        assert err.returncode == 1

    def test_empty_stderr(self) -> None:
        err = IncusError(command=["incus", "list"], returncode=1, stderr="")
        # Ne doit pas planter même avec stderr vide
        assert "incus list" in str(err)
