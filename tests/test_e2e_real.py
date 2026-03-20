"""Tests réels E2E — exécutés dans une VM KVM isolée.

Ces tests vérifient les interactions réelles avec Incus, nftables,
Ansible et les systèmes dépendants. Marqués @pytest.mark.real,
ils sont exécutés par `anklume dev test-real` dans une VM sandbox.

Prérequis (fournis par le rôle e2e_runner) :
- Incus installé et initialisé
- nftables actif
- Ansible installé
- uv + dépendances anklume
"""

from __future__ import annotations

import subprocess

import pytest

from anklume.cli._apply import run_apply
from anklume.engine.addressing import assign_addresses
from anklume.engine.incus_driver import IncusDriver
from anklume.engine.parser import parse_project
from anklume.engine.reconciler import reconcile

from .conftest import write_test_project
from .incus_helpers import (
    cleanup_project,
    incus_run,
    instance_exists,
    instance_status,
    network_exists,
    project_exists,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

E2E_PREFIX = "e2e-real"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def real_project(tmp_path, monkeypatch):
    """Projet anklume temporaire avec nettoyage Incus."""
    project_name = f"{E2E_PREFIX}-a"
    monkeypatch.chdir(tmp_path)
    cleanup_project(project_name)
    yield tmp_path, project_name
    cleanup_project(project_name)


@pytest.fixture()
def real_multi_project(tmp_path, monkeypatch):
    """Projet avec 2 domaines."""
    projects = [f"{E2E_PREFIX}-a", f"{E2E_PREFIX}-b"]
    monkeypatch.chdir(tmp_path)
    for p in projects:
        cleanup_project(p)
    yield tmp_path, projects
    for p in projects:
        cleanup_project(p)


@pytest.fixture()
def driver():
    """Driver Incus réel."""
    return IncusDriver()


# ===========================================================================
# 1. Driver Incus — CRUD réel
# ===========================================================================


@pytest.mark.real
class TestRealDriverCrud:
    """Driver Incus — commandes réelles de base."""

    def test_project_create_list_delete(self, driver):
        name = f"{E2E_PREFIX}-drv"
        cleanup_project(name)
        try:
            driver.project_create(name, description="Test driver")
            assert driver.project_exists(name)

            projects = driver.project_list()
            assert any(p.name == name for p in projects)
        finally:
            cleanup_project(name)

        assert not driver.project_exists(name)

    def test_network_create_list_delete(self, driver):
        proj = f"{E2E_PREFIX}-net"
        cleanup_project(proj)
        try:
            driver.project_create(proj)
            driver.network_create(
                "net-test",
                proj,
                config={
                    "ipv4.address": "10.200.50.1/24",
                    "ipv4.nat": "true",
                },
            )
            assert driver.network_exists("net-test", proj)
            nets = driver.network_list(proj)
            assert any(n.name == "net-test" for n in nets)
        finally:
            cleanup_project(proj)

    def test_instance_lifecycle(self, driver):
        proj = f"{E2E_PREFIX}-inst"
        cleanup_project(proj)
        try:
            driver.project_create(proj)
            driver.network_create(
                "net-inst",
                proj,
                config={
                    "ipv4.address": "10.200.51.1/24",
                    "ipv4.nat": "true",
                },
            )
            driver.instance_create(
                name="test-box",
                project=proj,
                image="images:debian/13",
                instance_type="container",
                network="net-inst",
            )
            instances = driver.instance_list(proj)
            assert any(i.name == "test-box" for i in instances)

            driver.instance_start("test-box", proj)
            instances = driver.instance_list(proj)
            box = next(i for i in instances if i.name == "test-box")
            assert box.status == "Running"

            driver.instance_stop("test-box", proj)
            instances = driver.instance_list(proj)
            box = next(i for i in instances if i.name == "test-box")
            assert box.status == "Stopped"
        finally:
            cleanup_project(proj)

    def test_instance_exec(self, driver):
        proj = f"{E2E_PREFIX}-exec"
        cleanup_project(proj)
        try:
            driver.project_create(proj)
            driver.network_create(
                "net-exec",
                proj,
                config={
                    "ipv4.address": "10.200.52.1/24",
                    "ipv4.nat": "true",
                },
            )
            driver.instance_create(
                name="exec-box",
                project=proj,
                image="images:debian/13",
                instance_type="container",
                network="net-exec",
            )
            driver.instance_start("exec-box", proj)
            result = driver.instance_exec("exec-box", proj, ["hostname"])
            assert result.returncode == 0
        finally:
            cleanup_project(proj)


# ===========================================================================
# 2. Snapshots — CRUD + rollback réel
# ===========================================================================


@pytest.mark.real
class TestRealSnapshots:
    """Snapshots — create, list, restore, rollback."""

    def test_snapshot_create_list_restore(self, driver):
        proj = f"{E2E_PREFIX}-snap"
        cleanup_project(proj)
        try:
            driver.project_create(proj)
            driver.network_create(
                "net-snap",
                proj,
                config={
                    "ipv4.address": "10.200.53.1/24",
                    "ipv4.nat": "true",
                },
            )
            driver.instance_create(
                name="snap-box",
                project=proj,
                image="images:debian/13",
                instance_type="container",
                network="net-snap",
            )
            driver.instance_start("snap-box", proj)

            # Créer un fichier témoin
            driver.instance_exec("snap-box", proj, ["touch", "/tmp/before-snap"])

            # Snapshot
            driver.snapshot_create("snap-box", proj, "test-snap")
            snaps = driver.snapshot_list("snap-box", proj)
            assert any(s.name == "test-snap" for s in snaps)

            # Modifier l'état
            driver.instance_exec("snap-box", proj, ["touch", "/tmp/after-snap"])

            # Restaurer
            driver.instance_stop("snap-box", proj)
            driver.snapshot_restore("snap-box", proj, "test-snap")
            driver.instance_start("snap-box", proj)

            # Le fichier après-snap n'existe plus (IncusError = returncode != 0)
            from anklume.engine.incus_driver import IncusError

            with pytest.raises(IncusError):
                driver.instance_exec(
                    "snap-box",
                    proj,
                    ["test", "-f", "/tmp/after-snap"],
                )

        finally:
            cleanup_project(proj)

    def test_rollback_deletes_later_snapshots(self, driver):
        """rollback_snapshot supprime les snapshots postérieurs."""
        from anklume.engine.snapshot import rollback_snapshot

        proj = f"{E2E_PREFIX}-roll"
        cleanup_project(proj)
        try:
            driver.project_create(proj)
            driver.network_create(
                "net-roll",
                proj,
                config={
                    "ipv4.address": "10.200.54.1/24",
                    "ipv4.nat": "true",
                },
            )
            driver.instance_create(
                name="roll-box",
                project=proj,
                image="images:debian/13",
                instance_type="container",
                network="net-roll",
            )
            driver.instance_start("roll-box", proj)

            # 3 snapshots séquentiels
            driver.snapshot_create("roll-box", proj, "snap-1")
            driver.snapshot_create("roll-box", proj, "snap-2")
            driver.snapshot_create("roll-box", proj, "snap-3")

            # Rollback vers snap-1 (supprime snap-2 et snap-3)
            rollback_snapshot(driver, "roll-box", proj, "snap-1")

            snaps = driver.snapshot_list("roll-box", proj)
            snap_names = {s.name for s in snaps}
            assert "snap-1" in snap_names
            assert "snap-2" not in snap_names
            assert "snap-3" not in snap_names

        finally:
            cleanup_project(proj)


# ===========================================================================
# 3. Réconciliateur — pipeline apply réel
# ===========================================================================


@pytest.mark.real
class TestRealReconciler:
    """Réconciliateur avec vrai Incus."""

    def test_apply_creates_resources(self, real_project):
        path, project_name = real_project
        write_test_project(
            path,
            {
                project_name: {
                    "description": "Test réel",
                    "trust_level": "semi-trusted",
                    "machines": {
                        "dev": {"description": "Test", "type": "lxc"},
                    },
                },
            },
        )

        run_apply(dry_run=False, no_provision=True)

        full_name = f"{project_name}-dev"
        assert project_exists(project_name)
        assert network_exists(f"net-{project_name}", project_name)
        assert instance_exists(full_name, project_name)
        assert instance_status(full_name, project_name) == "Running"

    def test_idempotence(self, real_project):
        path, project_name = real_project
        write_test_project(
            path,
            {
                project_name: {
                    "description": "Idempotence",
                    "trust_level": "semi-trusted",
                    "machines": {
                        "dev": {"description": "Test", "type": "lxc"},
                    },
                },
            },
        )

        run_apply(dry_run=False, no_provision=True)

        driver = IncusDriver()
        infra = parse_project(path)
        assign_addresses(infra)
        result = reconcile(infra, driver, dry_run=True)
        assert len(result.actions) == 0

    def test_restart_stopped_instance(self, real_project):
        path, project_name = real_project
        write_test_project(
            path,
            {
                project_name: {
                    "description": "Restart",
                    "trust_level": "semi-trusted",
                    "machines": {
                        "dev": {"description": "Test", "type": "lxc"},
                    },
                },
            },
        )

        full_name = f"{project_name}-dev"
        run_apply(dry_run=False, no_provision=True)
        assert instance_status(full_name, project_name) == "Running"

        incus_run(["stop", full_name, "--project", project_name])
        assert instance_status(full_name, project_name) == "Stopped"

        run_apply(dry_run=False, no_provision=True)
        assert instance_status(full_name, project_name) == "Running"


# ===========================================================================
# 4. Destroy — protection ephemeral
# ===========================================================================


@pytest.mark.real
class TestRealDestroy:
    """Destroy avec protection ephemeral."""

    def test_destroy_respects_protection(self, real_project):
        """Destroy sans --force n'efface pas les instances protégées."""
        from anklume.engine.destroy import destroy

        path, project_name = real_project
        write_test_project(
            path,
            {
                project_name: {
                    "description": "Protected",
                    "trust_level": "semi-trusted",
                    "machines": {
                        "safe": {"description": "Protected", "type": "lxc"},
                    },
                },
            },
        )
        run_apply(dry_run=False, no_provision=True)

        full_name = f"{project_name}-safe"
        assert instance_exists(full_name, project_name)

        # Destroy sans force — instance protégée reste
        driver = IncusDriver()
        infra = parse_project(path)
        assign_addresses(infra)
        destroy(infra, driver, force=False, dry_run=False)

        assert instance_exists(full_name, project_name)

    def test_destroy_force_removes_all(self, real_project):
        """Destroy --force supprime tout."""
        from anklume.engine.destroy import destroy

        path, project_name = real_project
        write_test_project(
            path,
            {
                project_name: {
                    "description": "Force",
                    "trust_level": "semi-trusted",
                    "machines": {
                        "dev": {"description": "Test", "type": "lxc"},
                    },
                },
            },
        )
        run_apply(dry_run=False, no_provision=True)

        driver = IncusDriver()
        infra = parse_project(path)
        assign_addresses(infra)
        destroy(infra, driver, force=True, dry_run=False)

        assert not project_exists(project_name)


# ===========================================================================
# 5. Status — déclaré vs réel
# ===========================================================================


@pytest.mark.real
class TestRealStatus:
    """Comparaison état déclaré vs état réel Incus."""

    def test_status_synced(self, real_project):
        from anklume.engine.status import compute_status

        path, project_name = real_project
        write_test_project(
            path,
            {
                project_name: {
                    "description": "Status",
                    "trust_level": "semi-trusted",
                    "machines": {
                        "dev": {"description": "Test", "type": "lxc"},
                    },
                },
            },
        )
        run_apply(dry_run=False, no_provision=True)

        driver = IncusDriver()
        infra = parse_project(path)
        assign_addresses(infra)
        status = compute_status(infra, driver)

        assert status.instances_total > 0
        for ds in status.domains:
            assert ds.project_exists
            assert ds.network_exists


# ===========================================================================
# 6. Nftables — déploiement et vérification
# ===========================================================================


@pytest.mark.real
class TestRealNftables:
    """Règles nftables — déploiement réel."""

    def test_deploy_and_verify_rules(self, real_multi_project):
        """Déployer les règles et vérifier avec nft list."""
        from anklume.engine.nftables import generate_ruleset

        path, projects = real_multi_project

        # 2 domaines avec une politique
        write_test_project(
            path,
            {
                projects[0]: {
                    "description": "Alpha",
                    "trust_level": "semi-trusted",
                    "machines": {"a": {"description": "A", "type": "lxc"}},
                },
                projects[1]: {
                    "description": "Beta",
                    "trust_level": "untrusted",
                    "machines": {"b": {"description": "B", "type": "lxc"}},
                },
            },
            policies=[
                {
                    "from": projects[0],
                    "to": projects[1],
                    "ports": [8080],
                    "description": "A accède à B port 8080",
                },
            ],
        )

        infra = parse_project(path)
        assign_addresses(infra)
        ruleset = generate_ruleset(infra)

        assert "table inet anklume" in ruleset
        assert "drop" in ruleset

        # Déployer via nft -f
        result = subprocess.run(
            ["nft", "-f", "-"],
            input=ruleset,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"nft -f a échoué : {result.stderr}"

        # Vérifier que la table existe
        verify = subprocess.run(
            ["nft", "list", "table", "inet", "anklume"],
            capture_output=True,
            text=True,
        )
        assert verify.returncode == 0
        assert "anklume" in verify.stdout

        # Cleanup nftables
        subprocess.run(
            ["nft", "delete", "table", "inet", "anklume"],
            capture_output=True,
        )


# ===========================================================================
# 7. Nesting — préfixes et injection de contexte
# ===========================================================================


@pytest.mark.real
class TestRealNesting:
    """Nesting — injection de fichiers de contexte dans les instances."""

    def test_context_files_injected(self, real_project):
        """Les fichiers /etc/anklume/ sont injectés après démarrage."""
        path, project_name = real_project
        write_test_project(
            path,
            {
                project_name: {
                    "description": "Nesting",
                    "trust_level": "semi-trusted",
                    "machines": {
                        "nested": {"description": "Nested", "type": "lxc"},
                    },
                },
            },
        )

        run_apply(dry_run=False, no_provision=True)

        full_name = f"{project_name}-nested"
        driver = IncusDriver()

        # Vérifier les fichiers de contexte
        for fname in ["absolute_level", "relative_level", "vm_nested", "yolo"]:
            result = driver.instance_exec(
                full_name,
                project_name,
                ["cat", f"/etc/anklume/{fname}"],
            )
            assert result.returncode == 0, f"Fichier manquant : /etc/anklume/{fname}"

        # Vérifier les valeurs (L0 crée des L1)
        result = driver.instance_exec(
            full_name,
            project_name,
            ["cat", "/etc/anklume/absolute_level"],
        )
        assert result.stdout.strip() == "1"


# ===========================================================================
# 8. Portal — transfert de fichiers
# ===========================================================================


@pytest.mark.real
class TestRealPortal:
    """Transfert de fichiers hôte ↔ conteneur."""

    def test_push_pull_file(self, real_project, tmp_path, driver):
        path, project_name = real_project
        write_test_project(
            path,
            {
                project_name: {
                    "description": "Portal",
                    "trust_level": "semi-trusted",
                    "machines": {
                        "box": {"description": "Box", "type": "lxc"},
                    },
                },
            },
        )
        run_apply(dry_run=False, no_provision=True)

        full_name = f"{project_name}-box"

        # Créer un fichier local
        local_file = tmp_path / "test-file.txt"
        local_file.write_text("contenu de test")

        # Push
        driver.file_push(full_name, project_name, str(local_file), "/root/test-file.txt")

        # Vérifier dans le conteneur
        result = driver.instance_exec(
            full_name,
            project_name,
            ["cat", "/root/test-file.txt"],
        )
        assert "contenu de test" in result.stdout

        # Pull
        pulled = tmp_path / "pulled.txt"
        driver.file_pull(full_name, project_name, "/root/test-file.txt", str(pulled))
        assert pulled.read_text().strip() == "contenu de test"


# ===========================================================================
# 9. Disposable — conteneurs jetables
# ===========================================================================


@pytest.mark.real
class TestRealDisposable:
    """Conteneurs jetables — lancement et cleanup."""

    def test_launch_and_cleanup(self, driver):
        from anklume.engine.disposable import (
            cleanup_disposables,
            launch_disposable,
            list_disposables,
        )

        container = launch_disposable(driver, "images:debian/13")
        assert container.name.startswith("disp-")

        disps = list_disposables(driver)
        assert any(d.name == container.name for d in disps)

        cleanup_disposables(driver)
        disps = list_disposables(driver)
        assert not any(d.name == container.name for d in disps)


# ===========================================================================
# 10. Golden images — publish/list/delete
# ===========================================================================


@pytest.mark.real
class TestRealGolden:
    """Golden images — cycle complet."""

    def test_create_list_delete(self, driver, tmp_path, monkeypatch):
        proj = f"{E2E_PREFIX}-g"
        cleanup_project(proj)
        try:
            monkeypatch.chdir(tmp_path)
            write_test_project(
                tmp_path,
                {
                    proj: {
                        "description": "Golden",
                        "trust_level": "semi-trusted",
                        "machines": {
                            "box": {"description": "Golden box", "type": "lxc"},
                        },
                    },
                },
            )
            run_apply(dry_run=False, no_provision=True)

            full_name = f"{proj}-box"
            infra = parse_project(tmp_path)
            assign_addresses(infra)

            from anklume.engine.golden import create_golden, delete_golden, list_golden

            # Publier
            img = create_golden(driver, infra, full_name)
            assert img.alias.startswith("golden/")

            # Lister
            images = list_golden(driver)
            assert any(i.alias == img.alias for i in images)

            # Supprimer
            delete_golden(driver, img.alias)
            images = list_golden(driver)
            assert not any(i.alias == img.alias for i in images)

        finally:
            cleanup_project(proj)


# ===========================================================================
# 11. Import infrastructure
# ===========================================================================


@pytest.mark.real
class TestRealImport:
    """Import d'une infrastructure Incus existante."""

    def test_scan_generates_domains(self, real_project, tmp_path):
        path, project_name = real_project
        write_test_project(
            path,
            {
                project_name: {
                    "description": "Import",
                    "trust_level": "semi-trusted",
                    "machines": {
                        "dev": {"description": "Dev", "type": "lxc"},
                    },
                },
            },
        )
        run_apply(dry_run=False, no_provision=True)

        from anklume.engine.import_infra import scan_incus

        driver = IncusDriver()
        scanned = scan_incus(driver)

        # Le projet e2e-real-a doit être détecté
        scanned_names = [d.project for d in scanned]
        assert project_name in scanned_names


# ===========================================================================
# 12. Doctor — diagnostic réel
# ===========================================================================


@pytest.mark.real
class TestRealDoctor:
    """Diagnostic sur un système réel."""

    def test_doctor_checks_incus(self):
        from anklume.engine.doctor import run_doctor

        report = run_doctor()
        # Incus est installé dans la VM
        incus_check = next(
            (c for c in report.checks if c.name == "Incus"),
            None,
        )
        assert incus_check is not None
        assert incus_check.status == "ok"


# ===========================================================================
# 13. Network status — bridges et nftables
# ===========================================================================


@pytest.mark.real
class TestRealNetworkStatus:
    """État réseau réel."""

    def test_network_status_after_apply(self, real_project):
        from anklume.engine.ops import compute_network_status

        path, project_name = real_project
        write_test_project(
            path,
            {
                project_name: {
                    "description": "Network",
                    "trust_level": "semi-trusted",
                    "machines": {
                        "dev": {"description": "Dev", "type": "lxc"},
                    },
                },
            },
        )
        run_apply(dry_run=False, no_provision=True)

        driver = IncusDriver()
        infra = parse_project(path)
        assign_addresses(infra)
        status = compute_network_status(infra, driver)

        assert len(status.networks) > 0


# ===========================================================================
# 14. Provisioner Ansible — rôle base réel
# ===========================================================================


@pytest.mark.real
class TestRealProvisioner:
    """Provisioning Ansible réel (rôle base)."""

    def test_provision_installs_base_packages(self, real_project):
        path, project_name = real_project
        write_test_project(
            path,
            {
                project_name: {
                    "description": "Provision",
                    "trust_level": "semi-trusted",
                    "machines": {
                        "prov": {
                            "description": "Provisioned",
                            "type": "lxc",
                            "roles": ["base"],
                        },
                    },
                },
            },
        )

        # Apply avec provisioning
        run_apply(dry_run=False, no_provision=False)

        full_name = f"{project_name}-prov"
        driver = IncusDriver()

        # Vérifier que curl est installé (rôle base)
        result = driver.instance_exec(
            full_name,
            project_name,
            ["which", "curl"],
        )
        assert result.returncode == 0


# ===========================================================================
# 15. Console tmux
# ===========================================================================


@pytest.mark.real
class TestRealConsole:
    """Console tmux — création de session."""

    def test_build_console_config(self, real_project):
        from anklume.engine.console import build_console_config

        path, project_name = real_project
        write_test_project(
            path,
            {
                project_name: {
                    "description": "Console",
                    "trust_level": "semi-trusted",
                    "machines": {
                        "dev": {"description": "Dev", "type": "lxc"},
                    },
                },
            },
        )
        run_apply(dry_run=False, no_provision=True)

        driver = IncusDriver()
        infra = parse_project(path)
        assign_addresses(infra)
        config = build_console_config(infra, driver)

        all_panes = [p for panes in config.windows.values() for p in panes]
        assert len(all_panes) > 0
        assert any(project_name in p.domain for p in all_panes)


# ===========================================================================
# 16. Showcase — cycle complet (init → apply → status → destroy)
# ===========================================================================


@pytest.mark.real
class TestRealShowcase:
    """Reproduit le test Phase 25a : showcase complet dans un environnement réel."""

    @pytest.fixture()
    def showcase_project(self, tmp_path, monkeypatch):
        """Crée un mini-showcase (2 domaines, 4 instances) adapté à la VM."""
        monkeypatch.chdir(tmp_path)
        project_dir = tmp_path / "mini-showcase"

        # Mini-showcase : 2 domaines LXC, pas de GPU, pas de GUI, pas de VM
        write_test_project(
            project_dir,
            {
                "e2e-sc-a": {
                    "description": "Mini-showcase alpha (trusted)",
                    "trust_level": "trusted",
                    "machines": {
                        "web": {"description": "Serveur web", "type": "lxc"},
                        "db": {"description": "Base de données", "type": "lxc"},
                    },
                },
                "e2e-sc-b": {
                    "description": "Mini-showcase beta (disposable)",
                    "trust_level": "disposable",
                    "ephemeral": True,
                    "machines": {
                        "browser": {"description": "Navigation jetable", "type": "lxc"},
                        "tools": {"description": "Outils éphémères", "type": "lxc"},
                    },
                },
            },
            policies=[
                {
                    "description": "Alpha → Beta SSH",
                    "from": "e2e-sc-a",
                    "to": "e2e-sc-b",
                    "ports": [22],
                },
            ],
        )
        monkeypatch.chdir(project_dir)

        yield project_dir

        # Cleanup
        for proj in ("e2e-sc-a", "e2e-sc-b"):
            cleanup_project(proj)

    def test_showcase_apply_and_status(self, showcase_project):
        """Déploie le mini-showcase, vérifie le status."""
        from anklume.engine.status import compute_status

        run_apply(dry_run=False, no_provision=True)

        infra = parse_project(showcase_project)
        assign_addresses(infra)
        driver = IncusDriver()
        status = compute_status(infra, driver)

        for ds in status.domains:
            assert ds.project_exists, f"Projet manquant : {ds.domain_name}"
            assert ds.network_exists, f"Réseau manquant : {ds.domain_name}"

        running_count = sum(
            1
            for ds in status.domains
            for inst in ds.instances
            if inst.state == "Running"
        )
        assert running_count == 4, f"{running_count}/4 instances running"

    def test_showcase_snapshot_cycle(self, showcase_project):
        """Create, list, restore un snapshot."""
        from anklume.engine.snapshot import create_snapshot, restore_snapshot

        run_apply(dry_run=False, no_provision=True)

        driver = IncusDriver()
        infra = parse_project(showcase_project)
        assign_addresses(infra)

        first_domain = infra.enabled_domains[0]
        first_machine = next(iter(first_domain.machines.values()))
        instance_name = first_machine.full_name
        project_name = first_domain.name

        create_snapshot(driver, instance_name, project_name, name="test-snap")
        snaps = driver.snapshot_list(instance_name, project_name)
        assert "test-snap" in [s.name for s in snaps]
        restore_snapshot(driver, instance_name, project_name, "test-snap")

    def test_showcase_destroy_respects_protection(self, showcase_project):
        """destroy sans --force ne supprime que les éphémères."""
        from anklume.engine.destroy import destroy

        run_apply(dry_run=False, no_provision=True)

        driver = IncusDriver()
        infra = parse_project(showcase_project)
        assign_addresses(infra)

        # Destroy sans force : seules les éphémères (beta) sont supprimées
        result = destroy(infra, driver, force=False)
        assert len(result.skipped) > 0, "Aucune instance protégée ?"

        # Destroy avec force : tout est nettoyé
        result = destroy(infra, driver, force=True)
        assert len(result.errors) == 0
