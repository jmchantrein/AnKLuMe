"""Tests pour engine/dev_setup.py — préparation de l'environnement de dev."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from anklume.engine.dev_setup import (
    DevSetupReport,
    SetupStep,
    check_dev_dependencies,
    check_git_hooks,
    check_incus_available,
    install_git_hooks,
    run_dev_setup,
)


class TestSetupStep:
    """Tests pour la dataclass SetupStep."""

    def test_ok_step(self):
        """Étape ok."""
        s = SetupStep(name="test", status="ok", message="installé")
        assert s.status == "ok"
        assert s.skipped is False

    def test_skipped_step(self):
        """Étape skippée."""
        s = SetupStep(name="test", status="ok", message="déjà installé", skipped=True)
        assert s.skipped is True


class TestDevSetupReport:
    """Tests pour DevSetupReport."""

    def test_counts(self):
        """Comptage par statut."""
        report = DevSetupReport(
            steps=[
                SetupStep(name="a", status="ok", message=""),
                SetupStep(name="b", status="ok", message=""),
                SetupStep(name="c", status="warning", message=""),
                SetupStep(name="d", status="error", message=""),
            ]
        )
        assert report.ok_count == 2
        assert report.warning_count == 1
        assert report.error_count == 1

    def test_success(self):
        """Succès si aucune erreur."""
        report = DevSetupReport(
            steps=[
                SetupStep(name="a", status="ok", message=""),
                SetupStep(name="b", status="warning", message=""),
            ]
        )
        assert report.success is True

    def test_failure(self):
        """Échec si au moins une erreur."""
        report = DevSetupReport(
            steps=[
                SetupStep(name="a", status="ok", message=""),
                SetupStep(name="b", status="error", message="manquant"),
            ]
        )
        assert report.success is False


class TestCheckIncusAvailable:
    """Tests pour check_incus_available."""

    def test_incus_present(self):
        """Incus installé et fonctionnel → ok."""
        mock_result = MagicMock(returncode=0, stdout='[{"name":"default"}]')
        with (
            patch("anklume.engine.dev_setup.shutil.which", return_value="/usr/bin/incus"),
            patch("anklume.engine.dev_setup.subprocess.run", return_value=mock_result),
        ):
            result = check_incus_available()
        assert result.status == "ok"

    def test_incus_missing(self):
        """Incus absent → erreur."""
        with patch("anklume.engine.dev_setup.shutil.which", return_value=None):
            result = check_incus_available()
        assert result.status == "error"

    def test_incus_present_but_no_access(self):
        """Incus installé mais accès refusé → erreur."""
        mock_result = MagicMock(returncode=1, stderr="permission denied")
        with (
            patch("anklume.engine.dev_setup.shutil.which", return_value="/usr/bin/incus"),
            patch("anklume.engine.dev_setup.subprocess.run", return_value=mock_result),
        ):
            result = check_incus_available()
        assert result.status == "error"


class TestCheckDevDependencies:
    """Tests pour check_dev_dependencies."""

    def test_all_present(self):
        """Toutes les dépendances dev installées → ok."""
        with patch("anklume.engine.dev_setup.shutil.which") as mock_which:
            mock_which.side_effect = lambda b: (
                f"/usr/bin/{b}"
                if b
                in {
                    "ruff",
                    "ansible-playbook",
                }
                else None
            )
            results = check_dev_dependencies()

        # Au moins ruff doit être vérifié
        names = [r.name for r in results]
        assert "ruff" in names

    def test_ruff_missing(self):
        """ruff absent → warning."""
        with patch("anklume.engine.dev_setup.shutil.which", return_value=None):
            results = check_dev_dependencies()

        ruff_step = next(r for r in results if r.name == "ruff")
        assert ruff_step.status == "warning"


class TestCheckGitHooks:
    """Tests pour check_git_hooks."""

    def test_hook_present(self, tmp_path: Path):
        """Hook présent → ok."""
        hook = tmp_path / ".git" / "hooks" / "pre-commit"
        hook.parent.mkdir(parents=True)
        hook.write_text("#!/bin/sh\nexit 0\n")
        hook.chmod(0o755)

        result = check_git_hooks(tmp_path)
        assert result.status == "ok"

    def test_hook_missing(self, tmp_path: Path):
        """Hook absent → warning."""
        (tmp_path / ".git" / "hooks").mkdir(parents=True)

        result = check_git_hooks(tmp_path)
        assert result.status == "warning"

    def test_hook_not_executable(self, tmp_path: Path):
        """Hook présent mais pas exécutable → warning."""
        hook = tmp_path / ".git" / "hooks" / "pre-commit"
        hook.parent.mkdir(parents=True)
        hook.write_text("#!/bin/sh\nexit 0\n")
        hook.chmod(0o644)

        result = check_git_hooks(tmp_path)
        assert result.status == "warning"
        assert "exécutable" in result.message


class TestInstallGitHooks:
    """Tests pour install_git_hooks."""

    def test_install_creates_hook(self, tmp_path: Path):
        """L'installation crée le pre-commit hook."""
        hooks_dir = tmp_path / ".git" / "hooks"
        hooks_dir.mkdir(parents=True)

        # Créer un fichier source pour le hook
        source_hook = tmp_path / "hooks" / "pre-commit"
        source_hook.parent.mkdir(parents=True)
        source_hook.write_text("#!/bin/sh\nexit 0\n")

        result = install_git_hooks(tmp_path, source_hook)
        assert result.status == "ok"

        installed = hooks_dir / "pre-commit"
        assert installed.exists()
        assert installed.stat().st_mode & 0o111  # exécutable

    def test_install_skips_existing(self, tmp_path: Path):
        """L'installation skip si le hook existe déjà."""
        hooks_dir = tmp_path / ".git" / "hooks"
        hooks_dir.mkdir(parents=True)
        hook = hooks_dir / "pre-commit"
        hook.write_text("#!/bin/sh\ncustom hook\n")
        hook.chmod(0o755)

        result = install_git_hooks(tmp_path)
        assert result.skipped is True


class TestRunDevSetup:
    """Tests pour run_dev_setup (orchestration)."""

    def test_returns_report(self, tmp_path: Path):
        """run_dev_setup retourne un DevSetupReport."""
        (tmp_path / ".git" / "hooks").mkdir(parents=True)

        with (
            patch("anklume.engine.dev_setup.shutil.which", return_value="/usr/bin/incus"),
            patch("anklume.engine.dev_setup.subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0, stdout="[]")
            report = run_dev_setup(project_root=tmp_path)

        assert isinstance(report, DevSetupReport)
        assert len(report.steps) > 0

    def test_report_has_incus_check(self, tmp_path: Path):
        """Le rapport contient la vérification Incus."""
        (tmp_path / ".git" / "hooks").mkdir(parents=True)

        with (
            patch("anklume.engine.dev_setup.shutil.which", return_value="/usr/bin/incus"),
            patch("anklume.engine.dev_setup.subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0, stdout="[]")
            report = run_dev_setup(project_root=tmp_path)

        names = [s.name for s in report.steps]
        assert "Incus" in names

    def test_report_has_git_hooks_check(self, tmp_path: Path):
        """Le rapport contient la vérification des hooks git."""
        (tmp_path / ".git" / "hooks").mkdir(parents=True)

        with (
            patch("anklume.engine.dev_setup.shutil.which", return_value="/usr/bin/incus"),
            patch("anklume.engine.dev_setup.subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0, stdout="[]")
            report = run_dev_setup(project_root=tmp_path)

        names = [s.name for s in report.steps]
        assert "Hooks git" in names
