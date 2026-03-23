"""Tests E2E — vérifient le pipeline complet contre le vrai Incus.

Ces tests créent de vraies ressources Incus (projets, réseaux, instances)
avec le préfixe `e2e-` pour éviter les conflits. Nettoyage automatique.

Prérequis : Incus installé et configuré sur l'hôte.
"""

import os

import pytest
import yaml

from anklume.cli._apply import run_apply
from anklume.cli._init import run_init, run_init_showcase
from anklume.engine.addressing import assign_addresses
from anklume.engine.incus_driver import IncusDriver
from anklume.engine.parser import parse_project
from anklume.engine.reconciler import reconcile

from .conftest import write_test_project
from .incus_helpers import (
    cleanup_project,
    instance_config_get,
    instance_exists,
    instance_status,
    network_exists,
    project_exists,
)


@pytest.fixture()
def e2e_project(tmp_path, monkeypatch):
    """Crée un projet anklume temporaire et nettoie Incus après."""
    project_name = "e2e-alpha"
    monkeypatch.chdir(tmp_path)

    # Nettoyage préventif
    cleanup_project(project_name)

    yield tmp_path, project_name

    # Nettoyage post-test
    cleanup_project(project_name)


@pytest.fixture()
def e2e_multi_project(tmp_path, monkeypatch):
    """Crée un projet anklume avec 2 domaines et nettoie après."""
    projects = ["e2e-alpha", "e2e-beta"]
    monkeypatch.chdir(tmp_path)

    for p in projects:
        cleanup_project(p)

    yield tmp_path, projects

    for p in projects:
        cleanup_project(p)


class TestE2EApplyAll:
    """Pipeline complet : apply all crée les ressources dans Incus."""

    def test_creates_project_network_instance(self, e2e_project):
        path, project_name = e2e_project
        write_test_project(
            path,
            {
                project_name: {
                    "description": "E2E test domain",
                    "trust_level": "semi-trusted",
                    "machines": {
                        "dev": {"description": "E2E dev", "type": "lxc"},
                    },
                },
            },
        )

        run_apply(dry_run=False)

        full_name = f"{project_name}-dev"
        assert project_exists(project_name)
        assert network_exists(f"net-{project_name}", project_name)
        assert instance_exists(full_name, project_name)
        assert instance_status(full_name, project_name) == "Running"

    def test_protection_delete_set(self, e2e_project):
        path, project_name = e2e_project
        write_test_project(
            path,
            {
                project_name: {
                    "description": "E2E test",
                    "trust_level": "semi-trusted",
                    "machines": {
                        "protected": {"description": "Protected", "type": "lxc"},
                    },
                },
            },
        )

        run_apply(dry_run=False)

        full_name = f"{project_name}-protected"
        val = instance_config_get(full_name, project_name, "security.protection.delete")
        assert val == "true"

    def test_ephemeral_no_protection(self, e2e_project):
        path, project_name = e2e_project
        write_test_project(
            path,
            {
                project_name: {
                    "description": "E2E test",
                    "trust_level": "semi-trusted",
                    "ephemeral": True,
                    "machines": {
                        "tmp": {"description": "Ephemeral", "type": "lxc"},
                    },
                },
            },
        )

        run_apply(dry_run=False)

        full_name = f"{project_name}-tmp"
        val = instance_config_get(full_name, project_name, "security.protection.delete")
        assert val != "true"


class TestE2EIdempotence:
    """Apply deux fois produit le même résultat."""

    def test_second_apply_no_changes(self, e2e_project):
        path, project_name = e2e_project
        write_test_project(
            path,
            {
                project_name: {
                    "description": "E2E idempotence",
                    "trust_level": "semi-trusted",
                    "machines": {
                        "dev": {"description": "E2E dev", "type": "lxc"},
                    },
                },
            },
        )

        # Premier apply
        run_apply(dry_run=False)
        assert instance_status(f"{project_name}-dev", project_name) == "Running"

        # Second apply — doit être idempotent
        driver = IncusDriver()

        infra = parse_project(path)
        assign_addresses(infra)
        result = reconcile(infra, driver, dry_run=True)

        assert len(result.actions) == 0, (
            f"Le second apply devrait ne rien faire, mais planifie : "
            f"{[a.detail for a in result.actions]}"
        )


class TestE2EDryRun:
    """Dry-run ne crée rien dans Incus."""

    def test_dry_run_creates_nothing(self, e2e_project):
        path, project_name = e2e_project
        write_test_project(
            path,
            {
                project_name: {
                    "description": "E2E dry-run",
                    "trust_level": "semi-trusted",
                    "machines": {
                        "dev": {"description": "E2E dev", "type": "lxc"},
                    },
                },
            },
        )

        run_apply(dry_run=True)

        assert not project_exists(project_name)


class TestE2EApplyDomain:
    """Apply domain ne déploie qu'un seul domaine."""

    def test_only_specified_domain(self, e2e_multi_project):
        path, projects = e2e_multi_project
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
                    "trust_level": "semi-trusted",
                    "machines": {"b": {"description": "B", "type": "lxc"}},
                },
            },
        )

        run_apply(domain_name=projects[0], dry_run=False)

        assert project_exists(projects[0])
        assert not project_exists(projects[1])


class TestE2EStoppedInstance:
    """Une instance arrêtée est redémarrée par apply."""

    def test_restarts_stopped_instance(self, e2e_project):
        path, project_name = e2e_project
        write_test_project(
            path,
            {
                project_name: {
                    "description": "E2E restart",
                    "trust_level": "semi-trusted",
                    "machines": {
                        "dev": {"description": "E2E dev", "type": "lxc"},
                    },
                },
            },
        )

        full_name = f"{project_name}-dev"

        # Premier apply
        run_apply(dry_run=False)
        assert instance_status(full_name, project_name) == "Running"

        # Arrêter l'instance manuellement
        from .incus_helpers import incus_run

        incus_run(["stop", full_name, "--project", project_name])
        assert instance_status(full_name, project_name) == "Stopped"

        # Second apply — doit redémarrer
        run_apply(dry_run=False)
        assert instance_status(full_name, project_name) == "Running"


@pytest.fixture()
def e2e_workflow(tmp_path, monkeypatch):
    """Crée un projet via anklume init et nettoie après."""
    project_name = "e2e-wflow"
    monkeypatch.chdir(tmp_path)
    cleanup_project(project_name)

    yield tmp_path, project_name

    cleanup_project(project_name)


class TestE2EDevWorkflow:
    """Workflow complet : init → configurer → apply → vérifier."""

    def test_init_configure_apply(self, e2e_workflow):
        path, project_name = e2e_workflow
        project_dir = path / "infra"

        # 1. anklume init
        run_init(str(project_dir))

        # 2. Changer le base d'adressage pour éviter conflit avec l'infra réelle
        anklume_yml = yaml.safe_load((project_dir / "anklume.yml").read_text())
        anklume_yml["addressing"]["base"] = "10.200"
        (project_dir / "anklume.yml").write_text(yaml.dump(anklume_yml))

        # 3. Remplacer le domaine par défaut par un nom E2E-safe
        (project_dir / "domains" / "pro.yml").unlink()
        (project_dir / "domains" / f"{project_name}.yml").write_text(
            yaml.dump(
                {
                    "description": "E2E workflow test",
                    "trust_level": "semi-trusted",
                    "machines": {
                        "dev": {"description": "Development", "type": "lxc"},
                    },
                }
            )
        )

        # 4. Apply depuis le répertoire projet
        os.chdir(project_dir)
        run_apply(dry_run=False)

        # 5. Vérifier les ressources Incus
        full_name = f"{project_name}-dev"
        assert project_exists(project_name)
        assert network_exists(f"net-{project_name}", project_name)
        assert instance_exists(full_name, project_name)
        assert instance_status(full_name, project_name) == "Running"

        # 6. Idempotence — second apply ne change rien
        driver = IncusDriver()
        infra = parse_project(project_dir)
        assign_addresses(infra)
        result = reconcile(infra, driver, dry_run=True)
        assert len(result.actions) == 0, (
            f"Second apply devrait être idempotent : {[a.detail for a in result.actions]}"
        )


class TestE2EImportRoundtrip:
    """Roundtrip : deploy → import → comparer la structure.

    Vérifie que ``anklume setup import`` reconstruit correctement
    la structure (machines, types, réseau) depuis Incus.

    Limitations connues de l'import (non vérifiées ici) :
    - Rôles Ansible, descriptions originales, trust level, vars, weight
    """

    def test_import_matches_deployed_structure(self, e2e_project):
        from anklume.engine.import_infra import import_infrastructure

        path, project_name = e2e_project
        write_test_project(
            path,
            {
                project_name: {
                    "description": "E2E import roundtrip",
                    "trust_level": "semi-trusted",
                    "machines": {
                        "web": {"description": "Web server", "type": "lxc"},
                        "db": {"description": "Database", "type": "lxc"},
                    },
                },
            },
        )

        # 1. Déployer
        run_apply(dry_run=False)
        assert instance_status(f"{project_name}-web", project_name) == "Running"
        assert instance_status(f"{project_name}-db", project_name) == "Running"

        # 2. Importer dans un répertoire séparé
        import_dir = path / "imported"
        driver = IncusDriver()
        result = import_infrastructure(driver, import_dir)

        # 3. Trouver le domaine importé
        imported = next((d for d in result.domains if d.project == project_name), None)
        assert imported is not None, (
            f"Domaine {project_name} absent de l'import. "
            f"Trouvés : {[d.project for d in result.domains]}"
        )

        # 4. Vérifier la structure
        imported_names = {inst.name.removeprefix(f"{project_name}-") for inst in imported.instances}
        assert imported_names == {"web", "db"}

        # 5. Vérifier les types (tous LXC)
        for inst in imported.instances:
            assert inst.instance_type == "container"

        # 6. Vérifier le réseau
        assert imported.network == f"net-{project_name}"

        # 7. Vérifier le fichier YAML généré
        yml_path = import_dir / "domains" / f"{project_name}.yml"
        assert yml_path.is_file()
        content = yaml.safe_load(yml_path.read_text())
        assert set(content["machines"].keys()) == {"web", "db"}
        for m in content["machines"].values():
            assert m["type"] == "lxc"


# ===========================================================================
# Tests showcase — pipeline dry-run complet (pas de vrai Incus)
# ===========================================================================


class TestShowcaseDryRun:
    """Valide le template showcase à travers tout le pipeline sans Incus."""

    @pytest.fixture(autouse=True)
    def _setup_showcase(self, tmp_path, monkeypatch):
        """Initialise un projet showcase dans un répertoire temporaire."""
        monkeypatch.chdir(tmp_path)
        run_init_showcase(str(tmp_path / "showcase"))
        monkeypatch.chdir(tmp_path / "showcase")
        self.path = tmp_path / "showcase"

    def test_init_creates_files(self):
        assert (self.path / "anklume.yml").is_file()
        assert (self.path / "policies.yml").is_file()
        domain_files = list((self.path / "domains").glob("*.yml"))
        assert len(domain_files) >= 5  # vault, pro, perso, ai-tools, sandbox, gaming

    def test_parse_succeeds(self):
        infra = parse_project(self.path)
        assert len(infra.domains) >= 5
        assert "vault" in infra.domains
        assert "pro" in infra.domains

    def test_validate_succeeds(self):
        from anklume.engine.validator import validate

        infra = parse_project(self.path)
        result = validate(infra)
        assert result.valid, f"Validation échouée : {result}"

    def test_addressing_assigns_ips(self):
        from anklume.engine.addressing import assign_addresses

        infra = parse_project(self.path)
        assign_addresses(infra)
        for domain in infra.enabled_domains:
            assert domain.subnet is not None
            assert domain.gateway is not None
            for machine in domain.machines.values():
                assert machine.ip is not None

    def test_nftables_generates_ruleset(self):
        from anklume.engine.addressing import assign_addresses
        from anklume.engine.nftables import generate_ruleset

        infra = parse_project(self.path)
        assign_addresses(infra)
        ruleset = generate_ruleset(infra)
        assert "policy drop" in ruleset
        assert "intra-domaine" in ruleset
        assert "inter-domaines" in ruleset

    def test_dry_run_produces_plan(self):
        """apply --dry-run réussit et produit un plan non-vide."""
        from anklume.engine.addressing import assign_addresses
        from anklume.engine.reconciler import reconcile
        from anklume.engine.validator import validate
        from tests.conftest import mock_driver

        infra = parse_project(self.path)
        result = validate(infra)
        assert result.valid

        assign_addresses(infra)

        driver = mock_driver()
        result = reconcile(infra, driver=driver, dry_run=True)
        assert len(result.actions) > 0

    def test_all_trust_levels_present(self):
        infra = parse_project(self.path)
        trust_levels = {d.trust_level for d in infra.domains.values()}
        assert "admin" in trust_levels
        assert "trusted" in trust_levels
        assert "semi-trusted" in trust_levels
        assert "disposable" in trust_levels

    def test_policies_parsed(self):
        infra = parse_project(self.path)
        assert len(infra.policies) >= 5  # showcase a ~10 policies
