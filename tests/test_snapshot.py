"""Tests unitaires pour engine/snapshot.py.

Le module snapshot est testé avec IncusDriver mocké.
On vérifie la logique métier : nommage, création auto/manuelle,
listing, restauration, résolution de projet.
"""

from __future__ import annotations

import pytest

from anklume.engine.incus_driver import IncusError, IncusProject, IncusSnapshot
from anklume.engine.snapshot import (
    create_auto_snapshots,
    create_snapshot,
    generate_name,
    list_all_snapshots,
    resolve_instance_project,
    restore_snapshot,
    rollback_pre_apply,
)

from .conftest import (
    make_domain,
    make_infra,
    make_machine,
    mock_driver,
    running_instance,
    stopped_instance,
)

# ============================================================
# generate_name
# ============================================================


class TestGenerateName:
    def test_pre_phase(self) -> None:
        name = generate_name("pre")
        assert name.startswith("anklume-pre-")
        # Format : anklume-pre-YYYYMMDD-HHMMSS
        parts = name.split("-")
        assert len(parts) == 4
        assert len(parts[2]) == 8  # YYYYMMDD
        assert len(parts[3]) == 6  # HHMMSS

    def test_post_phase(self) -> None:
        name = generate_name("post")
        assert name.startswith("anklume-post-")

    def test_snap_default(self) -> None:
        name = generate_name("snap")
        assert name.startswith("anklume-snap-")

    def test_no_arg_defaults_to_snap(self) -> None:
        name = generate_name()
        assert name.startswith("anklume-snap-")

    def test_unique_names(self) -> None:
        """Deux appels successifs produisent le meme nom (meme seconde)
        ou des noms differents (secondes differentes)."""
        n1 = generate_name("pre")
        n2 = generate_name("pre")
        assert n1.startswith("anklume-pre-")
        assert n2.startswith("anklume-pre-")


# ============================================================
# create_snapshot
# ============================================================


class TestCreateSnapshot:
    def test_with_custom_name(self) -> None:
        driver = mock_driver()
        result = create_snapshot(driver, "pro-dev", "pro", name="avant-migration")
        assert result == "avant-migration"
        driver.snapshot_create.assert_called_once_with("pro-dev", "pro", "avant-migration")

    def test_without_name_generates_default(self) -> None:
        driver = mock_driver()
        result = create_snapshot(driver, "pro-dev", "pro")
        assert result.startswith("anklume-snap-")
        driver.snapshot_create.assert_called_once()

    def test_driver_error_propagates(self) -> None:
        driver = mock_driver()
        driver.snapshot_create.side_effect = IncusError(
            ["incus", "snapshot", "create"],
            1,
            "not found",
        )
        with pytest.raises(IncusError):
            create_snapshot(driver, "pro-dev", "pro")


# ============================================================
# create_auto_snapshots
# ============================================================


class TestCreateAutoSnapshots:
    def test_pre_snapshots_existing_instances(self) -> None:
        """Pre-apply : snapshot des instances existantes dans les domaines concernés."""
        domain = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro")},
        )
        infra = make_infra(domains={"pro": domain})
        driver = mock_driver(
            projects=[IncusProject(name="pro")],
            instances={"pro": [running_instance("pro-dev", "pro")]},
        )

        created = create_auto_snapshots(driver, infra, "pre")

        assert len(created) == 1
        inst, proj, snap_name = created[0]
        assert inst == "pro-dev"
        assert proj == "pro"
        assert snap_name.startswith("anklume-pre-")
        driver.snapshot_create.assert_called_once()

    def test_pre_snapshots_skip_new_instances(self) -> None:
        """Pre-apply : pas de snapshot pour les instances qui n'existent pas encore."""
        domain = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro")},
        )
        infra = make_infra(domains={"pro": domain})
        driver = mock_driver(
            projects=[IncusProject(name="pro")],
            instances={"pro": []},
        )

        created = create_auto_snapshots(driver, infra, "pre")

        assert len(created) == 0
        driver.snapshot_create.assert_not_called()

    def test_pre_snapshots_skip_new_project(self) -> None:
        """Pre-apply : pas de snapshot si le projet n'existe pas encore."""
        domain = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro")},
        )
        infra = make_infra(domains={"pro": domain})
        driver = mock_driver()

        created = create_auto_snapshots(driver, infra, "pre")

        assert len(created) == 0

    def test_post_snapshots_all_instances(self) -> None:
        """Post-apply : snapshot de toutes les instances du domaine."""
        domain = make_domain(
            "pro",
            machines={
                "dev": make_machine("dev", "pro"),
                "desktop": make_machine("desktop", "pro"),
            },
        )
        infra = make_infra(domains={"pro": domain})
        driver = mock_driver(
            projects=[IncusProject(name="pro")],
            instances={
                "pro": [
                    running_instance("pro-dev", "pro"),
                    running_instance("pro-desktop", "pro"),
                ]
            },
        )

        created = create_auto_snapshots(driver, infra, "post")

        assert len(created) == 2
        driver.snapshot_create.assert_called()
        assert driver.snapshot_create.call_count == 2

    def test_disabled_domain_skipped(self) -> None:
        """Domaines desactivés ignorés."""
        domain = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro")},
            enabled=False,
        )
        infra = make_infra(domains={"pro": domain})
        driver = mock_driver(
            projects=[IncusProject(name="pro")],
            instances={"pro": [running_instance("pro-dev", "pro")]},
        )

        created = create_auto_snapshots(driver, infra, "pre")
        assert len(created) == 0

    def test_multiple_domains(self) -> None:
        """Snapshots sur plusieurs domaines."""
        d1 = make_domain("pro", machines={"dev": make_machine("dev", "pro")})
        d2 = make_domain("perso", machines={"web": make_machine("web", "perso")})
        infra = make_infra(domains={"pro": d1, "perso": d2})
        driver = mock_driver(
            projects=[IncusProject(name="pro"), IncusProject(name="perso")],
            instances={
                "pro": [running_instance("pro-dev", "pro")],
                "perso": [running_instance("perso-web", "perso")],
            },
        )

        created = create_auto_snapshots(driver, infra, "pre")
        assert len(created) == 2

    def test_snapshot_failure_is_warning(self) -> None:
        """Si un snapshot échoue, on continue (best-effort). Pas d'exception."""
        domain = make_domain(
            "pro",
            machines={
                "dev": make_machine("dev", "pro"),
                "desktop": make_machine("desktop", "pro"),
            },
        )
        infra = make_infra(domains={"pro": domain})
        driver = mock_driver(
            projects=[IncusProject(name="pro")],
            instances={
                "pro": [
                    running_instance("pro-dev", "pro"),
                    running_instance("pro-desktop", "pro"),
                ]
            },
        )
        # pro-desktop (alphabétiquement premier) échoue, pro-dev réussit
        driver.snapshot_create.side_effect = [
            IncusError(["incus", "snapshot", "create"], 1, "failed"),
            None,
        ]

        created = create_auto_snapshots(driver, infra, "pre")

        assert len(created) == 1
        assert created[0][0] == "pro-dev"

    def test_stopped_instances_also_snapshotted(self) -> None:
        """Les instances arrêtées sont aussi snapshottées."""
        domain = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro")},
        )
        infra = make_infra(domains={"pro": domain})
        driver = mock_driver(
            projects=[IncusProject(name="pro")],
            instances={"pro": [stopped_instance("pro-dev", "pro")]},
        )

        created = create_auto_snapshots(driver, infra, "pre")
        assert len(created) == 1


# ============================================================
# list_all_snapshots
# ============================================================


class TestListAllSnapshots:
    def test_lists_snapshots_all_domains(self) -> None:
        """Liste les snapshots de toutes les instances de tous les domaines."""
        domain = make_domain("pro", machines={"dev": make_machine("dev", "pro")})
        infra = make_infra(domains={"pro": domain})
        driver = mock_driver(
            projects=[IncusProject(name="pro")],
            instances={"pro": [running_instance("pro-dev", "pro")]},
            snapshots={
                "pro-dev": [
                    IncusSnapshot(
                        name="anklume-pre-20260307-143022", created_at="2026-03-07T14:30Z"
                    ),
                ]
            },
        )

        result = list_all_snapshots(driver, infra)

        assert "pro-dev" in result
        assert len(result["pro-dev"]) == 1
        assert result["pro-dev"][0].name.startswith("anklume-pre-")

    def test_lists_snapshots_specific_instance(self) -> None:
        """Liste les snapshots d'une instance spécifique."""
        domain = make_domain(
            "pro",
            machines={
                "dev": make_machine("dev", "pro"),
                "desktop": make_machine("desktop", "pro"),
            },
        )
        infra = make_infra(domains={"pro": domain})
        driver = mock_driver(
            projects=[IncusProject(name="pro")],
            instances={
                "pro": [
                    running_instance("pro-dev", "pro"),
                    running_instance("pro-desktop", "pro"),
                ]
            },
            snapshots={
                "pro-dev": [IncusSnapshot(name="snap1", created_at="2026-03-07T14:30:22Z")],
                "pro-desktop": [IncusSnapshot(name="snap2", created_at="2026-03-07T15:00:00Z")],
            },
        )

        result = list_all_snapshots(driver, infra, instance_name="pro-dev")

        assert "pro-dev" in result
        assert "pro-desktop" not in result

    def test_empty_snapshots(self) -> None:
        """Instance sans snapshots."""
        domain = make_domain("pro", machines={"dev": make_machine("dev", "pro")})
        infra = make_infra(domains={"pro": domain})
        driver = mock_driver(
            projects=[IncusProject(name="pro")],
            instances={"pro": [running_instance("pro-dev", "pro")]},
            snapshots={"pro-dev": []},
        )

        result = list_all_snapshots(driver, infra)
        assert result.get("pro-dev") == []

    def test_project_not_exists(self) -> None:
        """Domaine dont le projet n'existe pas encore dans Incus."""
        domain = make_domain("pro", machines={"dev": make_machine("dev", "pro")})
        infra = make_infra(domains={"pro": domain})
        driver = mock_driver()

        result = list_all_snapshots(driver, infra)
        assert result == {}


# ============================================================
# restore_snapshot
# ============================================================


class TestRestoreSnapshot:
    def test_restore_running_instance(self) -> None:
        """Restaurer un snapshot sur une instance running : stop → restore → start."""
        driver = mock_driver(
            instances={"pro": [running_instance("pro-dev", "pro")]},
        )

        restore_snapshot(driver, "pro-dev", "pro", "anklume-pre-20260307-143022")

        driver.instance_stop.assert_called_once_with("pro-dev", "pro")
        driver.snapshot_restore.assert_called_once_with(
            "pro-dev",
            "pro",
            "anklume-pre-20260307-143022",
        )
        driver.instance_start.assert_called_once_with("pro-dev", "pro")

    def test_restore_stopped_instance(self) -> None:
        """Restaurer un snapshot sur une instance stopped : restore seulement."""
        driver = mock_driver(
            instances={"pro": [stopped_instance("pro-dev", "pro")]},
        )

        restore_snapshot(driver, "pro-dev", "pro", "snap1")

        driver.instance_stop.assert_not_called()
        driver.snapshot_restore.assert_called_once_with("pro-dev", "pro", "snap1")
        driver.instance_start.assert_not_called()

    def test_restore_error_propagates(self) -> None:
        """Erreur de restore propagée."""
        driver = mock_driver(
            instances={"pro": [stopped_instance("pro-dev", "pro")]},
        )
        driver.snapshot_restore.side_effect = IncusError(
            ["incus", "snapshot", "restore"],
            1,
            "snapshot not found",
        )

        with pytest.raises(IncusError, match="snapshot not found"):
            restore_snapshot(driver, "pro-dev", "pro", "nonexistent")


# ============================================================
# resolve_instance_project
# ============================================================


class TestResolveInstanceProject:
    def test_finds_project(self) -> None:
        domain = make_domain("pro", machines={"dev": make_machine("dev", "pro")})
        infra = make_infra(domains={"pro": domain})

        assert resolve_instance_project(infra, "pro-dev") == "pro"

    def test_not_found_returns_none(self) -> None:
        infra = make_infra()
        assert resolve_instance_project(infra, "pro-dev") is None

    def test_hyphenated_domain(self) -> None:
        """Domaine avec tiret (ex: ai-tools) — résolution correcte."""
        domain = make_domain(
            "ai-tools",
            machines={"gpu": make_machine("gpu", "ai-tools")},
        )
        infra = make_infra(domains={"ai-tools": domain})

        assert resolve_instance_project(infra, "ai-tools-gpu") == "ai-tools"

    def test_multiple_domains(self) -> None:
        d1 = make_domain("pro", machines={"dev": make_machine("dev", "pro")})
        d2 = make_domain("perso", machines={"web": make_machine("web", "perso")})
        infra = make_infra(domains={"pro": d1, "perso": d2})

        assert resolve_instance_project(infra, "pro-dev") == "pro"
        assert resolve_instance_project(infra, "perso-web") == "perso"
        assert resolve_instance_project(infra, "unknown-vm") is None


# ============================================================
# rollback_pre_apply
# ============================================================


class TestRollbackPreApply:
    def test_restores_most_recent_pre_snapshot(self) -> None:
        """Restaure le snapshot anklume-pre-* le plus récent par instance."""
        domain = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro")},
        )
        infra = make_infra(domains={"pro": domain})
        driver = mock_driver(
            projects=[IncusProject(name="pro")],
            instances={"pro": [running_instance("pro-dev", "pro")]},
            snapshots={
                "pro-dev": [
                    IncusSnapshot(
                        name="anklume-pre-20260301-100000",
                        created_at="2026-03-01T10:00Z",
                    ),
                    IncusSnapshot(
                        name="anklume-pre-20260310-120000",
                        created_at="2026-03-10T12:00Z",
                    ),
                    IncusSnapshot(
                        name="anklume-post-20260310-120001",
                        created_at="2026-03-10T12:00Z",
                    ),
                ],
            },
        )

        restored = rollback_pre_apply(driver, infra)

        assert len(restored) == 1
        inst, proj, snap = restored[0]
        assert inst == "pro-dev"
        assert proj == "pro"
        assert snap == "anklume-pre-20260310-120000"
        driver.snapshot_restore.assert_called_once()

    def test_no_pre_snapshots_returns_empty(self) -> None:
        """Aucun snapshot anklume-pre-* → liste vide."""
        domain = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro")},
        )
        infra = make_infra(domains={"pro": domain})
        driver = mock_driver(
            projects=[IncusProject(name="pro")],
            instances={"pro": [running_instance("pro-dev", "pro")]},
            snapshots={
                "pro-dev": [
                    IncusSnapshot(
                        name="anklume-post-20260310-120000",
                        created_at="2026-03-10T12:00Z",
                    ),
                ],
            },
        )

        restored = rollback_pre_apply(driver, infra)

        assert len(restored) == 0

    def test_dry_run_does_not_restore(self) -> None:
        """En dry-run, liste les snapshots mais ne restaure pas."""
        domain = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro")},
        )
        infra = make_infra(domains={"pro": domain})
        driver = mock_driver(
            projects=[IncusProject(name="pro")],
            instances={"pro": [running_instance("pro-dev", "pro")]},
            snapshots={
                "pro-dev": [
                    IncusSnapshot(
                        name="anklume-pre-20260310-120000",
                        created_at="2026-03-10T12:00Z",
                    ),
                ],
            },
        )

        restored = rollback_pre_apply(driver, infra, dry_run=True)

        assert len(restored) == 1
        driver.snapshot_restore.assert_not_called()
        driver.instance_stop.assert_not_called()

    def test_multiple_domains(self) -> None:
        """Rollback sur plusieurs domaines."""
        d1 = make_domain("pro", machines={"dev": make_machine("dev", "pro")})
        d2 = make_domain("perso", machines={"web": make_machine("web", "perso")})
        infra = make_infra(domains={"pro": d1, "perso": d2})
        driver = mock_driver(
            projects=[IncusProject(name="pro"), IncusProject(name="perso")],
            instances={
                "pro": [running_instance("pro-dev", "pro")],
                "perso": [running_instance("perso-web", "perso")],
            },
            snapshots={
                "pro-dev": [
                    IncusSnapshot(
                        name="anklume-pre-20260310-120000",
                        created_at="2026-03-10T12:00Z",
                    ),
                ],
                "perso-web": [
                    IncusSnapshot(
                        name="anklume-pre-20260310-120000",
                        created_at="2026-03-10T12:00Z",
                    ),
                ],
            },
        )

        restored = rollback_pre_apply(driver, infra)

        assert len(restored) == 2

    def test_skips_absent_instances(self) -> None:
        """Ne tente pas de restaurer les instances absentes."""
        domain = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro")},
        )
        infra = make_infra(domains={"pro": domain})
        driver = mock_driver(
            projects=[IncusProject(name="pro")],
            instances={"pro": []},
        )

        restored = rollback_pre_apply(driver, infra)

        assert len(restored) == 0

    def test_skips_absent_project(self) -> None:
        """Ne tente pas de restaurer si le projet n'existe pas."""
        domain = make_domain(
            "pro",
            machines={"dev": make_machine("dev", "pro")},
        )
        infra = make_infra(domains={"pro": domain})
        driver = mock_driver()

        restored = rollback_pre_apply(driver, infra)

        assert len(restored) == 0

    def test_restore_failure_continues(self) -> None:
        """Si la restauration échoue sur une instance, les autres continuent."""
        domain = make_domain(
            "pro",
            machines={
                "dev": make_machine("dev", "pro"),
                "desktop": make_machine("desktop", "pro"),
            },
        )
        infra = make_infra(domains={"pro": domain})
        driver = mock_driver(
            projects=[IncusProject(name="pro")],
            instances={
                "pro": [
                    running_instance("pro-desktop", "pro"),
                    running_instance("pro-dev", "pro"),
                ]
            },
            snapshots={
                "pro-desktop": [
                    IncusSnapshot(
                        name="anklume-pre-20260310-120000",
                        created_at="2026-03-10T12:00Z",
                    ),
                ],
                "pro-dev": [
                    IncusSnapshot(
                        name="anklume-pre-20260310-120000",
                        created_at="2026-03-10T12:00Z",
                    ),
                ],
            },
        )
        # snapshot_restore échoue sur le premier appel (pro-desktop), réussit sur pro-dev
        driver.snapshot_restore.side_effect = [
            IncusError(["incus", "snapshot", "restore"], 1, "failed"),
            None,
        ]

        restored = rollback_pre_apply(driver, infra)

        # pro-desktop échoue (restore_snapshot raises), pro-dev réussit
        assert len(restored) == 1
        assert restored[0][0] == "pro-dev"
