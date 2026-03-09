"""Tests pour engine/doctor.py — diagnostic automatique."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from anklume.engine.doctor import (
    CheckResult,
    DoctorReport,
    check_ansible,
    check_domains,
    check_golden,
    check_gpu,
    check_incus,
    check_networks,
    check_nftables,
    run_doctor,
)
from anklume.engine.incus_driver import IncusImage, IncusProject
from tests.conftest import make_domain, make_infra, make_machine, mock_driver


class TestCheckResult:
    """Tests pour la dataclass CheckResult."""

    def test_ok_result(self):
        """Résultat ok."""
        r = CheckResult(name="test", status="ok", message="tout va bien")
        assert r.status == "ok"
        assert r.fix_command is None

    def test_error_with_fix(self):
        """Résultat erreur avec commande de correction."""
        r = CheckResult(
            name="test",
            status="error",
            message="bridge absent",
            fix_command="anklume apply",
        )
        assert r.status == "error"
        assert r.fix_command == "anklume apply"


class TestDoctorReport:
    """Tests pour DoctorReport."""

    def test_counts(self):
        """Comptage par statut."""
        report = DoctorReport(
            checks=[
                CheckResult(name="a", status="ok", message=""),
                CheckResult(name="b", status="ok", message=""),
                CheckResult(name="c", status="warning", message=""),
                CheckResult(name="d", status="error", message=""),
            ]
        )
        assert report.ok_count == 2
        assert report.warning_count == 1
        assert report.error_count == 1

    def test_empty_report(self):
        """Rapport vide."""
        report = DoctorReport(checks=[])
        assert report.ok_count == 0
        assert report.warning_count == 0
        assert report.error_count == 0


class TestCheckIncus:
    """Tests pour check_incus."""

    def test_incus_present(self):
        """Incus installé → ok."""
        with patch("anklume.engine.doctor.shutil.which", return_value="/usr/bin/incus"):
            result = check_incus()
        assert result.status == "ok"

    def test_incus_missing(self):
        """Incus absent → erreur."""
        with patch("anklume.engine.doctor.shutil.which", return_value=None):
            result = check_incus()
        assert result.status == "error"


class TestCheckNftables:
    """Tests pour check_nftables."""

    def test_nft_present(self):
        """nftables installé → ok."""
        with patch("anklume.engine.doctor.shutil.which", return_value="/usr/sbin/nft"):
            result = check_nftables()
        assert result.status == "ok"

    def test_nft_missing(self):
        """nftables absent → error."""
        with patch("anklume.engine.doctor.shutil.which", return_value=None):
            result = check_nftables()
        assert result.status == "error"


class TestCheckAnsible:
    """Tests pour check_ansible."""

    def test_ansible_present(self):
        """Ansible installé → ok."""
        with patch("anklume.engine.doctor.shutil.which", return_value="/usr/bin/ansible-playbook"):
            result = check_ansible()
        assert result.status == "ok"

    def test_ansible_missing(self):
        """Ansible absent → warning."""
        with patch("anklume.engine.doctor.shutil.which", return_value=None):
            result = check_ansible()
        assert result.status == "warning"


class TestCheckGpu:
    """Tests pour check_gpu."""

    def test_gpu_present(self):
        """GPU détecté → ok."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "NVIDIA RTX PRO 5000"
        with patch("anklume.engine.doctor.subprocess.run", return_value=mock_result):
            result = check_gpu()
        assert result.status == "ok"

    def test_gpu_missing(self):
        """GPU absent → warning (pas une erreur, optionnel)."""
        with patch("anklume.engine.doctor.subprocess.run", side_effect=FileNotFoundError):
            result = check_gpu()
        assert result.status == "warning"


class TestCheckDomains:
    """Tests pour check_domains."""

    def test_valid_domains(self):
        """Domaines valides → ok."""
        domain = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro")},
        )
        infra = make_infra(domains={"pro": domain})

        results = check_domains(infra)

        assert len(results) == 1
        assert results[0].status == "ok"

    def test_empty_infra(self):
        """Infra sans domaines → warning."""
        infra = make_infra(domains={})

        results = check_domains(infra)

        assert len(results) == 1
        assert results[0].status == "warning"


class TestCheckNetworks:
    """Tests pour check_networks."""

    def test_network_exists(self):
        """Bridge existant → ok."""
        domain = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro")},
            subnet="10.100.20.0/24",
        )
        infra = make_infra(domains={"pro": domain})
        driver = mock_driver(projects=[IncusProject(name="pro")])
        driver.network_exists.side_effect = None
        driver.network_exists.return_value = True

        results = check_networks(infra, driver)

        assert len(results) == 1
        assert results[0].status == "ok"

    def test_network_missing(self):
        """Bridge absent → warning."""
        domain = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro")},
            subnet="10.100.20.0/24",
        )
        infra = make_infra(domains={"pro": domain})
        driver = mock_driver(projects=[IncusProject(name="pro")])
        driver.network_exists.side_effect = None
        driver.network_exists.return_value = False

        results = check_networks(infra, driver)

        assert len(results) == 1
        assert results[0].status == "warning"
        assert results[0].fix_command is not None


class TestCheckGolden:
    """Tests pour check_golden."""

    def test_golden_images_present(self):
        """Golden images détectées → ok."""
        driver = mock_driver()
        driver.image_list.return_value = [
            IncusImage(fingerprint="aaa", aliases=["golden/pro-dev"], size=100),
        ]

        result = check_golden(driver)

        assert result.status == "ok"

    def test_no_golden_images(self):
        """Aucune golden image → ok (c'est optionnel)."""
        driver = mock_driver()
        driver.image_list.return_value = []

        result = check_golden(driver)

        assert result.status == "ok"


class TestRunDoctor:
    """Tests pour run_doctor (orchestration)."""

    def test_run_returns_report(self):
        """run_doctor retourne un DoctorReport."""
        driver = mock_driver()
        driver.image_list.return_value = []
        infra = make_infra(domains={})

        with patch("anklume.engine.doctor.shutil.which", return_value="/usr/bin/incus"):
            with patch("anklume.engine.doctor.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="GPU OK")
                report = run_doctor(driver=driver, infra=infra)

        assert isinstance(report, DoctorReport)
        assert len(report.checks) > 0

    def test_run_without_infra(self):
        """run_doctor fonctionne sans infra (checks système uniquement)."""
        with patch("anklume.engine.doctor.shutil.which", return_value="/usr/bin/incus"):
            with patch("anklume.engine.doctor.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="GPU OK")
                report = run_doctor()

        assert isinstance(report, DoctorReport)
        # Au minimum les checks système (incus, nft, ansible, gpu)
        assert len(report.checks) >= 4
