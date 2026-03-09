"""Tests pour engine/clipboard.py — presse-papiers hôte ↔ conteneur."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from anklume.engine.clipboard import (
    CLIPBOARD_PATH,
    ClipboardResult,
    clipboard_pull,
    clipboard_push,
    read_host_clipboard,
    write_host_clipboard,
)
from tests.conftest import make_domain, make_infra, make_machine, mock_driver


class TestReadHostClipboard:
    """Tests pour read_host_clipboard."""

    @patch("anklume.engine.clipboard.subprocess.run")
    def test_read_success(self, mock_run):
        """Lecture réussie du presse-papiers."""
        mock_run.return_value = MagicMock(returncode=0, stdout="texte copié")

        result = read_host_clipboard()

        assert result == "texte copié"
        mock_run.assert_called_once_with(
            ["wl-paste", "--no-newline"],
            capture_output=True,
            text=True,
            timeout=5,
        )

    @patch("anklume.engine.clipboard.subprocess.run")
    def test_read_failure(self, mock_run):
        """Erreur si wl-paste échoue."""
        mock_run.return_value = MagicMock(returncode=1, stderr="error")

        with pytest.raises(RuntimeError, match="wl-paste"):
            read_host_clipboard()


class TestWriteHostClipboard:
    """Tests pour write_host_clipboard."""

    @patch("anklume.engine.clipboard.subprocess.run")
    def test_write_success(self, mock_run):
        """Écriture réussie sur le presse-papiers."""
        mock_run.return_value = MagicMock(returncode=0)

        write_host_clipboard("nouveau texte")

        mock_run.assert_called_once_with(
            ["wl-copy"],
            input="nouveau texte",
            capture_output=True,
            text=True,
            timeout=5,
        )

    @patch("anklume.engine.clipboard.subprocess.run")
    def test_write_failure(self, mock_run):
        """Erreur si wl-copy échoue."""
        mock_run.return_value = MagicMock(returncode=1, stderr="error")

        with pytest.raises(RuntimeError, match="wl-copy"):
            write_host_clipboard("texte")


class TestClipboardPush:
    """Tests pour clipboard_push."""

    @patch("anklume.engine.clipboard.read_host_clipboard")
    def test_push_success(self, mock_read):
        """Push du presse-papiers vers le conteneur."""
        mock_read.return_value = "contenu clipboard"

        infra = make_infra(domains={"pro": make_domain("pro", {"dev": make_machine("dev", "pro")})})
        driver = mock_driver()

        result = clipboard_push(driver, infra, "pro-dev")

        assert isinstance(result, ClipboardResult)
        assert result.direction == "push"
        assert result.instance == "pro-dev"
        assert result.content_length == len("contenu clipboard")
        driver.instance_exec.assert_called_once()

    @patch("anklume.engine.clipboard.read_host_clipboard")
    def test_push_unknown_instance(self, mock_read):
        """Erreur si instance inconnue."""
        infra = make_infra()
        driver = mock_driver()

        with pytest.raises(ValueError, match="Instance inconnue"):
            clipboard_push(driver, infra, "inexistant")

    @patch("anklume.engine.clipboard.read_host_clipboard")
    def test_push_empty_clipboard(self, mock_read):
        """Push d'un presse-papiers vide."""
        mock_read.return_value = ""

        infra = make_infra(domains={"pro": make_domain("pro", {"dev": make_machine("dev", "pro")})})
        driver = mock_driver()

        result = clipboard_push(driver, infra, "pro-dev")

        assert result.content_length == 0


class TestClipboardPull:
    """Tests pour clipboard_pull."""

    @patch("anklume.engine.clipboard.write_host_clipboard")
    def test_pull_success(self, mock_write):
        """Pull du presse-papiers depuis le conteneur."""
        infra = make_infra(domains={"pro": make_domain("pro", {"dev": make_machine("dev", "pro")})})
        driver = mock_driver()
        driver.instance_exec.return_value = MagicMock(stdout="texte distant")

        result = clipboard_pull(driver, infra, "pro-dev")

        assert isinstance(result, ClipboardResult)
        assert result.direction == "pull"
        assert result.instance == "pro-dev"
        assert result.content_length == len("texte distant")
        mock_write.assert_called_once_with("texte distant")

    @patch("anklume.engine.clipboard.write_host_clipboard")
    def test_pull_unknown_instance(self, mock_write):
        """Erreur si instance inconnue."""
        infra = make_infra()
        driver = mock_driver()

        with pytest.raises(ValueError, match="Instance inconnue"):
            clipboard_pull(driver, infra, "inexistant")

    @patch("anklume.engine.clipboard.write_host_clipboard")
    def test_pull_reads_clipboard_path(self, mock_write):
        """Pull utilise le bon chemin distant."""
        infra = make_infra(domains={"pro": make_domain("pro", {"dev": make_machine("dev", "pro")})})
        driver = mock_driver()
        driver.instance_exec.return_value = MagicMock(stdout="data")

        clipboard_pull(driver, infra, "pro-dev")

        driver.instance_exec.assert_called_once_with("pro-dev", "pro", ["cat", CLIPBOARD_PATH])
