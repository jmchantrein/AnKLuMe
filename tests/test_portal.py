"""Tests pour engine/portal.py — transfert de fichiers hôte ↔ conteneur."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from anklume.engine.portal import (
    TransferResult,
    _parse_ls_output,
    list_remote,
    pull_file,
    push_file,
)
from tests.conftest import make_domain, make_infra, make_machine, mock_driver


class TestPushFile:
    """Tests pour push_file."""

    def test_push_basic(self, tmp_path):
        """Push d'un fichier existant vers /tmp/."""
        local = tmp_path / "test.txt"
        local.write_text("contenu")

        infra = make_infra(domains={"pro": make_domain("pro", {"dev": make_machine("dev", "pro")})})
        driver = mock_driver()

        result = push_file(driver, infra, "pro-dev", str(local))

        assert isinstance(result, TransferResult)
        assert result.instance == "pro-dev"
        expected = "/tmp/test.txt"
        assert result.remote_path == expected
        assert result.size == 7
        driver.file_push.assert_called_once_with(
            "pro-dev",
            "pro",
            str(local),
            expected,
        )

    def test_push_custom_remote_path(self, tmp_path):
        """Push vers un chemin distant personnalisé."""
        local = tmp_path / "data.bin"
        local.write_bytes(b"\x00" * 100)

        infra = make_infra(domains={"pro": make_domain("pro", {"dev": make_machine("dev", "pro")})})
        driver = mock_driver()

        result = push_file(driver, infra, "pro-dev", str(local), "/home/user/data.bin")

        assert result.remote_path == "/home/user/data.bin"
        assert result.size == 100

    def test_push_unknown_instance(self, tmp_path):
        """Erreur si instance inconnue."""
        local = tmp_path / "file.txt"
        local.write_text("x")

        infra = make_infra()
        driver = mock_driver()

        with pytest.raises(ValueError, match="Instance inconnue"):
            push_file(driver, infra, "inexistant", str(local))

    def test_push_file_not_found(self):
        """Erreur si fichier local introuvable."""
        infra = make_infra(domains={"pro": make_domain("pro", {"dev": make_machine("dev", "pro")})})
        driver = mock_driver()

        bad_path = "/tmp/inexistant_xyz.txt"
        with pytest.raises(FileNotFoundError, match="introuvable"):
            push_file(driver, infra, "pro-dev", bad_path)

    def test_push_remote_path_with_trailing_slash(self, tmp_path):
        """Si remote_path finit par /, ajoute le nom du fichier."""
        local = tmp_path / "rapport.pdf"
        local.write_text("pdf")

        infra = make_infra(domains={"pro": make_domain("pro", {"dev": make_machine("dev", "pro")})})
        driver = mock_driver()

        result = push_file(driver, infra, "pro-dev", str(local), "/home/")

        assert result.remote_path == "/home/rapport.pdf"


class TestPullFile:
    """Tests pour pull_file."""

    def test_pull_basic(self, tmp_path):
        """Pull d'un fichier vers le répertoire courant."""
        infra = make_infra(domains={"pro": make_domain("pro", {"dev": make_machine("dev", "pro")})})
        driver = mock_driver()

        # Simuler le fichier tiré
        dest = tmp_path / "syslog"
        dest.write_text("log content")

        result = pull_file(driver, infra, "pro-dev", "/var/log/syslog", str(dest))

        assert isinstance(result, TransferResult)
        assert result.instance == "pro-dev"
        assert result.remote_path == "/var/log/syslog"
        driver.file_pull.assert_called_once()

    def test_pull_unknown_instance(self):
        """Erreur si instance inconnue."""
        infra = make_infra()
        driver = mock_driver()

        remote = "/tmp/file.txt"
        with pytest.raises(ValueError, match="Instance inconnue"):
            pull_file(driver, infra, "inexistant", remote)

    def test_pull_to_directory(self, tmp_path):
        """Pull vers un répertoire ajoute le nom du fichier distant."""
        infra = make_infra(domains={"pro": make_domain("pro", {"dev": make_machine("dev", "pro")})})
        driver = mock_driver()

        result = pull_file(driver, infra, "pro-dev", "/var/log/syslog", str(tmp_path))

        assert result.local_path == str(tmp_path / "syslog")


class TestListRemote:
    """Tests pour list_remote."""

    def test_list_basic(self):
        """Listing d'un répertoire distant."""
        infra = make_infra(domains={"pro": make_domain("pro", {"dev": make_machine("dev", "pro")})})
        driver = mock_driver()
        driver.instance_exec.return_value = MagicMock(
            stdout=(
                "total 8\n"
                "drwxr-xr-x 2 root root 4096 Mar  9 10:00 backup\n"
                "-rw-r--r-- 1 root root  128 Mar  9 09:00 rapport.pdf\n"
            )
        )

        entries = list_remote(driver, infra, "pro-dev", "/root/")

        assert len(entries) == 2
        assert entries[0].name == "backup"
        assert entries[0].entry_type == "directory"
        assert entries[1].name == "rapport.pdf"
        assert entries[1].entry_type == "file"
        assert entries[1].size == 128

    def test_list_unknown_instance(self):
        """Erreur si instance inconnue."""
        infra = make_infra()
        driver = mock_driver()

        with pytest.raises(ValueError, match="Instance inconnue"):
            list_remote(driver, infra, "inexistant")

    def test_list_empty_directory(self):
        """Répertoire vide retourne une liste vide."""
        infra = make_infra(domains={"pro": make_domain("pro", {"dev": make_machine("dev", "pro")})})
        driver = mock_driver()
        driver.instance_exec.return_value = MagicMock(stdout="total 0\n")

        entries = list_remote(driver, infra, "pro-dev")

        assert entries == []


class TestParseLsOutput:
    """Tests pour _parse_ls_output."""

    def test_parse_files_and_dirs(self):
        """Parse correctement fichiers et répertoires."""
        output = (
            "total 12\n"
            "drwxr-xr-x 2 root root 4096 Mar  9 10:00 .\n"
            "drwxr-xr-x 3 root root 4096 Mar  9 10:00 ..\n"
            "-rw-r--r-- 1 root root  512 Mar  9 09:00 fichier.txt\n"
            "lrwxrwxrwx 1 root root   11 Mar  9 09:00 lien -> fichier.txt\n"
            "drwxr-xr-x 2 root root 4096 Mar  9 10:00 sous-rep\n"
        )

        entries = _parse_ls_output(output)

        assert len(entries) == 3
        assert entries[0].name == "fichier.txt"
        assert entries[0].entry_type == "file"
        assert entries[0].size == 512
        assert entries[0].permissions == "-rw-r--r--"
        assert entries[1].entry_type == "link"
        assert entries[2].entry_type == "directory"

    def test_parse_empty(self):
        """Sortie vide retourne liste vide."""
        assert _parse_ls_output("") == []
        assert _parse_ls_output("total 0\n") == []

    def test_ignore_dot_entries(self):
        """Les entrées . et .. sont ignorées."""
        output = (
            "total 4\n"
            "drwxr-xr-x 2 root root 4096 Mar  9 10:00 .\n"
            "drwxr-xr-x 3 root root 4096 Mar  9 10:00 ..\n"
        )

        assert _parse_ls_output(output) == []
