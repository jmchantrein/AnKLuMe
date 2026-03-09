"""Tests pour les méthodes fichier et exec du driver Incus."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from anklume.engine.incus_driver import IncusDriver, IncusError


class TestFilePush:
    """Tests pour file_push."""

    @patch("anklume.engine.incus_driver.subprocess.run")
    def test_push_command(self, mock_run):
        """Vérifie la commande incus file push."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        driver = IncusDriver()

        remote = "/tmp/file.txt"  # noqa: S108
        driver.file_push("pro-dev", "pro", "/local/file.txt", remote)

        cmd = mock_run.call_args[0][0]
        assert cmd == [
            "incus",
            "file",
            "push",
            "/local/file.txt",
            f"pro-dev{remote}",
            "--project",
            "pro",
        ]

    @patch("anklume.engine.incus_driver.subprocess.run")
    def test_push_error(self, mock_run):
        """Erreur si la commande échoue."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="no such file")
        driver = IncusDriver()

        with pytest.raises(IncusError):
            driver.file_push("pro-dev", "pro", "/bad", "/tmp/x")  # noqa: S108


class TestFilePull:
    """Tests pour file_pull."""

    @patch("anklume.engine.incus_driver.subprocess.run")
    def test_pull_command(self, mock_run):
        """Vérifie la commande incus file pull."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        driver = IncusDriver()

        driver.file_pull("pro-dev", "pro", "/var/log/syslog", "/local/syslog")

        cmd = mock_run.call_args[0][0]
        assert cmd == [
            "incus",
            "file",
            "pull",
            "pro-dev/var/log/syslog",
            "/local/syslog",
            "--project",
            "pro",
        ]


class TestInstanceExecInput:
    """Tests pour instance_exec avec paramètre input."""

    @patch("anklume.engine.incus_driver.subprocess.run")
    def test_exec_with_input(self, mock_run):
        """instance_exec passe l'input à subprocess."""
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        driver = IncusDriver()

        remote = "/tmp/file"  # noqa: S108
        result = driver.instance_exec(
            "pro-dev",
            "pro",
            ["tee", remote],
            input="contenu",
        )

        assert result.stdout == "ok"
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["input"] == "contenu"

    @patch("anklume.engine.incus_driver.subprocess.run")
    def test_exec_without_input(self, mock_run):
        """instance_exec sans input passe None."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        driver = IncusDriver()

        driver.instance_exec("pro-dev", "pro", ["ls"])

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["input"] is None

    @patch("anklume.engine.incus_driver.subprocess.run")
    def test_exec_error_raises(self, mock_run):
        """Erreur si la commande échoue."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        driver = IncusDriver()

        with pytest.raises(IncusError):
            driver.instance_exec("pro-dev", "pro", ["false"])
